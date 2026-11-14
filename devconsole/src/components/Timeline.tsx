import type { ExperimentManifest } from '../api/extensionTypes';
import type { ExperimentData } from '../hooks/useExperimentData';
import { clock, clockMs } from '../lib/format';
import { label, STAGE_LABEL, STAGE_STATE_LABEL } from '../lib/labels';
import { timeline, type TimelineNode } from '../model/overview';
import { Badge, errorText, type Tone } from './common';

const STATE_TONE: Record<string, Tone> = { pending: 'neutral', running: 'info', done: 'ok', failed: 'danger' };

/** 实验时间线：运行 1 → 学习 → 运行 2，对照与运行 2 并列（同一批 B 组来访）。 */
export function Timeline({ m, data }: { m: ExperimentManifest; data: ExperimentData }) {
  const nodes = timeline(
    m,
    { run1: data.runs.run1.state.data, run2: data.runs.run2.state.data, control: data.runs.control.state.data },
    data.status.data,
  );
  const [run1, learn, run2, control] = nodes;
  return (
    <section className="panel timeline-panel" aria-label="实验时间线">
      <div className="timeline-head">
        <h2>
          实验 <span className="mono">{m.experiment_id}</span>
        </h2>
        <Badge tone={m.stage === 'failed' ? 'danger' : m.stage === 'done' ? 'ok' : 'info'}>
          {m.stage === 'done' || m.stage === 'failed' ? label(STAGE_LABEL, m.stage) : `当前：${label(STAGE_LABEL, m.stage)}`}
        </Badge>
        <span className="small muted">清单更新于 {clock(m.updated_at)}</span>
      </div>
      {m.error && (
        <p className="timeline-error" role="alert">
          实验失败：{m.error}
        </p>
      )}
      <ol className="timeline">
        <Node node={run1} poll={data.runs.run1.state} />
        <li className="arrow" aria-hidden="true">→</li>
        <Node node={learn} />
        <li className="arrow" aria-hidden="true">→</li>
        <li className="pair">
          <ol className="pair-list">
            <Node node={run2} poll={data.runs.run2.state} role="run2" />
            <Node node={control} poll={data.runs.control.state} role="control" />
          </ol>
          <span className="pair-note small muted">同一批 B 组模拟来访</span>
        </li>
      </ol>
    </section>
  );
}

function Node({
  node,
  poll,
  role,
}: {
  node: TimelineNode;
  poll?: ExperimentData['runs']['run1']['state'];
  role?: 'run2' | 'control';
}) {
  const p = node.progress;
  return (
    <li className={`node node-${node.state} ${role ? `role-${role}` : node.key === 'run1' ? 'role-run1' : ''}`}>
      <div className="node-title">
        <strong>{node.title}</strong>
        <Badge tone={STATE_TONE[node.state]}>{label(STAGE_STATE_LABEL, node.state)}</Badge>
      </div>
      <div className="small muted">{node.sub}</div>
      {poll && poll.enabled && (
        <div className="node-progress small">
          {p ? (
            <>
              <progress max={p.total} value={(p.completed ?? 0) + (p.failed ?? 0)} aria-label={`${node.title} 进度`} />
              <span>
                {p.completed ?? '—'} / {p.total} 个来访完成{p.failed ? `，失败 ${p.failed}` : ''}
              </span>
            </>
          ) : poll.data ? (
            <span className="muted">后端未提供进度</span>
          ) : null}
          {poll.error && !poll.data && <span className="node-error">{errorText(poll.error)}</span>}
          {poll.lastSuccessAt !== null && (
            <span className="muted">
              来源 /runs/{poll.data?.run_id} · {clockMs(poll.lastSuccessAt)}
            </span>
          )}
        </div>
      )}
    </li>
  );
}
