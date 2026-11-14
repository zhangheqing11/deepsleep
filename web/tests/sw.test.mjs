import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

// Runs the actual worker with an in-memory CacheStorage and controlled network.
// No browser, network, package installation or application API is used.
const source = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');
const SCOPE = 'https://example.test/deepsleep/';
const PREFIX = `deepsleep-web:${SCOPE}:`;
const HOME = new URL('index.html', SCOPE).href;
const ASSET = new URL('assets/index-Abcd1234.js', SCOPE).href;

function response(body, options = {}) {
  const make = () => {
    const r = new Response(body, { status: options.status ?? 200, headers: { 'Content-Type': options.mime ?? 'text/javascript', ...options.headers } });
    Object.defineProperties(r, {
      type: { value: options.type ?? 'basic' },
      redirected: { value: options.redirected ?? false },
      clone: { value: make },
    });
    return r;
  };
  return make();
}

function harness() {
  const stores = new Map();
  const listeners = new Map();
  const network = new Map();
  const state = { offline: false, readError: false, writeError: false, skipped: false, claimed: false };
  const fetched = [];
  const urlOf = (key) => new URL(typeof key === 'string' ? key : key.url, SCOPE).href;
  const fetch = async (req) => {
    const url = urlOf(req);
    fetched.push(url);
    if (state.offline) throw new TypeError('offline');
    if (network.has(url)) return network.get(url).clone();
    const path = new URL(url).pathname;
    const mime = path.endsWith('.html') || path.endsWith('/') ? 'text/html'
      : path.endsWith('.webmanifest') ? 'application/manifest+json'
      : path.endsWith('.svg') ? 'image/svg+xml'
      : path.endsWith('.png') ? 'image/png'
      : path.endsWith('.css') ? 'text/css' : 'text/javascript';
    return response(path.endsWith('.html') ? '<html>installed shell</html>' : 'asset', { mime });
  };
  const open = async (name) => {
    if (state.readError) throw new Error('CacheStorage unavailable');
    if (!stores.has(name)) stores.set(name, new Map());
    const entries = stores.get(name);
    const cache = {
      match: async (key) => entries.get(urlOf(key))?.clone(),
      put: async (key, value) => {
        if (state.writeError) throw new DOMException('full', 'QuotaExceededError');
        entries.set(urlOf(key), value.clone());
      },
      addAll: async (keys) => {
        for (const key of keys) {
          const r = await fetch(key);
          if (!r.ok) throw new Error('bad precache response');
          await cache.put(key, r);
        }
      },
    };
    return cache;
  };
  const caches = {
    open, keys: async () => [...stores.keys()], delete: async (name) => stores.delete(name),
    match: async (key) => {
      for (const store of stores.values()) if (store.has(urlOf(key))) return store.get(urlOf(key)).clone();
      return undefined;
    },
  };
  const self = {
    location: new URL('sw.js', SCOPE), registration: { scope: SCOPE },
    addEventListener: (name, callback) => listeners.set(name, callback),
    skipWaiting: async () => { state.skipped = true; },
    clients: { claim: async () => { state.claimed = true; } },
  };
  vm.runInNewContext(source, { self, caches, fetch, URL, Request, Response, Headers, Promise, console });
  async function lifecycle(name) {
    const waits = [];
    listeners.get(name)({ waitUntil: (p) => waits.push(p) });
    await Promise.all(waits);
  }
  async function request(path, options = {}) {
    let output;
    const waits = [];
    listeners.get('fetch')({
      request: { url: new URL(path, SCOPE).href, method: options.method ?? 'GET', mode: options.mode ?? 'cors', headers: new Headers(options.headers) },
      respondWith: (p) => { output = Promise.resolve(p); },
      waitUntil: (p) => waits.push(p),
    });
    const handled = output !== undefined;
    const result = await output;
    await Promise.all(waits);
    return { handled, result };
  }
  return { stores, network, state, fetched, open, lifecycle, request };
}

