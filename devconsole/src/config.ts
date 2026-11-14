// 进化后台唯一的配置入口：数据模式、接口地址、轮询参数。组件里不要直接写地址。

import { parseBaseUrl, parseDataMode, parseMs } from './lib/settings';

const env = import.meta.env;

export const MODE_SETTING = parseDataMode(env.VITE_DATA_MODE);

/** API 基础地址，默认走同源 /api/v1（开发期由 Vite 代理）。 */
export const API_BASE_URL = parseBaseUrl(env.VITE_API_BASE_URL);

const experimentPoll = parseMs('VITE_EXPERIMENT_POLL_MS', env.VITE_EXPERIMENT_POLL_MS, 2000, 500);
const runPoll = parseMs('VITE_RUN_POLL_MS', env.VITE_RUN_POLL_MS, 1000, 500);
const timeout = parseMs('VITE_REQUEST_TIMEOUT_MS', env.VITE_REQUEST_TIMEOUT_MS, 8000, 1000);

/** 当前实验发现：一直轮询，另一台电脑开始新实验时展示页自动切换。 */
export const EXPERIMENT_POLL_MS = experimentPoll.value;
/** 运行进度 / 学习状态：到终态即停。 */
export const RUN_POLL_MS = runPoll.value;
/** 单次请求超时。 */
export const REQUEST_TIMEOUT_MS = timeout.value;
/** 失败后的退避间隔，依次使用，最后一个值重复。 */
export const BACKOFF_MS = [2000, 4000, 8000];
/** 连续失败多少次后标为“断连 / 数据过期”（仍保留上次数据并继续重试）。 */
export const STALE_AFTER_FAILURES = 3;
/** 报告 409 REPORT_NOT_READY 时的重试间隔。 */
export const REPORT_RETRY_MS = 2000;

export const CONFIG_WARNINGS: string[] = [experimentPoll.warning, runPoll.warning, timeout.warning].filter(
  (w): w is string => w !== null,
);

export const CONTRACTS_VERSION = '0.1.0';
