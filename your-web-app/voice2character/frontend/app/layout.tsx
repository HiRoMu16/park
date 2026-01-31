'use client';

/**
 * ルートレイアウト
 * アプリケーション全体の共通レイアウトを定義する
 * - Noto Sans JPフォントの読み込み
 * - ダークモードのトグル機能（localStorageベース）
 * - Headerコンポーネントの配置
 */

import { useEffect, useState, createContext, useContext, useCallback } from 'react';
import Header from '@/components/Header';
import './globals.css';

/** ダークモードコンテキストの型 */
interface DarkModeContextType {
  isDark: boolean;
  toggleDarkMode: () => void;
}

/** ダークモードコンテキスト */
export const DarkModeContext = createContext<DarkModeContextType>({
  isDark: false,
  toggleDarkMode: () => {},
});

/** ダークモードコンテキストを使用するカスタムフック */
export function useDarkMode(): DarkModeContextType {
  return useContext(DarkModeContext);
}

/** メタデータ（クライアントコンポーネントのため手動で設定） */
const APP_TITLE = 'VoiceScribe - 高精度音声文字起こし';
const APP_DESCRIPTION =
  '1000MB超の大容量動画にも対応した高精度音声文字起こしサービス。MP4, AVI, MOV, MKV, WebM, M4A, MP3, WAV, FLAC形式をサポート。';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isDark, setIsDark] = useState(false);
  const [mounted, setMounted] = useState(false);

  // 初期化: localStorageとシステム設定からダークモードの状態を復元
  useEffect(() => {
    const stored = localStorage.getItem('voicescribe-dark-mode');
    if (stored !== null) {
      setIsDark(stored === 'true');
    } else {
      // システムのカラースキーム設定に従う
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      setIsDark(prefersDark);
    }
    setMounted(true);
  }, []);

  // ダークモードのクラス切り替え
  useEffect(() => {
    if (mounted) {
      document.documentElement.classList.toggle('dark', isDark);
    }
  }, [isDark, mounted]);

  /** ダークモードのトグル関数 */
  const toggleDarkMode = useCallback(() => {
    setIsDark((prev) => {
      const next = !prev;
      localStorage.setItem('voicescribe-dark-mode', String(next));
      return next;
    });
  }, []);

  return (
    <html lang="ja" suppressHydrationWarning>
      <head>
        {/* Google Fonts: Noto Sans JP */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
        {/* メタデータ */}
        <title>{APP_TITLE}</title>
        <meta name="description" content={APP_DESCRIPTION} />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta charSet="utf-8" />
        <link rel="icon" href="/favicon.ico" />
      </head>
      <body
        className={`
          min-h-screen font-sans antialiased
          transition-colors duration-300
          ${mounted ? '' : 'opacity-0'}
        `}
      >
        <DarkModeContext.Provider value={{ isDark, toggleDarkMode }}>
          {/* ヘッダー */}
          <Header />

          {/* メインコンテンツエリア */}
          <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {children}
          </main>

          {/* フッター */}
          <footer className="border-t border-gray-200 dark:border-gray-800 mt-auto">
            <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
              <div className="text-center text-sm text-gray-500 dark:text-gray-400">
                <p>&copy; {new Date().getFullYear()} VoiceScribe. All rights reserved.</p>
                <p className="mt-1">高精度音声文字起こしサービス</p>
              </div>
            </div>
          </footer>
        </DarkModeContext.Provider>
      </body>
    </html>
  );
}
