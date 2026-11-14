import type { HealthResponse } from '../api/draftTypes';
import type { ResourceState } from '../hooks/useResource';
import { CONTRACTS_VERSION, type AdapterKind } from '../config';
import { Badge } from './common';
import { DataSourceBadge } from './DataSourceBanner';

export function HealthBar({
  adapter,
  health,
  onRetry,
}: {
  adapter: AdapterKind;
  health: ResourceState<HealthResponse>;
  onRetry: () => void;
}) {
  return (
    <div className="health" aria-live="polite">
      {health.status === 'loading' || health.status === 'idle' ? (
        <Badge>检查服务…</Badge>
      ) : health.status === 'error' ? (
        <>
          <Badge tone="danger">后端不可用</Badge>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
            重新检查
          </button>
        </>
      ) : (
        <>
          <Badge tone={health.data.status === 'ok' ? 'ok' : 'warn'}>
            {health.data.status === 'ok' ? '服务正常' : `服务状态：${health.data.status}`}
          </Badge>
          <DataSourceBadge adapter={adapter} mode={health.data.execution_mode} />
          {health.data.contracts_version && health.data.contracts_version !== CONTRACTS_VERSION && (
            <Badge tone="warn">
              契约版本不一致：后端 {health.data.contracts_version} / 前端 {CONTRACTS_VERSION}
            </Badge>
          )}
        </>
      )}
    </div>
  );
}