test('activation deletes only old caches owned by this app at this scope', async () => {
  const h = harness();
  for (const key of [`${PREFIX}v1`, 'other-app-v7', 'deepsleep-web:https://example.test/other/:v1', 'deepsleep-v1']) await h.open(key);
  await h.lifecycle('install');
  await h.lifecycle('activate');
  assert.equal(h.stores.has(`${PREFIX}v1`), false);
  for (const key of ['other-app-v7', 'deepsleep-web:https://example.test/other/:v1', 'deepsleep-v1']) assert.equal(h.stores.has(key), true, key);
  assert.equal(h.state.claimed, true);
});

test('a scoped hashed asset is cached and can be read offline', async () => {
  const h = harness();
  const first = await h.request(ASSET);
  assert.equal(await first.result.text(), 'asset');
  h.state.offline = true;
  assert.equal(await (await h.request(ASSET)).result.text(), 'asset');
  assert.deepEqual(h.fetched, [ASSET]);
});

for (const [path, options] of [
  ['api/v1/runs', {}], ['/api/v1/health', {}], ['users', {}], ['profile.json', {}],
  ['assets/profile.json', {}], ['assets/index.js', {}], ['assets/index-Abcd1234.js?token=private', {}],
  ['/other/assets/index-Abcd1234.js', {}], ['https://elsewhere.test/index.js', {}],
  ['assets/index-Abcd1234.js', { method: 'POST' }],
  ['assets/index-Abcd1234.js', { headers: { Authorization: 'Bearer test' } }],
  ['account', { mode: 'navigate' }], ['?token=private', { mode: 'navigate' }],
]) {
  test(`does not intercept ${options.method ?? 'GET'} ${path} ${options.headers ? 'with authorization' : ''}`, async () => {
    const h = harness();
    assert.equal((await h.request(path, options)).handled, false);
    assert.equal(h.fetched.length, 0);
    assert.equal(h.stores.size, 0);
  });
}

for (const [label, options] of [
  ['500', { status: 500 }], ['redirect', { redirected: true }], ['HTML fallback', { mime: 'text/html' }],
  ['private', { headers: { 'Cache-Control': 'private, max-age=60' } }],
  ['no-store', { headers: { 'Cache-Control': 'no-store' } }],
]) {
  test(`does not cache an asset response that is ${label}`, async () => {
    const h = harness();
    h.network.set(ASSET, response(label, options));
    const first = await h.request(ASSET);
    assert.equal(await first.result.text(), label);
    for (const entries of h.stores.values()) assert.equal(entries.has(ASSET), false);
  });
}

test('HTTP error navigation is returned and never poisons the offline shell', async () => {
  const h = harness();
  await h.lifecycle('install');
  h.network.set(SCOPE, response('gateway error', { status: 500, mime: 'text/html' }));
  assert.equal((await h.request(SCOPE, { mode: 'navigate' })).result.status, 500);
  h.state.offline = true;
  assert.equal(await (await h.request(SCOPE, { mode: 'navigate' })).result.text(), '<html>installed shell</html>');
});

test('successful navigation also never writes a runtime page to the offline shell', async () => {
  const h = harness();
  await h.lifecycle('install');
  h.network.set(SCOPE, response('personalized page', { mime: 'text/html' }));
  assert.equal(await (await h.request(SCOPE, { mode: 'navigate' })).result.text(), 'personalized page');
  h.state.offline = true;
  assert.equal(await (await h.request('index.html', { mode: 'navigate' })).result.text(), '<html>installed shell</html>');
});

test('offline fallback never reads another cache and returns an explicit 503 without a shell', async () => {
  const h = harness();
  const other = await h.open('other-app-v7');
  await other.put(SCOPE, response('other app', { mime: 'text/html' }));
  await other.put(HOME, response('other app', { mime: 'text/html' }));
  h.state.offline = true;
  const { result } = await h.request(SCOPE, { mode: 'navigate' });
  assert.equal(result.status, 503);
  assert.notEqual(await result.text(), 'other app');
});

test('a bad precache entry prevents installation from activating', async () => {
  const h = harness();
  h.network.set(HOME, response('login redirect', { mime: 'text/html', redirected: true }));
  await assert.rejects(h.lifecycle('install'));
  assert.equal(h.state.skipped, false);
});

for (const failure of ['readError', 'writeError']) {
  test(`cache ${failure} does not discard a working network response`, async () => {
    const h = harness();
    h.state[failure] = true;
    assert.equal(await (await h.request(ASSET)).result.text(), 'asset');
  });
}
