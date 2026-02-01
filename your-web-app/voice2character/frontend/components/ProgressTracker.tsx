'use client';

/**
 * 進捗表示コンポーネント
 * - ステップインジケーター（アップロード -> 音声抽出 -> 文字起こし -> 完了）
 * - 円形プログレスバー
 * - 現在のステップの説明テキスト
 * - 推定残り時間
 * - アニメーション付きステップ遷移
 */

import { Upload, AudioLines, FileText, CheckCircle2, AlertCircle, Timer } from 'lucide-react';
import { clsx } from 'clsx';
import type { JobStatus } from '@/types';

/** 処理ステップの定義 */
interface ProcessStep {
  id: JobStatus | 'completed_step';
  label: string;
  description: string;
  icon: React.ElementType;
}

/** 処理ステップ一覧 */
const STEPS: ProcessStep[] = [
  {
    id: 'uploading',
    label: 'アップロード',
    description: 'ファイルをサーバーにアップロードしています...',
    icon: Upload,
  },
  {
    id: 'extracting',
    label: '音声抽出',
    description: '動画ファイルから音声データを抽出しています...',
    icon: AudioLines,
  },
  {
    id: 'transcribing',
    label: '文字起こし',
    description: 'AIが音声を解析して文字に変換しています...',
    icon: FileText,
  },
  {
    id: 'completed_step',
    label: '完了',
    description: '文字起こしが完了しました！',
    icon: CheckCircle2,
  },
];

/** ステータスからステップインデックスを取得 */
function getStepIndex(status: JobStatus): number {
  switch (status) {
    case 'uploading': return 0;
    case 'queued': return 0; // キュー待ちはアップロード完了後
    case 'extracting': return 1;
    case 'transcribing': return 2;
    case 'completed': return 3;
    case 'failed': return -1;
    default: return 0;
  }
}

/** コンポーネントのプロパティ */
interface ProgressTrackerProps {
  /** 現在のジョブステータス */
  status: JobStatus;
  /** 進捗率（0-100） */
  progress: number;
  /** 推定残り時間（秒、オプション） */
  estimatedTime?: number;
  /** サーバーからのステータスメッセージ（オプション） */
  statusMessage?: string;
  /** エラーメッセージ（オプション） */
  errorMessage?: string | null;
}

