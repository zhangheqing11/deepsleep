// 数据模式标识：不填 = mock；不认识的值是配置错误，不会悄悄退回 mock；snapshot 尚未实现，明确不可用。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadModules } from './support/load.mjs';

const m = await loadModules();

test('数据模式解析', () => {
  assert.deepEqual(m.parseDataMode(undefined), { ok: true, mode: 'mock', explicit: false });
  assert.deepEqual(m.parseDataMode(' HTTP '), { ok: true, mode: 'http', explicit: true });
  assert.deepEqual(m.parseDataMode('snapshot'), { ok: true, mode: 'snapshot', explicit: true });
  assert.deepEqual(m.parseDataMode('live'), { ok: false, raw: 'live' });
  assert.equal(m.isImplemented('snapshot'), false);
  assert.equal(m.isImplemented('http'), true);
});

test('轮询参数：不合法时用默认值并给出提示', () => {
  assert.deepEqual(m.parseMs('X', undefined, 2000, 500), { value: 2000, warning: null });
  assert.deepEqual(m.parseMs('X', '1500', 2000, 500), { value: 1500, warning: null });
  assert.equal(m.parseMs('X', '100', 2000, 500).value, 2000);
  assert.match(m.parseMs('X', 'abc', 2000, 500).warning, /不合法/);
});

test('接口地址：去掉末尾斜杠，默认 /api/v1', () => {
  assert.equal(m.parseBaseUrl(undefined), '/api/v1');
  assert.equal(m.parseBaseUrl('http://10.0.0.2:8000/api/v1/'), 'http://10.0.0.2:8000/api/v1');
});

for (const [raw, expected] of [
  ['snapshot', 'unavailable'],
  ['bogus', 'config_error'],
  ['http', 'ready'],
  ['', 'ready'],
]) {
  test(`按配置建立数据源：VITE_DATA_MODE=${raw || '（不填）'} → ${expected}`, async () => {
    const mod = await loadModules({ VITE_DATA_MODE: raw });
    const s = mod.setupSource('');
    assert.equal(s.state, expected);
    if (s.state === 'ready') assert.equal(s.client.mode, raw === 'http' ? 'http' : 'mock');
  });
}
