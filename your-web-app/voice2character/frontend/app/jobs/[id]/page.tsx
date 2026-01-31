'use client';

/**
 * ジョブ詳細ページ
 * - ジョブ情報表示（ファイル名、サイズ、ステータス、作成日時）
 * - ProgressTrackerコンポーネント（処理中の場合）
 * - TranscriptionViewerコンポーネント（完了時）
 * - ExportPanelコンポーネント（完了時）
 * - WebSocket接続で進捗をリアルタイム更新
 * - エラー時のリトライボタン
 * - 戻るリンク
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  FileText,
  HardDrive,
  Clock,
  RefreshCw,
  Loader2,
  AlertCircle,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { clsx } from 'clsx';
import { getJob, getTranscription, formatFileSize, formatDate, formatDuration } from '@/lib/api';
import { WebSocketManager } from '@/lib/websocket';
import type { ConnectionState } from '@/lib/websocket';
import type { Job, Transcription, JobStatus } from '@/types';
import ProgressTracker from '@/components/ProgressTracker';
import TranscriptionViewer from '@/components/TranscriptionViewer';
import ExportPanel from '@/components/ExportPanel';

/** ステータスラベルと色のマッピング */
const STATUS_LABELS: Record<JobStatus, { label: string; className: string }> = {
  uploading: {
    label: 'アップロード中',
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  queued: {
    label: 'キュー待ち',
    className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  extracting: {
    label: '音声抽出中',
    className: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  },
  transcribing: {
    label: '文字起こし中',
    className: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  },
  completed: {
    label: '完了',
    className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  failed: {
    label: 'エラー',
    className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
};

export default function JobDetailPage() {
  const params = useParams();
  const jobId = params.id as string;

  const [job, setJob] = useState<Job | null>(null);
  const [transcription, setTranscription] = useState<Transcription | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wsState, setWsState] = useState<ConnectionState>('disconnected');
  const wsManagerRef = useRef<WebSocketManager | null>(null);

  /** ジョブ情報を取得する */
  const fetchJob = useCallback(async () => {
    try {
      const data = await getJob(jobId);
      setJob(data);
      setError(null);

      // 完了済みの場合は文字起こし結果も取得
      if (data.status === 'completed') {
        try {
          const transData = await getTranscription(jobId);
          setTranscription(transData);
        } catch (transErr) {
          console.error('文字起こし結果の取得に失敗:', transErr);
        }
      }

      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ジョブ情報の取得に失敗しました');
      return null;
    }
  }, [jobId]);

  /** 初回データ読み込み */
  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setIsLoading(true);
      const jobData = await fetchJob();
      if (mounted) {
        setIsLoading(false);
      }

      // 処理中のジョブの場合、WebSocket接続を開始
      if (
        mounted &&
        jobData &&
        !['completed', 'failed'].includes(jobData.status)
      ) {
        startWebSocket();
      }
    };

    load();

    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  /** WebSocket接続を開始する */
  const startWebSocket = useCallback(() => {
    // 既存の接続を切断
    if (wsManagerRef.current) {
      wsManagerRef.current.destroy();
    }

    const manager = new WebSocketManager();
    wsManagerRef.current = manager;

    // 接続状態の監視
    manager.onStateChange((state) => {
      setWsState(state);
    });

    // 進捗更新の処理
    manager.onProgress((message) => {
      setJob((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          status: message.status,
          progress: message.progress,
          error_message: message.error_message || prev.error_message,
        };
      });

      // 完了時に文字起こし結果を取得
      if (message.status === 'completed') {
        getTranscription(jobId)
          .then((data) => setTranscription(data))
          .catch(console.error);
        // WebSocket切断
        manager.disconnect();
      }

      // エラー時にWebSocket切断
      if (message.status === 'failed') {
        manager.disconnect();
      }
    });

    // 接続開始
    manager.connect(jobId);
  }, [jobId]);

  /** コンポーネントのクリーンアップ */
  useEffect(() => {
    return () => {
      if (wsManagerRef.current) {
        wsManagerRef.current.destroy();
        wsManagerRef.current = null;
      }
    };
  }, []);

  /** リトライ処理 */
  const handleRetry = async () => {
    setIsLoading(true);
    setError(null);
    const jobData = await fetchJob();
    setIsLoading(false);

    if (jobData && !['completed', 'failed'].includes(jobData.status)) {
      startWebSocket();
    }
  };

  /** 処理中かどうかの判定 */
  const isProcessing = job
    ? ['uploading', 'queued', 'extracting', 'transcribing'].includes(job.status)
    : false;

  // ローディング状態
  if (isLoading) {
    return (
      <div className="page-transition flex flex-col items-center justify-center py-24">
        <Loader2 className="h-10 w-10 animate-spin text-brand-500" />
        <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
          ジョブ情報を読み込み中...
        </p>
      </div>
    );
  }

  // エラー状態（ジョブが見つからない場合）
  if (error && !job) {
    return (
      <div className="page-transition mx-auto max-w-2xl py-12">
        <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center dark:border-red-800 dark:bg-red-950/20">
          <AlertCircle className="mx-auto h-10 w-10 text-red-400" />
          <h2 className="mt-4 text-lg font-semibold text-red-700 dark:text-red-400">
            エラーが発生しました
          </h2>
          <p className="mt-2 text-sm text-red-600 dark:text-red-300">
            {error}
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={handleRetry}
              className="inline-flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-600"
            >
              <RefreshCw className="h-4 w-4" />
              再読み込み
            </button>
            <Link
              href="/"
              className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-medium text-gray-600 ring-1 ring-gray-200 transition-colors hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-gray-700"
            >
              <ArrowLeft className="h-4 w-4" />
              ホームへ戻る
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!job) return null;

  return (
    <div className="page-transition mx-auto max-w-4xl space-y-8 pb-12">
      {/* ============================================
          ナビゲーション
          ============================================ */}
      <div className="flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
        >
          <ArrowLeft className="h-4 w-4" />
          ホームへ戻る
        </Link>

        {/* WebSocket接続状態インジケーター */}
        {isProcessing && (
          <div className="flex items-center gap-1.5">
            {wsState === 'connected' ? (
              <Wifi className="h-4 w-4 text-green-500" />
            ) : wsState === 'connecting' ? (
              <Loader2 className="h-4 w-4 animate-spin text-yellow-500" />
            ) : (
              <WifiOff className="h-4 w-4 text-gray-400" />
            )}
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {wsState === 'connected'
                ? 'リアルタイム更新中'
                : wsState === 'connecting'
                  ? '接続中...'
                  : 'オフライン'}
            </span>
          </div>
        )}
      </div>

      {/* ============================================
          ジョブ情報カード
          ============================================ */}
      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          {/* 左側: ジョブ情報 */}
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-brand-50 dark:bg-brand-950/30">
              <FileText className="h-6 w-6 text-brand-500" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                {job.file_name}
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                <span className="inline-flex items-center gap-1.5">
                  <HardDrive className="h-4 w-4" />
                  {formatFileSize(job.file_size)}
                </span>
                {job.duration && (
                  <span className="inline-flex items-center gap-1.5">
                    <Clock className="h-4 w-4" />
                    {formatDuration(job.duration)}
                  </span>
                )}
                <span className="inline-flex items-center gap-1.5">
                  <Clock className="h-4 w-4" />
                  {formatDate(job.created_at)}
                </span>
              </div>
            </div>
          </div>

          {/* 右側: ステータスバッジ */}
          <div className="flex items-center gap-3">
            <span
              className={clsx(
                'status-badge text-sm',
                STATUS_LABELS[job.status].className
              )}
            >
              {STATUS_LABELS[job.status].label}
            </span>
            {/* 更新ボタン */}
            <button
              onClick={handleRetry}
              className="rounded-lg p-2 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
              title="情報を更新"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* ============================================
          進捗トラッカー（処理中の場合）
          ============================================ */}
      {isProcessing && (
        <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <ProgressTracker
            status={job.status}
            progress={job.progress}
            errorMessage={job.error_message}
          />
        </div>
      )}

      {/* ============================================
          エラー表示とリトライ（失敗時）
          ============================================ */}
      {job.status === 'failed' && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <ProgressTracker
              status={job.status}
              progress={job.progress}
              errorMessage={job.error_message}
            />
          </div>
          <div className="text-center">
            <button
              onClick={handleRetry}
              className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-500/25 transition-all hover:bg-brand-600 hover:shadow-xl hover:shadow-brand-500/30"
            >
              <RefreshCw className="h-4 w-4" />
              再読み込み
            </button>
          </div>
        </div>
      )}

      {/* ============================================
          文字起こし結果（完了時）
          ============================================ */}
      {job.status === 'completed' && transcription && (
        <div className="space-y-6">
          {/* 完了ステップ表示 */}
          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <ProgressTracker
              status={job.status}
              progress={100}
            />
          </div>

          {/* 文字起こし結果 */}
          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
              文字起こし結果
            </h2>
            <TranscriptionViewer
              segments={transcription.segments}
              fullText={transcription.full_text}
            />
          </div>

          {/* エクスポートパネル */}
          <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <ExportPanel
              jobId={jobId}
              fileName={job.file_name.replace(/\.[^/.]+$/, '')}
              segments={transcription.segments}
              fullText={transcription.full_text}
            />
          </div>
        </div>
      )}

      {/* ============================================
          完了後、文字起こし結果がまだ読み込まれていない場合
          ============================================ */}
      {job.status === 'completed' && !transcription && (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-gray-200 bg-white py-12 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
          <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            文字起こし結果を読み込み中...
          </p>
        </div>
      )}
    </div>
  );
}
