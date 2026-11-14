// 串行轮询：不堆积请求、单次超时、取消、退避、断连标记、终态停止。用可推进的假计时器重放。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { FakeTimers, flush, loadModules } from './support/load.mjs';

const { SerialPoller, ApiError, backoffFor } = await loadModules();

function setup(fetchImpl, extra = {}) {
  const timers = new FakeTimers();
  const snaps = [];
  const poller = new SerialPoller({
    fetch: fetchImpl,
    intervalMs: 1000,
    timeoutMs: 5000,
    backoffMs: [2000, 4000, 8000],
    staleAfter: 3,
    onUpdate: (s) => snaps.push(s),
    timers,
    now: () => timers.now,
    ...extra,
  });
  return { timers, snaps, poller, last: () => snaps.at(-1) };
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => {
    resolve = a;
    reject = b;
  });
  return { promise, resolve, reject };
}

test('上一个请求没结束不会发下一个，结束后才按间隔安排', async () => {
  const calls = [];
  const { timers, poller } = setup((signal) => {
    const d = deferred();
    calls.push({ d, signal });
    return d.promise;
  });
  poller.start();
  poller.start();
  await timers.advance(4000);
  assert.equal(calls.length, 1, '慢请求期间不发新请求');
  calls[0].d.resolve({ n: 1 });
  await flush();
  assert.deepEqual(timers.pending().filter((x) => x === 1000), [1000]);
  await timers.advance(1000);
  assert.equal(calls.length, 2);
});

test('单次超时：中止请求，记为网络失败，按退避重试', async () => {
  const signals = [];
  const { timers, poller, last } = setup((signal) => {
    signals.push(signal);
    return new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
  });
  poller.start();
  await timers.advance(5000);
  assert.equal(signals[0].aborted, true);
  assert.equal(last().error.kind, 'network');
  assert.match(last().error.message, /5000 毫秒/);
  assert.equal(last().failures, 1);
  await timers.advance(1999);
  assert.equal(signals.length, 1, '退避 2 秒内不重试');
  await timers.advance(1);
  assert.equal(signals.length, 2);
});

test('连续失败 3 次标为断连 / 过期，保留上次数据；恢复后清除', async () => {
  let fail = false;
  let n = 0;
  const { timers, poller, last } = setup(async () => {
    n += 1;
    if (fail) throw new ApiError({ kind: 'network', message: 'down' });
    return { n };
  });
  poller.start();
  await flush();
  assert.deepEqual(last().data, { n: 1 });
  const okAt = last().lastSuccessAt;
  fail = true;
  await timers.advance(1000);
  assert.equal(last().stale, false);
  await timers.advance(2000);
  await timers.advance(4000);
  assert.equal(last().failures, 3);
  assert.equal(last().stale, true);
  assert.deepEqual(last().data, { n: 1 }, '断连时保留最后一次成功的数据');
  assert.equal(last().lastSuccessAt, okAt);
  fail = false;
  await timers.advance(8000);
  assert.equal(last().stale, false);
  assert.equal(last().failures, 0);
});

test('到终态停止，不再安排请求', async () => {
  let n = 0;
  const { timers, poller, last } = setup(async () => ({ status: ++n >= 2 ? 'succeeded' : 'running' }), {
    isTerminal: (d) => d.status === 'succeeded',
  });
  poller.start();
  await timers.advance(1000);
  assert.equal(last().done, true);
  await timers.advance(60000);
  assert.equal(n, 2);
});

test('shouldStop：不该重试的错误（如 404）停止', async () => {
  let n = 0;
  const { timers, poller, last } = setup(
    async () => {
      n += 1;
      throw new ApiError({ kind: 'http', status: 404, code: 'RUN_NOT_FOUND', message: '' });
    },
    { shouldStop: (e) => e.status === 404 },
  );
  poller.start();
  await timers.advance(60000);
  assert.equal(n, 1);
  assert.equal(last().done, true);
});

test('retryDelay：报告未就绪按自定义间隔重试', async () => {
  let n = 0;
  const { timers, poller } = setup(
    async () => {
      n += 1;
      throw new ApiError({ kind: 'http', status: 409, code: 'REPORT_NOT_READY', message: '' });
    },
    { retryDelay: (e) => (e.code === 'REPORT_NOT_READY' ? 500 : null) },
  );
  poller.start();
  await flush();
  await timers.advance(500);
  assert.equal(n, 2);
});

test('stop：取消在途请求，之后不再回调也不再请求', async () => {
  const signals = [];
  const { timers, poller, snaps } = setup((signal) => {
    signals.push(signal);
    return new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
  });
  poller.start();
  await flush();
  const count = snaps.length;
  poller.stop();
  await flush();
  assert.equal(signals[0].aborted, true);
  await timers.advance(60000);
  assert.equal(signals.length, 1);
  assert.equal(snaps.length, count, '停止后不再回调');
});

test('退避序列重复最后一个值', () => {
  assert.deepEqual([1, 2, 3, 4, 9].map((f) => backoffFor([2000, 4000, 8000], f)), [2000, 4000, 8000, 8000, 8000]);
});
