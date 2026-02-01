'use client';

/**
 * トップページ
 * - ヒーローセクション（アプリ紹介）
 * - FileUploaderコンポーネント
 * - JobListコンポーネント（過去のジョブ一覧）
 * - 機能紹介セクション（対応形式、精度、大容量対応）
 */

import {
  Zap,
  Shield,
  FileVideo,
  Languages,
  Clock,
  HardDrive,
} from 'lucide-react';
import FileUploader from '@/components/FileUploader';
import JobList from '@/components/JobList';
import SystemInfoPanel from '@/components/SystemInfoPanel';

/** 機能紹介カードのデータ */
const FEATURES = [
  {
    icon: FileVideo,
    title: '多形式対応',
    description:
      'MP4, AVI, MOV, MKV, WebMなどの動画形式と、M4A, MP3, WAV, FLACなどの音声形式に幅広く対応。',
    color: 'from-blue-500 to-blue-600',
    bgColor: 'bg-blue-50 dark:bg-blue-950/20',
    iconColor: 'text-blue-500',
  },
  {
    icon: Zap,
    title: '高精度文字起こし',
    description:
      '最新のAIモデルを使用し、高い精度で音声をテキストに変換。タイムスタンプ付きで出力。',
    color: 'from-purple-500 to-purple-600',
    bgColor: 'bg-purple-50 dark:bg-purple-950/20',
    iconColor: 'text-purple-500',
  },
  {
    icon: HardDrive,
    title: '大容量ファイル対応',
    description:
      '1000MB超のファイルもチャンク分割アップロードで安定的に処理。最大5GBまで対応。',
    color: 'from-green-500 to-green-600',
    bgColor: 'bg-green-50 dark:bg-green-950/20',
    iconColor: 'text-green-500',
  },
  {
    icon: Languages,
    title: '多言語対応',
    description:
      '日本語、英語、中国語、韓国語など複数の言語に対応。自動言語検出機能も搭載。',
    color: 'from-orange-500 to-orange-600',
    bgColor: 'bg-orange-50 dark:bg-orange-950/20',
    iconColor: 'text-orange-500',
  },
  {
    icon: Clock,
    title: 'リアルタイム進捗',
    description:
      'WebSocketによるリアルタイムな進捗表示。処理状況をいつでも確認できます。',
    color: 'from-cyan-500 to-cyan-600',
    bgColor: 'bg-cyan-50 dark:bg-cyan-950/20',
    iconColor: 'text-cyan-500',
  },
  {
    icon: Shield,
    title: '多形式エクスポート',
    description:
      'TXT, SRT, VTT, JSON, TSVの5形式でエクスポート可能。用途に合わせて選択できます。',
    color: 'from-indigo-500 to-indigo-600',
    bgColor: 'bg-indigo-50 dark:bg-indigo-950/20',
    iconColor: 'text-indigo-500',
  },
];

export default function HomePage() {
  return (
    <div className="page-transition space-y-16 pb-12">
      {/* ============================================
          ヒーローセクション
          ============================================ */}
      <section className="relative pt-8 text-center sm:pt-12">
        {/* 背景装飾（ぼかし円） */}
        <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute -left-40 -top-40 h-80 w-80 rounded-full bg-brand-400/10 blur-3xl" />
          <div className="absolute -right-20 top-10 h-60 w-60 rounded-full bg-purple-400/10 blur-3xl" />
        </div>

        <div className="mx-auto max-w-3xl space-y-6">
          {/* バッジ */}
          <div className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-4 py-1.5 text-xs font-semibold text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300">
            <Zap className="h-3.5 w-3.5" />
            AIパワード音声文字起こし
          </div>

          {/* メインタイトル */}
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-5xl lg:text-6xl">
            音声を
            <span className="text-gradient">高精度</span>
            に
            <br className="hidden sm:block" />
            テキスト変換
          </h1>

          {/* サブタイトル */}
          <p className="mx-auto max-w-2xl text-base leading-relaxed text-gray-600 dark:text-gray-400 sm:text-lg">
            1000MB超の大容量動画ファイルにも対応した音声文字起こしサービス。
            <br className="hidden sm:block" />
            ドラッグ&ドロップでファイルをアップロードするだけで、
            AIが高精度にテキストを生成します。
          </p>
        </div>
      </section>

      {/* ============================================
          システム環境情報セクション
          ============================================ */}
      <section>
        <div className="mx-auto max-w-3xl">
          <SystemInfoPanel />
        </div>
      </section>

      {/* ============================================
          ファイルアップロードセクション
          ============================================ */}
      <section>
        <div className="mx-auto max-w-3xl">
          <FileUploader />
        </div>
      </section>

      {/* ============================================
          ジョブ一覧セクション
          ============================================ */}
      <section id="jobs">
        <div className="mx-auto max-w-4xl">
          <JobList />
        </div>
      </section>

      {/* ============================================
          機能紹介セクション
          ============================================ */}
      <section>
        <div className="mx-auto max-w-5xl">
          {/* セクションヘッダー */}
          <div className="mb-10 text-center">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white sm:text-3xl">
              充実の機能
            </h2>
            <p className="mt-3 text-gray-500 dark:text-gray-400">
              ビジネスで求められる品質と機能を提供します
            </p>
          </div>

          {/* 機能カードグリッド */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((feature) => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.title}
                  className="group rounded-2xl border border-gray-200 bg-white p-6 shadow-sm transition-all duration-300 hover:border-gray-300 hover:shadow-md dark:border-gray-800 dark:bg-gray-900 dark:hover:border-gray-700"
                >
                  {/* アイコン */}
                  <div
                    className={`inline-flex h-12 w-12 items-center justify-center rounded-xl ${feature.bgColor} transition-transform duration-300 group-hover:scale-110`}
                  >
                    <Icon className={`h-6 w-6 ${feature.iconColor}`} />
                  </div>

                  {/* テキスト */}
                  <h3 className="mt-4 text-base font-semibold text-gray-900 dark:text-white">
                    {feature.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-gray-500 dark:text-gray-400">
                    {feature.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ============================================
          対応形式一覧セクション
          ============================================ */}
      <section>
        <div className="mx-auto max-w-3xl">
          <div className="rounded-2xl border border-gray-200 bg-gradient-to-br from-gray-50 to-white p-8 dark:border-gray-800 dark:from-gray-900 dark:to-gray-950">
            <h3 className="text-center text-lg font-semibold text-gray-900 dark:text-white">
              対応ファイル形式
            </h3>
            <div className="mt-6 grid grid-cols-2 gap-4">
              {/* 動画形式 */}
              <div>
                <p className="mb-3 text-sm font-medium text-gray-500 dark:text-gray-400">
                  動画形式
                </p>
                <div className="flex flex-wrap gap-2">
                  {['MP4', 'AVI', 'MOV', 'MKV', 'WebM'].map((fmt) => (
                    <span
                      key={fmt}
                      className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700"
                    >
                      .{fmt}
                    </span>
                  ))}
                </div>
              </div>

              {/* 音声形式 */}
              <div>
                <p className="mb-3 text-sm font-medium text-gray-500 dark:text-gray-400">
                  音声形式
                </p>
                <div className="flex flex-wrap gap-2">
                  {['M4A', 'MP3', 'WAV', 'FLAC'].map((fmt) => (
                    <span
                      key={fmt}
                      className="rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-700"
                    >
                      .{fmt}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* ファイルサイズ */}
            <div className="mt-6 text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                最大ファイルサイズ:{' '}
                <span className="font-semibold text-brand-600 dark:text-brand-400">5GB</span>
                {' '}| チャンク分割アップロードで大容量ファイルも安心
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
