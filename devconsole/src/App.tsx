import { useMemo } from 'react';
import type { DataClient } from './api/client';
import type { ExperimentResult } from './api/extensionTypes';
import { FIXTURES, setupSource } from './api';
import { Notice } from './components/common';
import { TopBar } from './components/TopBar';
import { BACKOFF_MS, CONFIG_WARNINGS, EXPERIMENT_POLL_MS, REQUEST_TIMEOUT_MS, STALE_AFTER_FAILURES } from './config';
import { usePoller } from './hooks/usePoller';
import { OverviewPage } from './pages/OverviewPage';

export function App() {
  const setup = useMemo(() => setupSource(window.location.search), []);

  if (setup.state === 'config_error') {
    return (
      <div className="config-error">
        <Notice tone="danger" title="配置错误：数据模式不认识">
          VITE_DATA_MODE=<code>{setup.raw}</code>。只能是 mock、http 或 snapshot。为避免把模拟数据当成实时数据，页面不会自动改用 mock。
        </Notice>
      </div>
    );
  }

  if (setup.state === 'unavailable') {
    return (
      <>
        <TopBar mode={setup.mode} fixtureLabel={null} connection={null} executionModes={[]} />
        <main className="page">
          <Notice tone="warn" title="当前数据模式不可用">
            {setup.reason}
          </Notice>
        </main>
      </>
    );
  }

  const fixtureLabel = setup.fixture ? `开发样例：${FIXTURES[setup.fixture]}` : null;
  return <Dashboard client={setup.client} fixtureLabel={fixtureLabel} unknownFixture={setup.unknownFixture} />;
}

function Dashboard({
  client,
  fixtureLabel,
  unknownFixture,
}: {
  client: DataClient;
  fixtureLabel: string | null;
  unknownFixture: string | null;
}) {
  // 当前实验一直轮询（不设终态）：另一台电脑开始新实验时，展示页自动切换。
  const experiment = usePoller<ExperimentResult>('experiment', {
    fetch: (signal) => client.getExperiment(signal),
    intervalMs: EXPERIMENT_POLL_MS,
    timeoutMs: REQUEST_TIMEOUT_MS,
    backoffMs: BACKOFF_MS,
    staleAfter: STALE_AFTER_FAILURES,
  });

  return (
    <>
      <TopBar mode={client.mode} fixtureLabel={fixtureLabel} connection={experiment} executionModes={[]} />
      {client.mode === 'mock' && (
        <div className="banner banner-mock" role="note">
          模拟数据：指标与进化记录来自 contracts/examples 正式示例，实验进度和学习状态是手写开发样例，均不是实际运行结果。
          {unknownFixture && ` 未知的开发样例“${unknownFixture}”，已显示默认样例。`}
        </div>
      )}
      {client.mode === 'http' && experiment.stale && (
        <div className="banner banner-danger" role="alert">
          接口不可用：下方是最后一次成功读取的数据，可能已过期。正在自动重试。回放模式尚未实现，不会切换到其他数据。
        </div>
      )}
      <nav className="tabs" aria-label="进化后台视图">
        <a href="#/overview" className="active" aria-current="page">
          进化总览
        </a>
        {['运行与跑分', '进化记录', '分类器证据', '模拟来访'].map((t) => (
          <span key={t} aria-disabled="true" title="后续批次实现">
            {t}
          </span>
        ))}
      </nav>
      <OverviewPage client={client} experiment={experiment} />
      {CONFIG_WARNINGS.length > 0 && (
        <p className="foot" role="note">
          配置提示：{CONFIG_WARNINGS.join('；')}
        </p>
      )}
    </>
  );
}
