// ⚠ 接口草案类型：来自后端负责人的《前后端接口草案》及前端反馈，**尚未定稿，也不在 contracts/ 里**。
// 包括：health、创建运行、运行状态与进度、会谈列表项、统一错误结构。
// 定稿后（FastAPI OpenAPI 或 contracts/）以正式定义替换本文件。

import type { SessionStatus } from './contractTypes';

export type ExecutionMode = 'mock' | 'real';
export type RunTaskStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface HealthResponse {
  status: string;
  execution_mode: ExecutionMode;
  /** 前端反馈中建议新增，可能缺省 */
  contracts_version?: string;
}

/**
 * 后端 Mock 的场景开关（cxj/api-server api/MOCK_API.md），通过请求头 X-Mock-Scenario 传递，不放进请求体。
 * 只用于 execution_mode=mock 的调试；真实执行时不发送。
 */
export type BackendMockScenario = 'normal' | 'fail' | 'report_delay';

export interface CreateRunRequest {
  split: 'A' | 'B';
  /** 前端反馈：建议可选，缺省由后端使用当前版本 */
  playbook_version?: string;
}

export interface CreateRunResponse {
  run_id: string;
  status: RunTaskStatus;
  execution_mode: ExecutionMode;
}

export interface RunProgress {
  total: number;
  completed: number;
  failed: number;
}

export interface RunTaskError {
  code: string;
  message: string;
}

export interface RunStatusResponse {
  run_id: string;
  status: RunTaskStatus;
  execution_mode: ExecutionMode;
  split: string;
  playbook_version: string;
  progress: RunProgress;
  elapsed_ms: number;
  report_available: boolean;
  error: RunTaskError | null;
}

export interface SessionListItem {
  visitor_id: string;
  status: RunTaskStatus;
  session_available: boolean;
  /** 前端反馈中建议新增：契约 session.status，没有记录时为 null */
  session_status?: SessionStatus | null;
}

export interface ListResponse<T> {
  items: T[];
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    request_id?: string;
    details?: { field?: string; message: string }[];
  };
}
