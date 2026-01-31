'use client';

/**
 * 文字起こし結果表示コンポーネント
 * - タイムスタンプ付きセグメント一覧
 * - テキスト検索機能（ハイライト）
 * - コピーボタン（全文コピー）
 * - 信頼度スコアが低いセグメントの視覚的マーキング
 * - フルテキスト/セグメント表示モードの切り替え
 */

import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import {
  Search,
  Copy,
  Check,
  AlignLeft,
  List,
  ChevronUp,
  AlertTriangle,
  X,
} from 'lucide-react';
import { clsx } from 'clsx';
import { formatDuration } from '@/lib/api';
import type { TranscriptionSegment } from '@/types';

/** 低信頼度の閾値 */
const LOW_CONFIDENCE_THRESHOLD = 0.7;

/** 表示モード */
type ViewMode = 'segments' | 'fulltext';

/** コンポーネントのプロパティ */
interface TranscriptionViewerProps {
  /** セグメント一覧 */
  segments: TranscriptionSegment[];
  /** フルテキスト */
  fullText: string;
}

export default function TranscriptionViewer({
  segments,
  fullText,
}: TranscriptionViewerProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('segments');
  const [searchQuery, setSearchQuery] = useState('');
  const [copied, setCopied] = useState(false);
  const [highlightedSegmentId, setHighlightedSegmentId] = useState<number | null>(null);
  const segmentRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const listContainerRef = useRef<HTMLDivElement>(null);

  /** 検索クエリに一致するセグメントをフィルタリング */
  const filteredSegments = useMemo(() => {
    if (!searchQuery.trim()) return segments;
    const query = searchQuery.toLowerCase();
    return segments.filter((seg) => seg.text.toLowerCase().includes(query));
  }, [segments, searchQuery]);

  /** 検索結果のハイライト表示 */
  const highlightText = useCallback((text: string, query: string): React.ReactNode => {
    if (!query.trim()) return text;
    const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
    return parts.map((part, index) =>
      part.toLowerCase() === query.toLowerCase() ? (
        <mark
          key={index}
          className="rounded-sm bg-yellow-200 px-0.5 text-yellow-900 dark:bg-yellow-500/30 dark:text-yellow-200"
        >
          {part}
        </mark>
      ) : (
        part
      )
    );
  }, []);

  /** セグメントへのスクロール */
  const scrollToSegment = useCallback((segmentId: number) => {
    const element = segmentRefs.current.get(segmentId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setHighlightedSegmentId(segmentId);
      // ハイライトを一定時間後に解除
      setTimeout(() => setHighlightedSegmentId(null), 2000);
    }
  }, []);

  /** 全文コピー */
  const handleCopy = useCallback(async () => {
    try {
      const textToCopy = viewMode === 'fulltext'
        ? fullText
        : segments.map((seg) => `[${formatDuration(seg.start_time)}] ${seg.text}`).join('\n');
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // フォールバック: テキストエリアを使ったコピー
      const textArea = document.createElement('textarea');
      textArea.value = fullText;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [fullText, segments, viewMode]);

  /** ページトップへスクロール */
  const scrollToTop = useCallback(() => {
    if (listContainerRef.current) {
      listContainerRef.current.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }, []);

  // 検索クエリ変更時にハイライトをリセット
  useEffect(() => {
    setHighlightedSegmentId(null);
  }, [searchQuery]);

  return (
    <div className="space-y-4">
      {/* ツールバー */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* 左側: 表示モード切り替え */}
        <div className="flex items-center gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
          <button
            onClick={() => setViewMode('segments')}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-200',
              viewMode === 'segments'
                ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            )}
          >
            <List className="h-3.5 w-3.5" />
            セグメント表示
          </button>
          <button
            onClick={() => setViewMode('fulltext')}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-200',
              viewMode === 'fulltext'
                ? 'bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
            )}
          >
            <AlignLeft className="h-3.5 w-3.5" />
            フルテキスト
          </button>
        </div>

        {/* 右側: 検索とコピー */}
        <div className="flex items-center gap-2">
          {/* 検索入力 */}
          <div className="relative flex-1 sm:flex-initial">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="テキストを検索..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-9 pr-8 text-sm placeholder-gray-400 transition-all focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:placeholder-gray-500 sm:w-64"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* コピーボタン */}
          <button
            onClick={handleCopy}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-all duration-200',
              copied
                ? 'border-green-300 bg-green-50 text-green-700 dark:border-green-700 dark:bg-green-950/20 dark:text-green-400'
                : 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
            )}
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5" />
                コピー済み
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                全文コピー
              </>
            )}
          </button>
        </div>
      </div>

      {/* 検索結果件数 */}
      {searchQuery && (
        <div className="text-xs text-gray-500 dark:text-gray-400">
          {filteredSegments.length}件のセグメントが見つかりました
          {filteredSegments.length !== segments.length && ` （全${segments.length}件中）`}
        </div>
      )}

      {/* セグメント表示モード */}
      {viewMode === 'segments' && (
        <div
          ref={listContainerRef}
          className="max-h-[600px] overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-700"
        >
          {filteredSegments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Search className="h-8 w-8 text-gray-300 dark:text-gray-600" />
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                一致するテキストが見つかりませんでした
              </p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {filteredSegments.map((segment) => {
                const isLowConfidence =
                  segment.confidence !== null &&
                  segment.confidence < LOW_CONFIDENCE_THRESHOLD;
                const isHighlighted = highlightedSegmentId === segment.id;

                return (
                  <div
                    key={segment.id}
                    ref={(el) => {
                      if (el) segmentRefs.current.set(segment.id, el);
                    }}
                    className={clsx(
                      'group flex gap-3 px-4 py-3 transition-colors duration-200',
                      isHighlighted && 'segment-highlight',
                      isLowConfidence
                        ? 'bg-yellow-50/50 dark:bg-yellow-950/10'
                        : 'hover:bg-gray-50 dark:hover:bg-gray-800/50'
                    )}
                  >
                    {/* タイムスタンプ */}
                    <button
                      onClick={() => scrollToSegment(segment.id)}
                      className="flex-shrink-0 pt-0.5"
                      title="このセグメントにスクロール"
                    >
                      <span className="inline-flex items-center rounded-md bg-gray-100 px-2 py-1 text-xs font-mono font-medium text-gray-600 transition-colors hover:bg-brand-100 hover:text-brand-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-brand-950/30 dark:hover:text-brand-400">
                        {formatDuration(segment.start_time)}
                      </span>
                    </button>

                    {/* テキスト内容 */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm leading-relaxed text-gray-800 dark:text-gray-200">
                        {highlightText(segment.text, searchQuery)}
                      </p>
                      <div className="mt-1 flex items-center gap-3 text-[10px] text-gray-400 dark:text-gray-500">
                        <span>
                          {formatDuration(segment.start_time)} - {formatDuration(segment.end_time)}
                        </span>
                        {segment.confidence !== null && (
                          <span className={clsx(
                            'inline-flex items-center gap-0.5',
                            isLowConfidence && 'text-yellow-600 dark:text-yellow-400'
                          )}>
                            {isLowConfidence && <AlertTriangle className="h-3 w-3" />}
                            信頼度: {(segment.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* トップへスクロールボタン */}
          {filteredSegments.length > 10 && (
            <div className="sticky bottom-0 flex justify-end border-t border-gray-100 bg-white/80 p-2 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/80">
              <button
                onClick={scrollToTop}
                className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
              >
                <ChevronUp className="h-3.5 w-3.5" />
                先頭へ
              </button>
            </div>
          )}
        </div>
      )}

      {/* フルテキスト表示モード */}
      {viewMode === 'fulltext' && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700">
          <div className="max-h-[600px] overflow-y-auto p-6">
            <div className="prose prose-sm max-w-none dark:prose-invert">
              <p className="whitespace-pre-wrap leading-relaxed text-gray-800 dark:text-gray-200">
                {searchQuery ? highlightText(fullText, searchQuery) : fullText}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 統計情報 */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg bg-gray-50 px-4 py-3 dark:bg-gray-800/50">
        <div className="text-xs text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-700 dark:text-gray-300">{segments.length}</span> セグメント
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-700 dark:text-gray-300">{fullText.length}</span> 文字
        </div>
        {segments.length > 0 && (
          <div className="text-xs text-gray-500 dark:text-gray-400">
            <span className="font-medium text-gray-700 dark:text-gray-300">
              {formatDuration(segments[segments.length - 1].end_time)}
            </span> の音声
          </div>
        )}
        {segments.filter((s) => s.confidence !== null && s.confidence < LOW_CONFIDENCE_THRESHOLD).length > 0 && (
          <div className="flex items-center gap-1 text-xs text-yellow-600 dark:text-yellow-400">
            <AlertTriangle className="h-3 w-3" />
            <span>
              {segments.filter((s) => s.confidence !== null && s.confidence < LOW_CONFIDENCE_THRESHOLD).length}件の低信頼度セグメント
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
