'use client';

/**
 * ジョブ一覧コンポーネント
 * - ジョブのカード表示
 * - ステータスバッジ（色分け）
 * - ページネーション
 * - 削除ボタン（確認ダイアログ付き）
 * - 空の状態表示
 */

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  FileText,
  Trash2,
  Clock,
  HardDrive,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { clsx } from 'clsx';
import { getJobs, deleteJob, formatFileSize, formatDate } from '@/lib/api';
import type { Job, JobStatus, JobListResponse } from '@/types';

/** ステータスバッジの設定マップ */
const STATUS_CONFIG: Record<JobStatus, { label: string; className: string }> = {
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

/** 1ページあたりの表示件数 */
const ITEMS_PER_PAGE = 8;

export default function JobList() {
  const [jobs, setJobs] = useState<JobListResponse | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);

  /** ジョブ一覧を取得する */
  const fetchJobs = useCallback(async (page: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await getJobs(page, ITEMS_PER_PAGE);
      setJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ジョブ一覧の取得に失敗しました');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // 初回読み込みとページ変更時にデータ取得
  useEffect(() => {
    fetchJobs(currentPage);
  }, [currentPage, fetchJobs]);

  /** ジョブの削除処理 */
  const handleDelete = async (jobId: string) => {
    setDeletingJobId(jobId);
    try {
      await deleteJob(jobId);
      // 削除成功後にリストを再取得
      await fetchJobs(currentPage);
      setShowDeleteConfirm(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ジョブの削除に失敗しました');
    } finally {
      setDeletingJobId(null);
    }
  };

  /** ページネーション: 前のページ */
  const goToPreviousPage = () => {
    if (currentPage > 1) setCurrentPage(currentPage - 1);
  };

  /** ページネーション: 次のページ */
  const goToNextPage = () => {
    if (jobs && currentPage < jobs.total_pages) setCurrentPage(currentPage + 1);
  };

  // ローディング状態
  if (isLoading && !jobs) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">ジョブ一覧を読み込み中...</p>
      </div>
    );
  }

  // エラー状態
  if (error && !jobs) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <AlertCircle className="h-8 w-8 text-red-400" />
        <p className="mt-3 text-sm text-red-500">{error}</p>
        <button
          onClick={() => fetchJobs(currentPage)}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-600"
        >
          <RefreshCw className="h-4 w-4" />
          再読み込み
        </button>
      </div>
    );
  }

  // 空の状態
  if (jobs && jobs.jobs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gray-100 dark:bg-gray-800">
          <Inbox className="h-8 w-8 text-gray-400 dark:text-gray-500" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-gray-700 dark:text-gray-300">
          ジョブがありません
        </h3>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          上のアップロードエリアからファイルをアップロードして、文字起こしを開始しましょう。
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            ジョブ一覧
          </h3>
          {jobs && (
            <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
              {jobs.total}件
            </span>
          )}
        </div>
        <button
          onClick={() => fetchJobs(currentPage)}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
        >
          <RefreshCw className={clsx('h-3.5 w-3.5', isLoading && 'animate-spin')} />
          更新
        </button>
      </div>

      {/* ジョブカード一覧 */}
      <div className="grid gap-3">
        {jobs?.jobs.map((job) => (
          <Link
            key={job.id}
            href={`/jobs/${job.id}`}
            className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-all duration-200 hover:border-brand-200 hover:shadow-md dark:border-gray-700 dark:bg-gray-900 dark:hover:border-brand-800"
          >
            <div className="flex items-center gap-4">
              {/* ファイルアイコン */}
              <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-brand-50 transition-colors group-hover:bg-brand-100 dark:bg-brand-950/30 dark:group-hover:bg-brand-950/50">
                <FileText className="h-5 w-5 text-brand-500" />
              </div>

              {/* ジョブ情報 */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-semibold text-gray-900 group-hover:text-brand-600 dark:text-gray-100 dark:group-hover:text-brand-400">
                    {job.file_name}
                  </p>
                  {/* ステータスバッジ */}
                  <span className={clsx('status-badge flex-shrink-0', STATUS_CONFIG[job.status].className)}>
                    {STATUS_CONFIG[job.status].label}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                  <span className="inline-flex items-center gap-1">
                    <HardDrive className="h-3 w-3" />
                    {formatFileSize(job.file_size)}
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatDate(job.created_at)}
                  </span>
                </div>
              </div>

              {/* 削除ボタン */}
              <div className="flex-shrink-0" onClick={(e) => e.preventDefault()}>
                {showDeleteConfirm === job.id ? (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleDelete(job.id)}
                      disabled={deletingJobId === job.id}
                      className="rounded-lg bg-red-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-600 disabled:opacity-50"
                    >
                      {deletingJobId === job.id ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        '削除'
                      )}
                    </button>
                    <button
                      onClick={() => setShowDeleteConfirm(null)}
                      className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                    >
                      取消
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setShowDeleteConfirm(job.id)}
                    className="rounded-lg p-2 text-gray-400 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 dark:hover:bg-red-950/30"
                    title="ジョブを削除"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>

            {/* 進捗バー（処理中の場合のみ表示） */}
            {['uploading', 'extracting', 'transcribing'].includes(job.status) && (
              <div className="mt-3">
                <div className="h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  <div
                    className="progress-bar-animated h-full rounded-full transition-all duration-500"
                    style={{ width: `${job.progress}%` }}
                  />
                </div>
              </div>
            )}
          </Link>
        ))}
      </div>

      {/* ページネーション */}
      {jobs && jobs.total_pages > 1 && (
        <div className="flex items-center justify-between pt-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {jobs.total}件中 {(currentPage - 1) * ITEMS_PER_PAGE + 1}-{Math.min(currentPage * ITEMS_PER_PAGE, jobs.total)}件を表示
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={goToPreviousPage}
              disabled={currentPage <= 1}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-30 dark:text-gray-400 dark:hover:bg-gray-800"
              aria-label="前のページ"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            {/* ページ番号ボタン */}
            {Array.from({ length: jobs.total_pages }, (_, i) => i + 1).map((page) => (
              <button
                key={page}
                onClick={() => setCurrentPage(page)}
                className={clsx(
                  'inline-flex h-8 w-8 items-center justify-center rounded-lg text-sm font-medium transition-colors',
                  page === currentPage
                    ? 'bg-brand-500 text-white'
                    : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
                )}
              >
                {page}
              </button>
            ))}
            <button
              onClick={goToNextPage}
              disabled={!jobs || currentPage >= jobs.total_pages}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 transition-colors hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-30 dark:text-gray-400 dark:hover:bg-gray-800"
              aria-label="次のページ"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
