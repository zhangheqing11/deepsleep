import type { RunPollerState } from '../hooks/useRunPoller';
import type { AdapterKind } from '../config';
import { ms } from '../lib/format';
import { RUN_STATUS_LABEL } from '../lib/labels';
import { Badge, Card, ErrorNotice, KeyValue, Notice, Spinner, type Tone } from './common';
import { DataSourceBadge } from './DataSourceBanner';

const STATUS_TONE: Record<string, Tone> = {
  queued: 'neutral',
  running: 'info',
  succeeded: 'ok',
  failed: 'danger',
};

export function RunProgress({
  adapter,
  runId,
  poller,
  onClear,
}: {
  adapter: AdapterKind;
  runId: string;
  poller: RunPollerState;
  onClear: () => void;
}) {
  const { run, polling, transientError, stop, stopError, restart } = poller;

  const clearButton = (
    <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
      清除当前运行
    </button>
  );

  if (stop === 'not_found') {
    return (
      <Card title="当前运行" aside={clearButton}>
        <ErrorNotice
          error={stopError!}
          title="找不到这个运行"
          tone="warn"
          action={<span className="small muted">已停止查询，并清除了本地保存的运行编号。</span>}
        />
        <p className="mono small muted">{runId}</p>
      </Card>
    );
  }

  const total = run?.progress.total ?? 0;
  const done = run ? run.progress.completed + run.progress.failed : 0;
  const ratio = total > 0 ? Math.min(1, done / total) : 0;

  return (
    <Card
      title="当前运行"
      aside={
        <div className="btn-row">
          {run && <DataSourceBadge adapter={adapter} mode={run.execution_mode} />}
          {clearButton}
        </div>
      }
    >
      {!run && !stop && <Spinner label="正在查询运行状态…" />}

      {run && (
        <>
          <div className="progress-head">
            <Badge tone={STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</Badge>
            <span className="muted small">
              {total === 0
                ? '等待准备'
                : `已处理 ${done} / ${total} 个来访${run.progress.failed ? `（其中 ${run.progress.failed} 个执行失败）` : ''}`}
            </span>
          </div>
          <div
            className={`progress progress-${run.status}`}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={done}
            aria-label="运行进度"
          >
            <div className="progress-fill" style={{ width: `${ratio * 100}%` }} />
            {run.progress.failed > 0 && total > 0 && (
              <div
                className="progress-fail"
                style={{ left: `${(run.progress.completed / total) * 100}%`, width: `${(run.progress.failed / total) * 100}%` }}
              />
            )}
          </div>
          {ratio >= 1 && run.status === 'running' && (
            <p className="small muted">全部来访已处理，正在汇总；以运行状态为准。</p>
          )}

          <KeyValue
            items={[
              ['运行编号', <span className="mono">{run.run_id}</span>],
              ['来访分组', `${run.split} 组`],
              ['playbook 版本', <span className="mono">{run.playbook_version}</span>],
              ['已用时间', ms(run.elapsed_ms)],
            ]}
          />
        </>
      )}

      {transientError && (
        <ErrorNotice
          error={transientError}
          tone="warn"
          title="连接中断，正在自动重试"
          action={polling ? <span className="spinner" aria-hidden="true" /> : undefined}
        />
      )}

      {run?.status === 'failed' && (
        <Notice tone="danger" title="运行执行失败">
          <div>{run.error?.message ?? '后端未提供失败原因'}</div>
          {run.error?.code && <div className="mono small muted">{run.error.code}</div>}
        </Notice>
      )}

      {stop === 'client_error' && stopError && (
        <ErrorNotice
          error={stopError}
          title="查询运行状态被拒绝"
          action={
            <button type="button" className="btn btn-sm" onClick={restart}>
              重新查询
            </button>
          }
        />
      )}

      {stop === 'report_wait_timeout' && (
        <Notice
          tone="warn"
          title="运行已完成，但报告长时间未就绪"
          action={
            <button type="button" className="btn btn-sm" onClick={restart}>
              继续查询
            </button>
          }
        >
          已停止自动查询。
        </Notice>
      )}
    </Card>
  );
}
