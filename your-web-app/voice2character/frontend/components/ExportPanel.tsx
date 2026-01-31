'use client';

/**
 * エクスポートパネルコンポーネント
 * - エクスポート形式選択（TXT, SRT, VTT, JSON, TSV）
 * - 各形式の説明
 * - ダウンロードボタン
 * - プレビュー表示
 */

import { useState, useMemo } from 'react';
import {
  Download,
  FileText,
  Film,
  Code2,
  Table,
  Eye,
  EyeOff,
  CheckCircle2,
} from 'lucide-react';
import { clsx } from 'clsx';
import { getExportUrl, formatDuration } from '@/lib/api';
import type { ExportFormat, TranscriptionSegment } from '@/types';

/** エクスポート形式の情報 */
interface FormatInfo {
  id: ExportFormat;
  label: string;
  description: string;
  icon: React.ElementType;
  extension: string;
}

/** エクスポート形式一覧 */
const FORMATS: FormatInfo[] = [
  {
    id: 'txt',
    label: 'テキスト',
    description: 'プレーンテキスト形式。シンプルで読みやすいフォーマット。',
    icon: FileText,
    extension: '.txt',
  },
  {
    id: 'srt',
    label: 'SRT字幕',
    description: 'SubRip字幕形式。動画編集ソフトで広く対応。',
    icon: Film,
    extension: '.srt',
  },
  {
    id: 'vtt',
    label: 'WebVTT',
    description: 'Web Video Text Tracks形式。Webプレイヤーに最適。',
    icon: Film,
    extension: '.vtt',
  },
  {
    id: 'json',
    label: 'JSON',
    description: '構造化データ形式。プログラムでの処理に最適。',
    icon: Code2,
    extension: '.json',
  },
  {
    id: 'tsv',
    label: 'TSV',
    description: 'タブ区切り形式。スプレッドシートでの分析に対応。',
    icon: Table,
    extension: '.tsv',
  },
];

/** コンポーネントのプロパティ */
interface ExportPanelProps {
  /** ジョブID */
  jobId: string;
  /** ファイル名（拡張子なし） */
  fileName: string;
  /** セグメント一覧（プレビュー用） */
  segments: TranscriptionSegment[];
  /** フルテキスト（プレビュー用） */
  fullText: string;
}

/**
 * SRT形式のタイムコードを生成
 */
function formatSrtTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
}

/**
 * VTT形式のタイムコードを生成
 */
function formatVttTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
}

