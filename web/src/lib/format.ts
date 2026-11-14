// 只做展示格式化，不计算任何指标。

export const EMPTY = '暂无';

function trim(n: number, digits: number): string {
  return n.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');
}

/** 0–1 比例 → 百分比；null/undefined 显示“暂无”，绝不显示成 0% */
export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return EMPTY;
  return `${trim(v * 100, digits)}%`;
}

/** 比例差 → 带符号的百分点 */
export function pointDelta(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return EMPTY;
  const p = v * 100;
  const sign = p > 0 ? '+' : p < 0 ? '−' : '±';
  return `${sign}${trim(Math.abs(p), digits)} 个百分点`;
}

export function signed(v: number, digits = 1): string {
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  return `${sign}${trim(Math.abs(v), digits)}`;
}

export function ms(v: number): string {
  if (v < 1000) return `${Math.round(v)} 毫秒`;
  return `${trim(v / 1000, 1)} 秒`;
}

export function seconds(v: number): string {
  return `${trim(v, 1)} 秒`;
}

export function dateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', { hour12: false });
}

export function minutesToHours(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h} 小时 ${m} 分` : `${h} 小时`;
}
