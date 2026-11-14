// 按配置选择数据源。snapshot（回放包）尚未实现：返回 unavailable，页面明确显示不可用，不退回 mock。

import type { DataClient } from './client';
import { createHttpClient } from './httpClient';
import { createMockClient } from './mockClient';
import { API_BASE_URL, MODE_SETTING } from '../config';
import { FIXTURES, parseFixtureName, type FixtureName } from '../fixtures/devSamples';
import { isImplemented, type DataMode } from '../lib/settings';

export type SourceSetup =
  | { state: 'ready'; client: DataClient; fixture: FixtureName | null; unknownFixture: string | null }
  | { state: 'unavailable'; mode: DataMode; reason: string }
  | { state: 'config_error'; raw: string };

export function setupSource(search: string): SourceSetup {
  if (!MODE_SETTING.ok) return { state: 'config_error', raw: MODE_SETTING.raw };
  const mode = MODE_SETTING.mode;
  if (!isImplemented(mode)) {
    return {
      state: 'unavailable',
      mode,
      reason: '回放模式（snapshot）尚未实现：要等后端回放包导出格式（B4）确定后再做。当前不显示任何数据，也不会改用模拟数据。',
    };
  }
  if (mode === 'http') return { state: 'ready', client: createHttpClient(API_BASE_URL), fixture: null, unknownFixture: null };
  const f = parseFixtureName(search);
  return { state: 'ready', client: createMockClient(f.name), fixture: f.name, unknownFixture: f.unknown };
}

export { FIXTURES };
