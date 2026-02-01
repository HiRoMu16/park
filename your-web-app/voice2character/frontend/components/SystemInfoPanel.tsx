'use client';

/**
 * システム情報パネルコンポーネント
 * - サーバーのCPU、RAM、GPU情報を表示
 * - Whisperモデルの推奨設定を表示
 * - 折りたたみ可能なパネル
 */

import { useState, useEffect } from 'react';
import {
  Cpu,
  HardDrive,
  Monitor,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Loader2,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { clsx } from 'clsx';
import { getSystemInfo } from '@/lib/api';
import type { SystemInfo } from '@/types';

export default function SystemInfoPanel() {
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /** システム情報を取得する */
  const fetchSystemInfo = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const info = await getSystemInfo();
      setSystemInfo(info);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'システム情報の取得に失敗しました';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSystemInfo();
  }, []);

  return (
    <div className="rounded-2xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      {/* ヘッダー（クリックで折りたたみ切替） */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center justify-between px-6 py-4 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
      >
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 dark:bg-indigo-950/30">
            <Monitor className="h-5 w-5 text-indigo-500" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              サーバー環境情報
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              PC環境に合わせた最適な設定を確認できます
            </p>
          </div>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-5 w-5 text-gray-400" />
        ) : (
          <ChevronDown className="h-5 w-5 text-gray-400" />
        )}
      </button>

      {/* 展開時のコンテンツ */}
      {isExpanded && (
        <div className="border-t border-gray-100 px-6 pb-6 pt-4 dark:border-gray-800">
          {/* ローディング */}
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-8 text-gray-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm">システム情報を取得中...</span>
            </div>
          )}

          {/* エラー */}
          {error && !isLoading && (
            <div className="flex flex-col items-center gap-3 py-6">
              <div className="flex items-center gap-2 text-red-500">
                <AlertCircle className="h-5 w-5" />
                <span className="text-sm">{error}</span>
              </div>
              <button
                onClick={fetchSystemInfo}
                className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 dark:border-gray-600 dark:text-gray-400 dark:hover:bg-gray-800"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                再取得
              </button>
            </div>
          )}

          {/* システム情報の表示 */}
          {systemInfo && !isLoading && (
            <div className="space-y-4">
              {/* ハードウェア情報カード */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {/* CPU */}
                <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
                  <div className="mb-2 flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-blue-500" />
                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      CPU
                    </span>
                  </div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {systemInfo.cpu.model || '不明'}
                  </p>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {systemInfo.cpu.physical_cores}コア / {systemInfo.cpu.logical_cores}スレッド
                    {systemInfo.cpu.frequency_mhz && (
                      <> / {systemInfo.cpu.frequency_mhz}MHz</>
                    )}
                  </p>
                </div>

                {/* RAM */}
                <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
                  <div className="mb-2 flex items-center gap-2">
                    <HardDrive className="h-4 w-4 text-green-500" />
                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      RAM
                    </span>
                  </div>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {systemInfo.ram.total_gb} GB
                  </p>
                  <div className="mt-2 space-y-1">
                    <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
                      <span>使用率 {systemInfo.ram.used_percent}%</span>
                      <span>空き {systemInfo.ram.available_gb} GB</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                      <div
                        className={clsx(
                          'h-full rounded-full transition-all',
                          systemInfo.ram.used_percent > 90
                            ? 'bg-red-500'
                            : systemInfo.ram.used_percent > 70
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                        )}
                        style={{ width: `${systemInfo.ram.used_percent}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* GPU */}
                <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
                  <div className="mb-2 flex items-center gap-2">
                    <Monitor className="h-4 w-4 text-purple-500" />
                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                      GPU
                    </span>
                  </div>
                  {systemInfo.gpu ? (
                    <>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {systemInfo.gpu.name}
                      </p>
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        VRAM {systemInfo.gpu.vram_total_gb} GB / CUDA {systemInfo.gpu.cuda_version}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-sm font-medium text-gray-400 dark:text-gray-500">
                        検出されませんでした
                      </p>
                      <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                        CUDA対応GPUが必要です
                      </p>
                    </>
                  )}
                </div>
              </div>

              {/* 推奨設定 */}
              <div className="rounded-xl border border-brand-200 bg-gradient-to-r from-brand-50 to-indigo-50 p-4 dark:border-brand-800 dark:from-brand-950/20 dark:to-indigo-950/20">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-brand-100 dark:bg-brand-900/50">
                    <Sparkles className="h-4 w-4 text-brand-600 dark:text-brand-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      推奨設定
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center rounded-md bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
                        モデル: {systemInfo.recommendation.model}
                      </span>
                      <span className="inline-flex items-center rounded-md bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300">
                        デバイス: {systemInfo.recommendation.device === 'cuda' ? 'GPU' : 'CPU'}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
                      {systemInfo.recommendation.reason}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
