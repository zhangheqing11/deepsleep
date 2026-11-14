import type { RunPollerState } from '../hooks/useRunPoller';
import type { AdapterKind } from '../config';
import { ms } from '../lib/format';
import { RUN_STATUS_LABEL } from '../lib/labels';
import { Badge, ErrorNotice, Notice, Spinner, type Tone } from './common';
import { DataSourceBadge } from './DataSourceBanner';

const STATUS_TONE: Record<string, Tone> = {
  queued: 'neutral',
  running: 'info',
  succeeded: 'ok',
  failed: 'danger',
};

/** 当前运行：状态、进度、简要信息；网络问题与任务失败分开显示 */
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
  const { run: polled, polling, transientError, stop, stopError, restart } = poller;
  // 切换运行的瞬间不显示上一个运行的状态
  const run = polled && polled.run_id === runId ? polled : null;

  const clearButton = (
    <button type="button" className="quiet-btn" onClick={onClear}>
      清除当前运行
    </button>
  );

  if (stop === 'not_found') {
    return (
      <section className="section">
        <div className="section-head">
          <h2>当前运行</h2>
          {clearButton}
        </div>
        <ErrorNotice
          error={stopError!}
          title="找不到这个运行"
          tone="warn"
          action={<span className="small muted">已停止查询，并清除了本地保存的运行编号。请重新发起运行。</span>}
        />
        <p className="mono small muted">{runId}</p>
      </section>
    );
  }

  const total = run?.progress.total ?? null;
  const done = run ? run.progress.completed + run.progress.failed : 0;
  const ratio = total !== null && total > 0 ? Math.min(1, done / total) : 0;

  return (
    <section className="section">
      <div className="section-head">
        <h2>
          当前运行 <span className="mono small muted">{runId}</span>
        </h2>
        <div className="row">
          {run && <DataSourceBadge adapter={adapter} mode={run.execution_mode} />}
          {clearButton}
        </div>
      </div>

      {!run && !stop && <Spinner label="正在查询运行状态…" />}

      {run && (
        <>
          <div className="progress-label">
            <span className="row">
              <Badge tone={STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</Badge>
              {run.progress.failed > 0 && (
                <span className="small danger-text">{run.progress.failed} 个来访执行失败</span>
              )}
            </span>
            <span className="small muted tabular">{total === null ? `已处理 ${done} 个来访 · 总人数未知` : total === 0 ? '等待准备' : `${done} / ${total} 个来访`}</span>
          </div>
          <div
            className={`track track-${run.status}`}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total ?? undefined}
            aria-valuenow={total === null ? undefined : done}
            aria-label="运行进度"
          >
            <div className="track-fill" style={{ width: `${ratio * 100}%` }} />
            {run.progress.failed > 0 && total !== null && total > 0 && (
              <div
                className="track-fail"
                style={{
                  left: `${(run.progress.completed / total) * 100}%`,
                  width: `${(run.progress.failed / total) * 100}%`,
                }}
              />
            )}
          </div>
          {ratio >= 1 && run.status === 'running' && (
            <p className="small muted">全部来访已处理，正在汇总；以运行状态为准。</p>
          )}

          <dl className="runline">
            <div>
              <dt>来访分组</dt>
              <dd>{run.split} 组</dd>
            </div>
            <div>
              <dt>playbook 版本</dt>
              <dd className="mono">{run.playbook_version}</dd>
            </div>
            <div>
              <dt>已用时间</dt>
              <dd>{ms(run.elapsed_ms)}</dd>
            </div>
          </dl>
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
    </section>
  );
}
