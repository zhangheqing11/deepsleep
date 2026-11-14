// deepsleep 离线静态外壳；只在生产构建注册，见 src/main.tsx。
// CacheStorage 在同源应用间共享：读写和清理必须同时限定应用与注册 scope。
// 每次发布前更新 VERSION。仅安装时预缓存固定 HTML；导航响应永不写入缓存。
const VERSION = 'v2';
const SCOPE = new URL(self.registration.scope);
const CACHE_PREFIX = `deepsleep-web:${SCOPE.href}:`;
const CACHE_NAME = `${CACHE_PREFIX}${VERSION}`;
const HOME = new URL('index.html', SCOPE).href;
const STATIC_FILES = new Map([
  ['manifest.webmanifest', ['application/manifest+json', 'application/json']],
  ['icons/icon-192.png', ['image/png']],
  ['icons/icon-512.png', ['image/png']],
  ['icons/icon-maskable-512.png', ['image/png']],
  ['icons/apple-touch-icon.png', ['image/png']],
  ['icons/icon.svg', ['image/svg+xml']],
]);

function cacheable(response, contentTypes) {
  const mime = response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase();
  const policy = response.headers.get('Cache-Control') || '';
  return response.status === 200 && response.type === 'basic' && !response.redirected
    && !/(?:^|,)\s*(?:no-store|private)\b/i.test(policy) && contentTypes.includes(mime);
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const files = [[HOME, ['text/html']], ...Array.from(STATIC_FILES, ([path, types]) => [new URL(path, SCOPE).href, types])];
    // 全部验证通过后再写缓存；拒绝错误页、跳转登录页和不匹配的资源类型。
    const responses = await Promise.all(files.map(async ([url, types]) => {
      const response = await fetch(new Request(url, { cache: 'reload' }));
      if (!cacheable(response, types)) throw new Error('Invalid static shell response');
      return [url, response];
    }));
    const cache = await caches.open(CACHE_NAME);
    await Promise.all(responses.map(([url, response]) => cache.put(url, response)));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME).map((key) => caches.delete(key)));
    // 旧版 deepsleep-v1 没有 scope 信息，不猜测归属，不读取或自动删除。
    await self.clients.claim();
  })());
});

async function readCached(key) {
  try {
    const cache = await caches.open(CACHE_NAME);
    return await cache.match(key);
  } catch {
    return undefined;
  }
}

async function navigate(request) {
  try {
    // HTTP 4xx/5xx 也原样返回；只有网络失败才读取安装时的静态首页。
    // 不缓存导航结果，避免错误页或个性化 HTML 覆盖离线外壳。
    return await fetch(request);
  } catch {
    return (await readCached(HOME)) || new Response(null, { status: 503, statusText: 'Service Unavailable' });
  }
}

async function staticResource(request, types) {
  const hit = await readCached(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (cacheable(response, types)) {
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    } catch {
      // 离线缓存是可选能力：配额满或禁用缓存不能吞掉正常网络响应。
    }
  }
  return response;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== SCOPE.origin || !url.pathname.startsWith(SCOPE.pathname)) return;
  if (url.search || request.headers.has('Authorization') || request.headers.has('Range') || request.cache === 'no-store') return;
  const path = url.pathname.slice(SCOPE.pathname.length);

  if (request.mode === 'navigate') {
    // 路由使用 hash；只负责自己的入口，其余页面、API 和同源应用不接管。
    if (path === '' || path === 'index.html') event.respondWith(navigate(request));
    return;
  }

  let types = STATIC_FILES.get(path);
  // Vite 的带内容哈希 JS/CSS。未知 GET（包括 JSON / API）一律不缓存。
  if (/^assets\/[^/]+-[A-Za-z0-9_-]{8,}\.js$/.test(path)) types = ['text/javascript', 'application/javascript'];
  if (/^assets\/[^/]+-[A-Za-z0-9_-]{8,}\.css$/.test(path)) types = ['text/css'];
  if (types) event.respondWith(staticResource(request, types));
});
