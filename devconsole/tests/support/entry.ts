// 测试入口：把被测的真实模块打包给 node --test 使用（见 load.mjs）。不参与应用构建。
export { parseDataMode, parseMs, parseBaseUrl, isImplemented } from '../../src/lib/settings';
export { SerialPoller, backoffFor } from '../../src/lib/poller';
export { ApiError } from '../../src/api/errors';
export { ShapeError } from '../../src/lib/shape';
export {
  parseExperiment,
  parseRunState,
  parseReport,
  parseEvolution,
  parseEvolveStatus,
} from '../../src/api/validate';
export { createHttpClient } from '../../src/api/httpClient';
export { createMockClient } from '../../src/api/mockClient';
export { fixtureData, parseFixtureName, FIXTURES } from '../../src/fixtures/devSamples';
export { setupSource } from '../../src/api/index';
export { authHeader, getAuthState, noteUnauthorized, refreshAuth, signIn, signOut } from '../../src/api/auth';
