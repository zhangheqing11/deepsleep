import { api } from '../api';
import type { RunReport, Session } from '../api/contractTypes';
import type { HealthResponse, ListResponse, SessionListItem } from '../api/draftTypes';
import { ApiError, toApiError } from '../api/errors';
import { REPORT_NOT_READY_DELAY_MS, REPORT_NOT_READY_RETRIES } from '../config';
import { sleep, useResource } from './useResource';

export function useHealth() {
  return useResource<HealthResponse>('health', (signal) => api.health(signal));
}

/**
 * 报告：只有运行状态给出 report_available=true 时才请求。
 * 仍收到 409 REPORT_NOT_READY 时视为竞态，按配置重试几次再交给页面显示“报告生成中”。
 */
export function useReport(runId: string | null, reportAvailable: boolean) {
  const key = runId && reportAvailable ? `report:${runId}` : null;
  return useResource<RunReport>(key, async (signal) => {
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await api.getReport(runId as string, signal);
      } catch (e) {
        const err = toApiError(e);
        const notReady = err.kind === 'http' && err.code === 'REPORT_NOT_READY';
        if (!notReady || attempt >= REPORT_NOT_READY_RETRIES) throw err;
        await sleep(REPORT_NOT_READY_DELAY_MS, signal);
      }
    }
  });
}

export function isReportNotReady(e: ApiError): boolean {
  return e.kind === 'http' && e.code === 'REPORT_NOT_READY';
}

/** 会谈列表：首版在运行结束后读取（接口草案：运行完成后提供完整列表） */
export function useSessionList(runId: string | null, enabled: boolean) {
  const key = runId && enabled ? `sessions:${runId}` : null;
  return useResource<ListResponse<SessionListItem>>(key, (signal) => api.listSessions(runId as string, signal));
}

export function useSession(runId: string, visitorId: string) {
  return useResource<Session>(`session:${runId}/${visitorId}`, (signal) =>
    api.getSession(runId, visitorId, signal),
  );
}
