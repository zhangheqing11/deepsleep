// mock 模式：指标只来自正式示例；开发样例都带 _dev_sample 标记；数据静态，不随时间“增长”。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { example, loadModules } from './support/load.mjs';

const { createMockClient, fixtureData, parseFixtureName, FIXTURES } = await loadModules();
const signal = new AbortController().signal;
const n = () => 8;

test('每个开发样例都能通过同一套校验，且手写部分都带 _dev_sample', async () => {
  for (const name of Object.keys(FIXTURES)) {
    const data = fixtureData(name, n);
    const c = createMockClient(name);
    const exp = await c.getExperiment(signal);
    if (name === 'none') {
      assert.deepEqual(exp, { available: false });
      continue;
    }
    assert.equal(data.experiment._dev_sample, true, `${name} 清单`);
    for (const s of Object.values(data.runStates)) assert.equal(s._dev_sample, true);
    for (const s of Object.values(data.statuses)) assert.equal(s._dev_sample, true);
    if (data.evolution && data.evolution !== 'example') assert.equal(data.evolution._dev_sample, true);
    for (const key of ['run1', 'run2', 'control']) {
      const id = exp.manifest[key].run_id;
      if (data.runStates[id]) await c.getRunState(id, signal);
    }
    const evoId = exp.manifest.evolution.evolution_id;
    if (data.statuses[evoId]) await c.getEvolveStatus(evoId, signal);
  }
});

test('报告指标与正式示例一致；未完成的运行读报告得到 409，不给假数字', async () => {
  const c = createMockClient('running');
  const r1 = example('run_report.run1.json');
  assert.equal((await c.getReport(r1.run_id, signal)).metrics.isi_response_rate, r1.metrics.isi_response_rate);
  await assert.rejects(c.getReport('run-20261115-02', signal), (e) => e.status === 409 && e.code === 'REPORT_NOT_READY');
  await assert.rejects(c.getReport('nope', signal), (e) => e.status === 404);
});

test('学习进行中读进化记录：NOT_READY，区别于不存在', async () => {
  const c = createMockClient('learning');
  await assert.rejects(c.getEvolution('evolution-20261115-01', signal), (e) => e.code === 'NOT_READY');
  await assert.rejects(c.getEvolution('other', signal), (e) => e.code === 'EVOLUTION_NOT_FOUND');
});

test('数据静态：重复读取结果相同（不制造实时增长）', async () => {
  const c = createMockClient('running');
  const a = await c.getRunState('run-20261115-02', signal);
  await new Promise((r) => setTimeout(r, 20));
  const b = await c.getRunState('run-20261115-02', signal);
  assert.deepEqual(a, b);
});

test('开发样例选择：未知名称如实报告', () => {
  assert.deepEqual(parseFixtureName('?fixture=learning'), { name: 'learning', unknown: null });
  assert.deepEqual(parseFixtureName(''), { name: 'complete', unknown: null });
  assert.deepEqual(parseFixtureName('?fixture=hack'), { name: 'complete', unknown: 'hack' });
});
