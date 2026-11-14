import type { DataClient } from '../api/client';
import type { ExperimentResult } from '../api/extensionTypes';
import { Badge, Empty, errorText, Notice } from '../components/common';
import type { PollHandle } from '../hooks/usePoller';
import { clock } from '../lib/format';
import { label, STAGE_LABEL } from '../lib/labels';

/** 进化总览骨架：三栏分别回答“比什么指标 / 学到了什么 / 怎么回退”。内容在 F1 补齐。 */
export function OverviewPage({ experiment }: { client: DataClient; experiment: PollHandle<ExperimentResult> }) {
  const result = experiment.data;

  if (result === null) {
    if (experiment.error) {
      return (
        <main className="page">
          <Notice tone="danger" title="读取当前实验失败" action={<button onClick={experiment.retryNow}>立即重试</button>}>
            {errorText(experiment.error)}
          </Notice>
        </main>
      );
    }
    return (
      <main className="page">
        <Empty>正在读取当前实验…</Empty>
      </main>
    );
  }

  if (!result.available) {
    return (
      <main className="page">
        <Notice tone="info" title="还没有实验">
          操作员开始实验后，这里会自动出现，无需刷新，也不需要输入运行编号。
        </Notice>
      </main>
    );
  }

  const m = result.manifest;
  return (
    <main className="page">
      <section className="panel" aria-label="实验">
        <h2>
          实验 <span className="mono">{m.experiment_id}</span>
          <Badge tone={m.stage === 'failed' ? 'danger' : m.stage === 'done' ? 'ok' : 'info'}>{label(STAGE_LABEL, m.stage)}</Badge>
          <span className="small muted">清单更新于 {clock(m.updated_at)}</span>
        </h2>
        {m.error && <Notice tone="danger" title="实验失败">{m.error}</Notice>}
      </section>
      <div className="columns">
        <section className="panel">
          <h2>
            <span className="q">①</span>比什么指标
          </h2>
          <Empty>尚未生成</Empty>
        </section>
        <section className="panel">
          <h2>
            <span className="q">②</span>学到了什么
          </h2>
          <Empty>尚未生成</Empty>
        </section>
        <section className="panel">
          <h2>
            <span className="q">③</span>怎么回退
          </h2>
          <Empty>尚未生成</Empty>
        </section>
      </div>
    </main>
  );
}
