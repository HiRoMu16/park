'use client';

/**
 * ダークモードコンテキスト
 * アプリケーション全体でダークモードの状態を共有するためのコンテキストとフック
 */

import { createContext, useContext } from 'react';

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
