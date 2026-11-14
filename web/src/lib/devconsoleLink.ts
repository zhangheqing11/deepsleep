// “进化后台”入口：地址只在 VITE_DEVCONSOLE_URL 一处配置（见 src/config.ts）。
// 解析与探测都是纯逻辑，便于测试。探测读取目标下的 devconsole-meta.json：
// 只有返回的是进化后台的标识文件才算部署好了；拿到 HTML（例如被 SPA 回退到旧控制台首页）算“待部署”。

export type DevconsoleLink =
  | { state: 'unconfigured' }
  | { state: 'invalid'; raw: string; reason: string }
  | { state: 'configured'; href: string };

export const DEVCONSOLE_APP_ID = 'deepsleep-devconsole';
export const DEVCONSOLE_META_FILE = 'devconsole-meta.json';

/**
 * 只接受 http(s) 绝对地址或以单个“/”开头的同源路径。
 * 路径末尾补“/”，保证相对地址（标识文件）解析在进化后台目录下。
 */
export function resolveDevconsoleLink(raw: string | undefined | null, pageHref: string): DevconsoleLink {
  const v = (raw ?? '').trim();
  if (v === '') return { state: 'unconfigured' };
  const isPath = v.startsWith('/') && !v.startsWith('//');
  if (!isPath && !/^https?:\/\//i.test(v)) {
    return { state: 'invalid', raw: v, reason: '只能是 http(s):// 开头的完整地址，或以 / 开头的同源路径' };
  }
  let url: URL;
  try {
    url = new URL(v, pageHref);
  } catch {
    return { state: 'invalid', raw: v, reason: '地址无法解析' };
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return { state: 'invalid', raw: v, reason: '只能是 http 或 https 地址' };
  }
  if (url.username || url.password) return { state: 'invalid', raw: v, reason: '地址里不能带账号密码' };
  if (!url.pathname.endsWith('/')) url.pathname += '/';
  url.hash = '';
  return { state: 'configured', href: url.href };
}

export type ProbeResult = 'ok' | 'not_deployed' | 'unreachable';

export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

/** 读取目标下的标识文件。网络失败（含跨域被拦）→ unreachable；拿到的不是进化后台标识 → not_deployed。 */
export async function probeDevconsole(href: string, fetchImpl: FetchLike, signal?: AbortSignal): Promise<ProbeResult> {
  let res: Response;
  try {
    res = await fetchImpl(new URL(DEVCONSOLE_META_FILE, href).href, {
      method: 'GET',
      cache: 'no-store',
      credentials: 'omit',
      signal,
    });
  } catch {
    return 'unreachable';
  }
  if (!res.ok) return 'not_deployed';
  try {
    const body: unknown = JSON.parse(await res.text());
    return typeof body === 'object' && body !== null && (body as { app?: unknown }).app === DEVCONSOLE_APP_ID
      ? 'ok'
      : 'not_deployed';
  } catch {
    return 'not_deployed';
  }
}
