// 可替换的数据访问接口：页面只依赖这个接口，不关心背后是前端模拟还是后端 HTTP。

import type { AdapterKind } from '../config';
import type { Evolution, RunReport, Session } from './contractTypes';
import type {
  BackendMockScenario,
  CreateRunRequest,
  CreateRunResponse,
  HealthResponse,
  ListResponse,
  RunStatusResponse,
  SessionListItem,
} from './draftTypes';

import type { RunListItem, ExperimentResponse, RunEvidence, EvolutionListItem, EvolutionStatus, EvolutionInsights, PlaybookVersion, Playbook, PlaybookDiff } from './extensionTypes';
import type { PipelineLaunchRequest, PipelineLaunchResponse, PipelineResponse, PipelineStopResponse } from './extensionTypes';

export interface ApiClient {
  readonly adapter: AdapterKind;
  health(signal?: AbortSignal): Promise<HealthResponse>;
  /**
   * idempotencyKey：同一次操作的网络重试复用同一个 key。
   * mockScenario：仅 HTTP 适配器、后端为 Mock 时使用，作为 X-Mock-Scenario 请求头；前端本地模拟忽略此参数。
   */
  createRun(
    body: CreateRunRequest,
    idempotencyKey: string,
    signal?: AbortSignal,
    mockScenario?: BackendMockScenario,
  ): Promise<CreateRunResponse>;
  listRuns(limit?: number, signal?: AbortSignal): Promise<ListResponse<RunListItem>>;
  getExperiment(signal?: AbortSignal): Promise<ExperimentResponse>;
  getEvidence(runId: string, signal?: AbortSignal): Promise<RunEvidence>;
  listEvolutions(limit?: number, signal?: AbortSignal): Promise<ListResponse<EvolutionListItem>>;
  getEvolution(id: string, signal?: AbortSignal): Promise<Evolution>;
  getEvolutionStatus(id: string, signal?: AbortSignal): Promise<EvolutionStatus>;
  getEvolutionInsights(id: string, signal?: AbortSignal): Promise<EvolutionInsights>;
  listPlaybookVersions(signal?: AbortSignal): Promise<ListResponse<PlaybookVersion>>;
  getPlaybook(version: string, signal?: AbortSignal): Promise<Playbook>;
  getPlaybookDiff(from: string, to: string, signal?: AbortSignal): Promise<PlaybookDiff>;
  getRun(runId: string, signal?: AbortSignal): Promise<RunStatusResponse>;
  getReport(runId: string, signal?: AbortSignal): Promise<RunReport>;
  listSessions(runId: string, signal?: AbortSignal): Promise<ListResponse<SessionListItem>>;
  getSession(runId: string, visitorId: string, signal?: AbortSignal): Promise<Session>;
  /** 全链路演示（api/PIPELINE_API.md，非契约） */
  getPipeline(signal?: AbortSignal): Promise<PipelineResponse>;
  launchPipeline(body: PipelineLaunchRequest, signal?: AbortSignal): Promise<PipelineLaunchResponse>;
  stopPipeline(signal?: AbortSignal): Promise<PipelineStopResponse>;
}
