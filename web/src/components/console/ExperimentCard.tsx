import type { Experiment, ExperimentResponse } from '../../api/extensionTypes';
import type { useReadPoller } from '../../hooks/useReadPoller';
import { dateTime } from '../../lib/format';
import { label, STEP_STATE_LABEL } from '../../lib/labels';
import { Badge, Card, ErrorNotice, Notice, Spinner } from '../common';

export function ExperimentCard({ poller, mock, onCompare }: {
  poller: ReturnType<typeof useReadPoller<ExperimentResponse>>;
  mock: boolean;
  onCompare: (experiment: Experiment) => void;
}) {
  const { data, error, polling, reload } = poller;
  const experiment = data && 'experiment_id' in data ? data : null;
  return <Card title="当前实验" aside={<button type="button" className="btn btn-sm" onClick={reload}>重新查询</button>}>
    {mock && <p className="source-note">模拟实验（占位）· 固定示例，不代表实际学习效果。</p>}
    {error && <ErrorNotice error={error} title={polling ? '连接中断，正在自动重试' : '实验读取失败'} />}
    {!data && !error && <Spinner label="正在读取实验…" />}
    {data && !experiment && <p className="muted">暂无实验，等待操作员发起。</p>}
    {experiment && <>
      <p className="small muted">{experiment.experiment_id} · {dateTime(experiment.updated_at)}</p>
      <ol className="flow" aria-label="实验流程">
        {([
          ['运行 1', experiment.run1], ['学习', experiment.evolution],
          ['运行 2', experiment.run2], ['对照', experiment.control],
        ] as const).map(([title, node], i) => <li key={title}>
          <span className="flow-step">{i + 1}</span><div><strong>{title}</strong>
            <div><Badge tone={node?.state === 'failed' ? 'danger' : node?.state === 'done' ? 'ok' : 'neutral'}>{node ? label(STEP_STATE_LABEL, node.state) : '暂无'}</Badge></div>
            <div className="small mono">{node && ('run_id' in node ? node.run_id : node.evolution_id)}</div>
          </div>
        </li>)}
      </ol>
      {experiment.stage === 'failed' && <Notice tone="danger" title="实验执行失败">{experiment.error}</Notice>}
      {experiment.stage === 'done' && <button type="button" className="btn btn-primary" onClick={() => onCompare(experiment)}>打开三方对比</button>}
    </>}
  </Card>;
}
