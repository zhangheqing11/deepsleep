import type { ExperimentResult } from '../api/extensionTypes';
import { Empty, errorText, Notice } from '../components/common';
import { LearnedPanel } from '../components/LearnedPanel';
import { MetricsPanel } from '../components/MetricsPanel';
import { RollbackPanel } from '../components/RollbackPanel';
import { Timeline } from '../components/Timeline';
import type { ExperimentData } from '../hooks/useExperimentData';
import type { PollHandle } from '../hooks/usePoller';

/** 进化总览：时间线 + 三栏（比什么指标 / 学到了什么 / 怎么回退）。 */
export function OverviewPage({ experiment, data }: { experiment: PollHandle<ExperimentResult>; data: ExperimentData }) {
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
      <Timeline m={m} data={data} />
      <div className="columns">
        <MetricsPanel m={m} data={data} />
        <LearnedPanel m={m} data={data} />
        <RollbackPanel m={m} data={data} />
      </div>
    </main>
  );
}