export default function ExportPanel({
  jobId,
  fileName,
  segments,
  fullText,
}: ExportPanelProps) {
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat>('txt');
  const [showPreview, setShowPreview] = useState(false);

  /** 選択した形式のプレビューテキストを生成（最初の5セグメント） */
  const previewText = useMemo(() => {
    const previewSegments = segments.slice(0, 5);
    const hasMore = segments.length > 5;

    switch (selectedFormat) {
      case 'txt': {
        let text = previewSegments
          .map((seg) => `[${formatDuration(seg.start_time)}] ${seg.text}`)
          .join('\n');
        if (hasMore) text += '\n...(以下省略)';
        return text;
      }
      case 'srt': {
        let text = previewSegments
          .map(
            (seg, i) =>
              `${i + 1}\n${formatSrtTime(seg.start_time)} --> ${formatSrtTime(seg.end_time)}\n${seg.text}\n`
          )
          .join('\n');
        if (hasMore) text += '\n...(以下省略)';
        return text;
      }
      case 'vtt': {
        let text = 'WEBVTT\n\n';
        text += previewSegments
          .map(
            (seg) =>
              `${formatVttTime(seg.start_time)} --> ${formatVttTime(seg.end_time)}\n${seg.text}\n`
          )
          .join('\n');
        if (hasMore) text += '\n...(以下省略)';
        return text;
      }
      case 'json': {
        const jsonData = {
          segments: previewSegments.map((seg) => ({
            start: seg.start_time,
            end: seg.end_time,
            text: seg.text,
            confidence: seg.confidence,
          })),
        };
        let text = JSON.stringify(jsonData, null, 2);
        if (hasMore) text += '\n// ...(以下省略)';
        return text;
      }
      case 'tsv': {
        let text = 'start_time\tend_time\ttext\tconfidence\n';
        text += previewSegments
          .map(
            (seg) =>
              `${seg.start_time}\t${seg.end_time}\t${seg.text}\t${seg.confidence ?? ''}`
          )
          .join('\n');
        if (hasMore) text += '\n...(以下省略)';
        return text;
      }
      default:
        return '';
    }
  }, [selectedFormat, segments]);

  /** ダウンロードURLの取得 */
  const downloadUrl = getExportUrl(jobId, selectedFormat);

  /** 選択中のフォーマット情報 */
  const selectedFormatInfo = FORMATS.find((f) => f.id === selectedFormat);

  return (
    <div className="space-y-5">
      {/* セクションヘッダー */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          エクスポート
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          文字起こし結果をお好みの形式でダウンロードできます。
        </p>
      </div>

      {/* フォーマット選択グリッド */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {FORMATS.map((format) => {
          const Icon = format.icon;
          const isSelected = selectedFormat === format.id;

          return (
            <button
              key={format.id}
              onClick={() => setSelectedFormat(format.id)}
              className={clsx(
                'relative flex flex-col items-center gap-2 rounded-xl border-2 p-4 text-center transition-all duration-200',
                isSelected
                  ? 'border-brand-500 bg-brand-50 shadow-sm dark:border-brand-400 dark:bg-brand-950/30'
                  : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:hover:border-gray-600 dark:hover:bg-gray-800'
              )}
            >
              {/* 選択インジケーター */}
              {isSelected && (
                <div className="absolute right-2 top-2">
                  <CheckCircle2 className="h-4 w-4 text-brand-500 dark:text-brand-400" />
                </div>
              )}

              <Icon
                className={clsx(
                  'h-6 w-6',
                  isSelected
                    ? 'text-brand-500 dark:text-brand-400'
                    : 'text-gray-400 dark:text-gray-500'
                )}
              />
              <div>
                <p
                  className={clsx(
                    'text-sm font-semibold',
                    isSelected
                      ? 'text-brand-700 dark:text-brand-300'
                      : 'text-gray-700 dark:text-gray-300'
                  )}
                >
                  {format.label}
                </p>
                <p className="mt-0.5 text-[10px] text-gray-400 dark:text-gray-500">
                  {format.extension}
                </p>
              </div>
            </button>
          );
        })}
      </div>

      {/* 選択した形式の説明 */}
      {selectedFormatInfo && (
        <div className="rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-800/50">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {selectedFormatInfo.description}
          </p>
        </div>
      )}

      {/* アクションボタン */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        {/* ダウンロードボタン */}
        <a
          href={downloadUrl}
          download={`${fileName}${selectedFormatInfo?.extension || '.txt'}`}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all duration-200 hover:from-brand-600 hover:to-brand-700 hover:shadow-xl hover:shadow-brand-500/30 active:scale-[0.98]"
        >
          <Download className="h-4 w-4" />
          {selectedFormatInfo?.label}形式でダウンロード
        </a>

        {/* プレビュートグル */}
        <button
          onClick={() => setShowPreview(!showPreview)}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-600 transition-all duration-200 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
        >
          {showPreview ? (
            <>
              <EyeOff className="h-4 w-4" />
              プレビューを閉じる
            </>
          ) : (
            <>
              <Eye className="h-4 w-4" />
              プレビューを表示
            </>
          )}
        </button>
      </div>

      {/* プレビュー表示 */}
      {showPreview && (
        <div className="animate-slide-up overflow-hidden rounded-xl border border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-700 dark:bg-gray-800">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
              プレビュー ({selectedFormatInfo?.label} - {selectedFormatInfo?.extension})
            </span>
            <span className="text-[10px] text-gray-400 dark:text-gray-500">
              最初の5セグメントを表示
            </span>
          </div>
          <pre className="max-h-64 overflow-auto bg-white p-4 text-xs leading-relaxed text-gray-700 dark:bg-gray-900 dark:text-gray-300">
            <code>{previewText}</code>
          </pre>
        </div>
      )}
    </div>
  );
}
