import type { RunHistoryEntry } from '../../lib/storage';
import { dateTime } from '../../lib/format';
import { RUN_STATUS_LABEL, label } from '../../lib/labels';
import { Badge, Card } from '../common';

const STATUS_TONE: Record<string, 'neutral' | 'info' | 'ok' | 'danger' | 'warn'> = {
  queued: 'neutral',
  running: 'info',
  succeeded: 'ok',
  failed: 'danger',
  not_found: 'warn',
};

export function RecentRuns({
  history,
  currentRunId,
  disabled,
  onSelect,
  onForget,
}: {
  history: RunHistoryEntry[];
  currentRunId: string | null;
  disabled: boolean;
  onSelect: (runId: string) => void;
  onForget: (runId: string) => void;
}) {
  return (
    <Card title="最近运行" aside={<span className="small muted">仅本机记录</span>}>
      {history.length === 0 ? (
        <p className="muted small">这台浏览器还没有发起过运行。</p>
      ) : (
        <ul className="run-history">
          {history.map((h) => {
            const current = h.run_id === currentRunId;
            return (
              <li key={h.run_id} className={current ? 'current' : ''}>
                <button
                  type="button"
                  className="run-history-main"
                  disabled={disabled || current}
                  onClick={() => onSelect(h.run_id)}
                  aria-current={current ? 'true' : undefined}
                >
                  <span className="mono">{h.run_id}</span>
                  <span className="tags">
                    {h.split && <Badge>{`${h.split} 组`}</Badge>}
                    {h.playbook_version && <Badge>{h.playbook_version}</Badge>}
                    {h.status && (
                      <Badge tone={STATUS_TONE[h.status] ?? 'neutral'}>
                        {h.status === 'not_found' ? '已不存在' : label(RUN_STATUS_LABEL, h.status)}
                      </Badge>
                    )}
                    {current && <Badge tone="info">当前</Badge>}
                  </span>
                  <span className="small muted">{dateTime(h.created_at)}</span>
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  aria-label={`从本机记录中移除 ${h.run_id}`}
                  onClick={() => onForget(h.run_id)}
                >
                  移除
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <p className="small muted">后端提供运行列表接口后，这里改为读取服务端记录（含其他设备发起的运行）。</p>
    </Card>
  );
}
