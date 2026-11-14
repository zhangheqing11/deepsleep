// 可替换的数据访问接口：页面只依赖这个接口，不关心背后是前端模拟还是后端 HTTP。

import type { AdapterKind } from '../config';
import type { RunReport, Session } from './contractTypes';
import type {
  CreateRunRequest,
  CreateRunResponse,
  HealthResponse,
  ListResponse,
  RunStatusResponse,
  SessionListItem,
} from './draftTypes';

export interface ApiClient {
  readonly adapter: AdapterKind;
  health(signal?: AbortSignal): Promise<HealthResponse>;
  /** idempotencyKey：同一次操作的网络重试复用同一个 key */
  createRun(body: CreateRunRequest, idempotencyKey: string, signal?: AbortSignal): Promise<CreateRunResponse>;
  getRun(runId: string, signal?: AbortSignal): Promise<RunStatusResponse>;
  getReport(runId: string, signal?: AbortSignal): Promise<RunReport>;
  listSessions(runId: string, signal?: AbortSignal): Promise<ListResponse<SessionListItem>>;
  getSession(runId: string, visitorId: string, signal?: AbortSignal): Promise<Session>;
}
