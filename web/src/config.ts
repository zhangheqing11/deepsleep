// 前端唯一的接口配置入口。组件里不要直接写地址。

import { resolveDevconsoleLink } from './lib/devconsoleLink';

export type AdapterKind = 'mock' | 'http';

const env = import.meta.env;

/** API 基础地址，默认走 Vite 开发代理：/api/v1 */
export const API_BASE_URL: string = (env.VITE_API_BASE_URL?.trim() || '/api/v1').replace(/\/+$/, '');

/** mock = 前端本地模拟适配器；http = 请求后端 */
export const API_ADAPTER: AdapterKind = env.VITE_API_ADAPTER === 'mock' ? 'mock' : 'http';

/** 运行状态轮询间隔（接口草案：约 1 秒） */
export const POLL_INTERVAL_MS = 1000;

/** 网络失败或 5xx 时的退避间隔，依次使用，最后一个值重复 */
export const POLL_BACKOFF_MS = [2000, 4000, 5000];

/** 运行已 succeeded 但 report_available 仍为 false 时，最多再轮询多少次 */
export const REPORT_WAIT_MAX_POLLS = 30;

/** 报告接口返回 409 REPORT_NOT_READY 时的重试次数和间隔 */
export const REPORT_NOT_READY_RETRIES = 3;
export const REPORT_NOT_READY_DELAY_MS = 1000;

/** 当前前端对照的契约版本 */
export const CONTRACTS_VERSION = '0.1.0';

/**
 * 进化后台（独立应用 devconsole/）的地址，侧栏入口在新标签页打开它。
 * 只在这里配置：VITE_DEVCONSOLE_URL。不填时入口显示“尚未配置”。
 * 开发期可指向同机 devconsole 服务（如 http://localhost:5174/devconsole/）；部署时用后端确认的挂载地址（如 /devconsole/）。
 */
export const DEVCONSOLE_LINK = resolveDevconsoleLink(
  env.VITE_DEVCONSOLE_URL,
  typeof window === 'undefined' ? 'http://localhost/' : window.location.href,
);
