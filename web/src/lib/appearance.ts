// 外观偏好：只保存在本机浏览器，立即生效。三套界面共用。
import { useSyncExternalStore } from 'react';
import { readJson, writeJson } from './storage';

export type ThemeChoice = 'system' | 'light' | 'dark';
export interface Appearance {
  theme: ThemeChoice;
  font: 'standard' | 'large';
}

const KEY = 'deepsleep.appearance.v1';
const DEFAULT: Appearance = { theme: 'system', font: 'standard' };

function read(): Appearance {
  const saved = readJson<Partial<Appearance>>('local', KEY);
  return {
    theme: saved?.theme === 'light' || saved?.theme === 'dark' ? saved.theme : DEFAULT.theme,
    font: saved?.font === 'large' ? 'large' : DEFAULT.font,
  };
}

let snapshot = read();
const listeners = new Set<() => void>();
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
const get = () => snapshot;

function write(next: Appearance): void {
  writeJson('local', KEY, next);
  snapshot = next;
  listeners.forEach((l) => l());
}

export function useAppearance(): Appearance {
  return useSyncExternalStore(subscribe, get, get);
}

export function setThemeChoice(theme: ThemeChoice): void {
  write({ ...snapshot, theme });
}

export function setFontChoice(font: Appearance['font']): void {
  write({ ...snapshot, font });
}

export function applyAppearance(a: Appearance): void {
  const el = document.documentElement;
  if (a.theme === 'system') delete el.dataset.theme;
  else el.dataset.theme = a.theme;
  if (a.font === 'large') el.dataset.font = 'large';
  else delete el.dataset.font;
}

/** 当前实际显示的是不是深色（“跟随系统”时看系统设置）。 */
export function isDark(a: Appearance): boolean {
  if (a.theme !== 'system') return a.theme === 'dark';
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}
