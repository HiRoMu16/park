'use client';

/**
 * ファイルアップローダーコンポーネント
 * - ドラッグ&ドロップ対応
 * - チャンク分割アップロード（100MBチャンク）
 * - 進捗バー（%、転送速度、残り時間）
 * - 複数ファイル対応
 * - キャンセル機能
 * - アップロード完了後、自動でジョブ詳細ページに遷移
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Upload,
  FileVideo,
  FileAudio,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
  UploadCloud,
} from 'lucide-react';
import { clsx } from 'clsx';
import { initUpload, uploadChunk, completeUpload, formatFileSize } from '@/lib/api';
import type { UploadProgress } from '@/types';

/** チャンクサイズ: 100MB */
const CHUNK_SIZE = 100 * 1024 * 1024;

/** 最大ファイルサイズ: 5GB */
const MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024;

/** 対応するファイル形式 */
const ACCEPTED_FORMATS = {
  動画: ['mp4', 'avi', 'mov', 'mkv', 'webm'],
  音声: ['m4a', 'mp3', 'wav', 'flac'],
};

/** MIME型のマッピング */
const ACCEPTED_MIME_TYPES = [
  'video/mp4', 'video/x-msvideo', 'video/quicktime', 'video/x-matroska', 'video/webm',
  'audio/mp4', 'audio/mpeg', 'audio/wav', 'audio/flac', 'audio/x-m4a',
];

/** ファイルアップロード状態 */
interface FileUploadState {
  file: File;
  progress: UploadProgress;
  status: 'pending' | 'uploading' | 'completing' | 'completed' | 'error' | 'cancelled';
  jobId: string | null;
  error: string | null;
}

/** 言語選択オプション */
const LANGUAGE_OPTIONS = [
  { value: 'auto', label: '自動検出' },
  { value: 'ja', label: '日本語' },
  { value: 'en', label: '英語' },
  { value: 'zh', label: '中国語' },
  { value: 'ko', label: '韓国語' },
];

