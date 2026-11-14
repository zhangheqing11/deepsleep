// 配置解析（纯函数，可测试）。真正读取 import.meta.env 的只有 src/config.ts。

export type DataMode = 'mock' | 'http' | 'snapshot';

export type ModeSetting =
  | { ok: true; mode: DataMode; explicit: boolean }
  | { ok: false; raw: string };

/** 不填 → mock（页面全程标“模拟数据”）；不认识的值 → 配置错误，不悄悄退回 mock。 */
export function parseDataMode(raw: string | undefined | null): ModeSetting {
  const v = (raw ?? '').trim().toLowerCase();
  if (v === '') return { ok: true, mode: 'mock', explicit: false };
  if (v === 'mock' || v === 'http' || v === 'snapshot') return { ok: true, mode: v, explicit: true };
  return { ok: false, raw: String(raw) };
}

/** 已经实现的数据模式。snapshot（回放包）要等后端导出格式（B4）定了再做。 */
export const IMPLEMENTED_MODES: readonly DataMode[] = ['mock', 'http'];

export function isImplemented(mode: DataMode): boolean {
  return IMPLEMENTED_MODES.includes(mode);
}

/** 正整数毫秒；不填或不合法时用默认值，并给出提示文字供页面显示。 */
export function parseMs(
  name: string,
  raw: string | undefined | null,
  fallback: number,
  min: number,
): { value: number; warning: string | null } {
  if (raw === undefined || raw === null || raw.trim() === '') return { value: fallback, warning: null };
  const n = Number(raw.trim());
  if (!Number.isInteger(n) || n < min) {
    return { value: fallback, warning: `${name}=${raw} 不合法（需为不小于 ${min} 的整数毫秒），已用默认值 ${fallback}` };
  }
  return { value: n, warning: null };
}

/** API 基础地址：去掉末尾斜杠；不填时走同源 /api/v1。 */
export function parseBaseUrl(raw: string | undefined | null): string {
  const v = (raw ?? '').trim();
  return (v || '/api/v1').replace(/\/+$/, '');
}