export default function ProgressTracker({
  status,
  progress,
  estimatedTime,
  statusMessage,
  errorMessage,
}: ProgressTrackerProps) {
  const currentStepIndex = getStepIndex(status);

  /** 円形プログレスバーの計算 */
  const radius = 58;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (progress / 100) * circumference;

  /** 残り時間のフォーマット */
  const formatEstimatedTime = (seconds?: number): string => {
    if (!seconds || seconds <= 0) return '';
    if (seconds < 60) return `残り約${Math.ceil(seconds)}秒`;
    if (seconds < 3600) {
      const mins = Math.floor(seconds / 60);
      const secs = Math.ceil(seconds % 60);
      return secs > 0 ? `残り約${mins}分${secs}秒` : `残り約${mins}分`;
    }
    return `残り約${Math.floor(seconds / 3600)}時間${Math.ceil((seconds % 3600) / 60)}分`;
  };

  /** ステータスに応じたプログレスカラーを取得 */
  const getProgressColor = (): string => {
    if (status === 'failed') return 'stroke-red-500';
    if (status === 'completed') return 'stroke-green-500';
    return 'stroke-brand-500';
  };

  /** 表示するステップ説明（サーバーメッセージがあればそちらを優先） */
  const getStepDescription = (): string => {
    if (statusMessage) return statusMessage;
    if (currentStepIndex >= 0 && currentStepIndex < STEPS.length) {
      return STEPS[currentStepIndex].description;
    }
    return 'キュー待ちです。まもなく処理が開始されます...';
  };

  const etaText = formatEstimatedTime(estimatedTime);

  return (
    <div className="space-y-8">
      {/* 円形プログレスバー */}
      <div className="flex flex-col items-center">
        <div className="relative">
          <svg
            className="circular-progress h-36 w-36"
            viewBox="0 0 128 128"
          >
            {/* 背景トラック */}
            <circle
              className="circular-progress-track"
              cx="64"
              cy="64"
              r={radius}
              fill="none"
              strokeWidth="8"
            />
            {/* 進捗インジケーター */}
            <circle
              className={clsx('circular-progress-fill transition-all duration-1000 ease-out', getProgressColor())}
              cx="64"
              cy="64"
              r={radius}
              fill="none"
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
            />
          </svg>
          {/* パーセント表示 */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">
              {Math.round(progress)}%
            </span>
          </div>
        </div>

        {/* 残り時間表示（円形バーの下） */}
        {etaText && status === 'transcribing' && (
          <div className="mt-3 flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 dark:bg-brand-950/30">
            <Timer className="h-3.5 w-3.5 text-brand-500" />
            <span className="text-xs font-medium text-brand-600 dark:text-brand-400">
              {etaText}
            </span>
          </div>
        )}
      </div>

      {/* ステップインジケーター */}
      <div className="relative">
        {/* 接続線 */}
        <div className="absolute left-0 right-0 top-5 hidden h-0.5 bg-gray-200 dark:bg-gray-700 sm:block" />
        <div
          className="absolute left-0 top-5 hidden h-0.5 bg-brand-500 transition-all duration-700 ease-out sm:block"
          style={{
            width: status === 'failed' ? '0%' : `${Math.min((currentStepIndex / (STEPS.length - 1)) * 100, 100)}%`,
          }}
        />

        {/* ステップ一覧 */}
        <div className="relative flex flex-col gap-4 sm:flex-row sm:justify-between">
          {STEPS.map((step, index) => {
            const isCompleted = currentStepIndex > index;
            const isCurrent = currentStepIndex === index;
            const isFailed = status === 'failed' && currentStepIndex === -1;
            const StepIcon = step.icon;

            return (
              <div
                key={step.id}
                className={clsx(
                  'flex items-center gap-3 sm:flex-col sm:items-center sm:gap-2',
                  'transition-all duration-500'
                )}
              >
                {/* ステップアイコン */}
                <div
                  className={clsx(
                    'relative z-10 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full border-2 transition-all duration-500',
                    isCompleted
                      ? 'border-brand-500 bg-brand-500 text-white'
                      : isCurrent
                        ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-950/50 dark:text-brand-400'
                        : isFailed
                          ? 'border-red-300 bg-red-50 text-red-500 dark:border-red-700 dark:bg-red-950/30 dark:text-red-400'
                          : 'border-gray-300 bg-white text-gray-400 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-500'
                  )}
                >
                  {isCompleted ? (
                    <CheckCircle2 className="h-5 w-5" />
                  ) : (
                    <StepIcon className={clsx('h-5 w-5', isCurrent && 'animate-pulse-slow')} />
                  )}
                  {/* 現在のステップのパルスエフェクト */}
                  {isCurrent && !isFailed && (
                    <span className="absolute inset-0 animate-ripple rounded-full border-2 border-brand-400 opacity-75" />
                  )}
                </div>

                {/* ステップラベル */}
                <div className="sm:text-center">
                  <p
                    className={clsx(
                      'text-sm font-medium transition-colors duration-300',
                      isCompleted || isCurrent
                        ? 'text-gray-900 dark:text-white'
                        : 'text-gray-400 dark:text-gray-500'
                    )}
                  >
                    {step.label}
                  </p>
                  {isCurrent && !isFailed && (
                    <p className="mt-0.5 text-xs text-brand-500 dark:text-brand-400 sm:hidden">
                      {step.description}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 現在のステップの説明（デスクトップ） */}
      {status !== 'completed' && status !== 'failed' && (
        <div className="hidden text-center sm:block">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {getStepDescription()}
          </p>
        </div>
      )}

      {/* キュー待ち表示 */}
      {status === 'queued' && (
        <div className="rounded-xl bg-yellow-50 p-4 text-center dark:bg-yellow-950/20">
          <p className="text-sm font-medium text-yellow-700 dark:text-yellow-400">
            処理キューで待機中です。まもなく処理が開始されます。
          </p>
        </div>
      )}

      {/* エラー表示 */}
      {status === 'failed' && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950/20">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
            <div>
              <p className="font-medium text-red-700 dark:text-red-400">
                処理中にエラーが発生しました
              </p>
              {errorMessage && (
                <p className="mt-1 text-sm text-red-600 dark:text-red-300">
                  {errorMessage}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 完了表示 */}
      {status === 'completed' && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-center dark:border-green-800 dark:bg-green-950/20">
          <CheckCircle2 className="mx-auto h-6 w-6 text-green-500" />
          <p className="mt-2 font-medium text-green-700 dark:text-green-400">
            文字起こしが完了しました！
          </p>
        </div>
      )}
    </div>
  );
}