export default function FileUploader() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploads, setUploads] = useState<FileUploadState[]>([]);
  const [language, setLanguage] = useState('auto');
  const abortControllerRef = useRef<Map<string, boolean>>(new Map());

  /** ファイル形式のバリデーション */
  const validateFile = useCallback((file: File): string | null => {
    const ext = file.name.split('.').pop()?.toLowerCase() || '';
    const allFormats = [...ACCEPTED_FORMATS['動画'], ...ACCEPTED_FORMATS['音声']];

    if (!allFormats.includes(ext) && !ACCEPTED_MIME_TYPES.includes(file.type)) {
      return `未対応の形式です: .${ext}`;
    }
    if (file.size > MAX_FILE_SIZE) {
      return `ファイルサイズが上限（5GB）を超えています: ${formatFileSize(file.size)}`;
    }
    if (file.size === 0) {
      return 'ファイルが空です';
    }
    return null;
  }, []);

  /** ファイルの追加処理 */
  const addFiles = useCallback((files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const newUploads: FileUploadState[] = [];

    for (const file of fileArray) {
      const error = validateFile(file);
      newUploads.push({
        file,
        progress: { loaded: 0, total: file.size, percentage: 0, speed: 0, remainingTime: 0 },
        status: error ? 'error' : 'pending',
        jobId: null,
        error,
      });
    }

    setUploads((prev) => [...prev, ...newUploads]);
  }, [validateFile]);

  /** ドラッグ&ドロップハンドラ */
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  }, [addFiles]);

  /** ファイル選択ハンドラ */
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
      // input要素をリセットして同じファイルの再選択を可能にする
      e.target.value = '';
    }
  }, [addFiles]);

  /** アップロードからファイルを除去する */
  const removeUpload = useCallback((index: number) => {
    setUploads((prev) => {
      const upload = prev[index];
      if (upload?.jobId) {
        abortControllerRef.current.set(upload.jobId, true);
      }
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  /** 単一ファイルのチャンク分割アップロード実行 */
  const executeUpload = useCallback(async (index: number) => {
    setUploads((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], status: 'uploading' };
      return updated;
    });

    try {
      // 1. アップロード初期化
      const uploadState = uploads[index];
      if (!uploadState) return;

      const { job_id } = await initUpload(
        uploadState.file.name,
        uploadState.file.size,
        language
      );

      setUploads((prev) => {
        const updated = [...prev];
        if (updated[index]) {
          updated[index] = { ...updated[index], jobId: job_id };
        }
        return updated;
      });

      // 2. チャンク分割して送信
      const totalChunks = Math.ceil(uploadState.file.size / CHUNK_SIZE);
      let totalLoaded = 0;
      const startTime = Date.now();

      for (let i = 0; i < totalChunks; i++) {
        // キャンセルチェック
        if (abortControllerRef.current.get(job_id)) {
          abortControllerRef.current.delete(job_id);
          setUploads((prev) => {
            const updated = [...prev];
            if (updated[index]) {
              updated[index] = { ...updated[index], status: 'cancelled' };
            }
            return updated;
          });
          return;
        }

        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, uploadState.file.size);
        const chunk = uploadState.file.slice(start, end);

        await uploadChunk(job_id, i, totalChunks, chunk, (loaded) => {
          const currentLoaded = totalLoaded + loaded;
          const elapsed = (Date.now() - startTime) / 1000;
          const speed = elapsed > 0 ? currentLoaded / elapsed : 0;
          const remaining = speed > 0 ? (uploadState.file.size - currentLoaded) / speed : 0;

          setUploads((prev) => {
            const updated = [...prev];
            if (updated[index]) {
              updated[index] = {
                ...updated[index],
                progress: {
                  loaded: currentLoaded,
                  total: uploadState.file.size,
                  percentage: Math.round((currentLoaded / uploadState.file.size) * 100),
                  speed,
                  remainingTime: remaining,
                },
              };
            }
            return updated;
          });
        });

        totalLoaded += (end - start);
      }

      // 3. アップロード完了通知
      setUploads((prev) => {
        const updated = [...prev];
        if (updated[index]) {
          updated[index] = {
            ...updated[index],
            status: 'completing',
            progress: {
              ...updated[index].progress,
              loaded: uploadState.file.size,
              percentage: 100,
            },
          };
        }
        return updated;
      });

      await completeUpload(job_id, totalChunks);

      setUploads((prev) => {
        const updated = [...prev];
        if (updated[index]) {
          updated[index] = { ...updated[index], status: 'completed' };
        }
        return updated;
      });

      // 自動遷移（完了後1秒待ってからジョブ詳細ページへ）
      setTimeout(() => {
        router.push(`/jobs/${job_id}`);
      }, 1000);

    } catch (error) {
      const message = error instanceof Error ? error.message : 'アップロードに失敗しました';
      setUploads((prev) => {
        const updated = [...prev];
        if (updated[index]) {
          updated[index] = { ...updated[index], status: 'error', error: message };
        }
        return updated;
      });
    }
  }, [uploads, language, router]);

  /** 全ファイルのアップロード開始 */
  const startAllUploads = useCallback(() => {
    uploads.forEach((upload, index) => {
      if (upload.status === 'pending') {
        executeUpload(index);
      }
    });
  }, [uploads, executeUpload]);

  /** アップロードのキャンセル */
  const cancelUpload = useCallback((index: number) => {
    const upload = uploads[index];
    if (upload?.jobId) {
      abortControllerRef.current.set(upload.jobId, true);
    }
    setUploads((prev) => {
      const updated = [...prev];
      if (updated[index]) {
        updated[index] = { ...updated[index], status: 'cancelled' };
      }
      return updated;
    });
  }, [uploads]);

  /** 転送速度の表示用フォーマット */
  const formatSpeed = (bytesPerSec: number): string => {
    if (bytesPerSec === 0) return '計算中...';
    return `${formatFileSize(bytesPerSec)}/秒`;
  };

  /** 残り時間の表示用フォーマット */
  const formatRemainingTime = (seconds: number): string => {
    if (seconds <= 0 || !isFinite(seconds)) return '計算中...';
    if (seconds < 60) return `残り ${Math.ceil(seconds)}秒`;
    if (seconds < 3600) return `残り ${Math.ceil(seconds / 60)}分`;
    return `残り ${Math.floor(seconds / 3600)}時間${Math.ceil((seconds % 3600) / 60)}分`;
  };

  /** ファイルアイコンの判定 */
  const getFileIcon = (fileName: string) => {
    const ext = fileName.split('.').pop()?.toLowerCase() || '';
    if (ACCEPTED_FORMATS['動画'].includes(ext)) return FileVideo;
    return FileAudio;
  };

  /** ステータスに応じた色を返す */
  const getStatusColor = (status: FileUploadState['status']): string => {
    switch (status) {
      case 'pending': return 'text-gray-500';
      case 'uploading': return 'text-brand-500';
      case 'completing': return 'text-brand-600';
      case 'completed': return 'text-green-500';
      case 'error': return 'text-red-500';
      case 'cancelled': return 'text-gray-400';
      default: return 'text-gray-500';
    }
  };

  /** ステータスのラベルを返す */
  const getStatusLabel = (status: FileUploadState['status']): string => {
    switch (status) {
      case 'pending': return '待機中';
      case 'uploading': return 'アップロード中';
      case 'completing': return '処理を開始しています...';
      case 'completed': return '完了';
      case 'error': return 'エラー';
      case 'cancelled': return 'キャンセル済み';
      default: return '';
    }
  };

  /** 待機中のファイルがあるかチェック */
  const hasPendingFiles = uploads.some((u) => u.status === 'pending');

  // コンポーネントのクリーンアップ
  useEffect(() => {
    return () => {
      abortControllerRef.current.clear();
    };
  }, []);

  return (
    <div className="space-y-6">
      {/* ドラッグ&ドロップエリア */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={clsx(
          'drop-zone cursor-pointer group',
          isDragOver && 'drop-zone-active'
        )}
      >
        {/* 隠しファイルinput */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_MIME_TYPES.join(',')}
          onChange={handleFileSelect}
          className="hidden"
        />

        <div className="flex flex-col items-center gap-4 py-8">
          {/* アイコン */}
          <div className={clsx(
            'flex h-16 w-16 items-center justify-center rounded-2xl transition-all duration-300',
            isDragOver
              ? 'bg-brand-100 text-brand-600 dark:bg-brand-900/50 dark:text-brand-400 scale-110'
              : 'bg-gray-100 text-gray-400 group-hover:bg-brand-50 group-hover:text-brand-500 dark:bg-gray-800 dark:text-gray-500 dark:group-hover:bg-brand-950/50 dark:group-hover:text-brand-400'
          )}>
            <UploadCloud className="h-8 w-8" />
          </div>

          {/* テキスト */}
          <div className="space-y-2">
            <p className="text-lg font-semibold text-gray-700 dark:text-gray-200">
              {isDragOver ? 'ここにドロップしてください' : 'ファイルをドラッグ&ドロップ'}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              または<span className="mx-1 font-medium text-brand-500 hover:text-brand-600">クリックしてファイルを選択</span>
            </p>
          </div>

          {/* 対応形式の一覧 */}
          <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
            {Object.entries(ACCEPTED_FORMATS).map(([category, formats]) => (
              <div key={category} className="flex items-center gap-1.5">
                <span className="text-xs font-medium text-gray-400 dark:text-gray-500">{category}:</span>
                {formats.map((fmt) => (
                  <span
                    key={fmt}
                    className="rounded-md bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                  >
                    .{fmt.toUpperCase()}
                  </span>
                ))}
              </div>
            ))}
          </div>

          {/* サイズ制限 */}
          <p className="text-xs text-gray-400 dark:text-gray-500">
            最大ファイルサイズ: 5GB / 1000MB超の大容量ファイルに対応
          </p>
        </div>
      </div>

      {/* 言語選択とアップロードボタン */}
      {uploads.length > 0 && (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          {/* 言語選択 */}
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              文字起こし言語
            </label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 sm:w-48"
            >
              {LANGUAGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* アップロード開始ボタン */}
          {hasPendingFiles && (
            <button
              onClick={startAllUploads}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all duration-200 hover:from-brand-600 hover:to-brand-700 hover:shadow-xl hover:shadow-brand-500/30 active:scale-[0.98]"
            >
              <Upload className="h-4 w-4" />
              アップロード開始
            </button>
          )}
        </div>
      )}

      {/* ファイル一覧 */}
      {uploads.length > 0 && (
        <div className="space-y-3">
          {uploads.map((upload, index) => {
            const FileIcon = getFileIcon(upload.file.name);
            return (
              <div
                key={`${upload.file.name}-${index}`}
                className="animate-slide-up rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md dark:border-gray-700 dark:bg-gray-900"
              >
                <div className="flex items-start gap-3">
                  {/* ファイルアイコン */}
                  <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-brand-50 dark:bg-brand-950/30">
                    <FileIcon className="h-5 w-5 text-brand-500" />
                  </div>

                  {/* ファイル情報 */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                          {upload.file.name}
                        </p>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          {formatFileSize(upload.file.size)}
                        </p>
                      </div>

                      {/* ステータスとアクション */}
                      <div className="flex items-center gap-2">
                        <span className={clsx('text-xs font-medium', getStatusColor(upload.status))}>
                          {getStatusLabel(upload.status)}
                        </span>

                        {/* アップロード中のキャンセルボタン */}
                        {upload.status === 'uploading' && (
                          <button
                            onClick={() => cancelUpload(index)}
                            className="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-red-500 dark:hover:bg-gray-800"
                            title="キャンセル"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}

                        {/* 待機中・エラー時の削除ボタン */}
                        {(upload.status === 'pending' || upload.status === 'error' || upload.status === 'cancelled') && (
                          <button
                            onClick={() => removeUpload(index)}
                            className="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-red-500 dark:hover:bg-gray-800"
                            title="削除"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}

                        {/* 完了アイコン */}
                        {upload.status === 'completed' && (
                          <CheckCircle2 className="h-5 w-5 text-green-500" />
                        )}

                        {/* ローディングアイコン */}
                        {upload.status === 'completing' && (
                          <Loader2 className="h-5 w-5 animate-spin text-brand-500" />
                        )}
                      </div>
                    </div>

                    {/* プログレスバー */}
                    {(upload.status === 'uploading' || upload.status === 'completing') && (
                      <div className="mt-3 space-y-1.5">
                        <div className="h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                          <div
                            className="progress-bar-animated progress-bar-striped h-full rounded-full transition-all duration-300"
                            style={{ width: `${upload.progress.percentage}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
                          <span>
                            {formatFileSize(upload.progress.loaded)} / {formatFileSize(upload.progress.total)}
                            （{upload.progress.percentage}%）
                          </span>
                          <span>
                            {formatSpeed(upload.progress.speed)} - {formatRemainingTime(upload.progress.remainingTime)}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* エラーメッセージ */}
                    {upload.status === 'error' && upload.error && (
                      <div className="mt-2 flex items-center gap-1.5 text-xs text-red-500">
                        <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                        <span>{upload.error}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
