import type { RunHistoryEntry } from '../../lib/storage';
import { dateTime } from '../../lib/format';
import { RUN_STATUS_LABEL, label } from '../../lib/labels';
import { Badge } from '../common';

const STATUS_TONE: Record<string, 'neutral' | 'info' | 'ok' | 'danger' | 'warn'> = {
  queued: 'neutral',
  running: 'info',
  succeeded: 'ok',
  failed: 'danger',
  not_found: 'warn',
};

/** 最近运行：收成一行，展开后是紧凑列表 */
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
  if (history.length === 0) return null;
  return (
    <details className="fold">
      <summary>
        最近运行（{history.length}） <span className="small muted">· 仅本机记录</span>
      </summary>
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
                <span className="small muted">
                  {[h.split && `${h.split} 组`, h.playbook_version].filter(Boolean).join(' · ')}
                </span>
                {h.status && (
                  <Badge tone={STATUS_TONE[h.status] ?? 'neutral'}>
                    {h.status === 'not_found' ? '已不存在' : label(RUN_STATUS_LABEL, h.status)}
                  </Badge>
                )}
                {current && <span className="small">当前</span>}
                <span className="small muted run-history-time">{dateTime(h.created_at)}</span>
              </button>
              <button
                type="button"
                className="quiet-btn"
                aria-label={`从本机记录中移除 ${h.run_id}`}
                onClick={() => onForget(h.run_id)}
              >
                移除
              </button>
            </li>
          );
        })}
      </ul>
      <p className="small muted">后端提供运行列表接口后，这里改为读取服务端记录（含其他设备发起的运行）。</p>
    </details>
  );
}
