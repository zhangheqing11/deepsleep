// 极简结构校验：只校验页面真正读取的字段，额外字段放过。
// 不符合时抛 ShapeError，带字段路径；调用方转成 invalid_response。

export class ShapeError extends Error {
  constructor(readonly path: string, detail: string) {
    super(`${path}：${detail}`);
    this.name = 'ShapeError';
  }
}

type Rec = Record<string, unknown>;

export function obj(v: unknown, path: string): Rec {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) throw new ShapeError(path, '应为对象');
  return v as Rec;
}

export function arr(v: unknown, path: string): unknown[] {
  if (!Array.isArray(v)) throw new ShapeError(path, '应为数组');
  return v;
}

export function str(v: unknown, path: string): string {
  if (typeof v !== 'string' || v === '') throw new ShapeError(path, '应为非空字符串');
  return v;
}

export function strOrNull(v: unknown, path: string): string | null {
  if (v === null || v === undefined) return null;
  return str(v, path);
}

export function bool(v: unknown, path: string): boolean {
  if (typeof v !== 'boolean') throw new ShapeError(path, '应为布尔值');
  return v;
}

export function boolOrNull(v: unknown, path: string): boolean | null {
  if (v === null || v === undefined) return null;
  return bool(v, path);
}

export function num(v: unknown, path: string): number {
  if (typeof v !== 'number' || !Number.isFinite(v)) throw new ShapeError(path, '应为数字');
  return v;
}

export function int(v: unknown, path: string, min = 0): number {
  const n = num(v, path);
  if (!Number.isInteger(n) || n < min) throw new ShapeError(path, `应为不小于 ${min} 的整数`);
  return n;
}

/** 缺失或 null → null（显示“暂无”）；有值必须是数字。不把缺失补成 0。 */
export function numOrNull(v: unknown, path: string): number | null {
  if (v === null || v === undefined) return null;
  return num(v, path);
}

/** 0–1 比例；缺失或 null → null。 */
export function ratioOrNull(v: unknown, path: string): number | null {
  const n = numOrNull(v, path);
  if (n !== null && (n < 0 || n > 1)) throw new ShapeError(path, '比例应在 0–1 之间');
  return n;
}

export function oneOf<T extends string>(v: unknown, allowed: readonly T[], path: string): T {
  if (typeof v !== 'string' || !(allowed as readonly string[]).includes(v)) {
    throw new ShapeError(path, `应为 ${allowed.join(' / ')} 之一`);
  }
  return v as T;
}

/** 用于 URL 路径的 ID：不能含斜杠、空白等。与后端草案白名单一致。 */
export function safeId(v: unknown, path: string): string {
  const s = str(v, path);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(s)) throw new ShapeError(path, 'ID 只能含字母、数字、点、下划线和短横线');
  return s;
}

export function safeIdOrNull(v: unknown, path: string): string | null {
  if (v === null || v === undefined) return null;
  return safeId(v, path);
}
