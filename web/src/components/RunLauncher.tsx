import { useState } from 'react';
import type { BackendMockScenario, ExecutionMode } from '../api/draftTypes';
import type { ApiError } from '../api/errors';
import { MOCK_SCENARIOS, getMockScenario, setMockScenario, type MockScenario } from '../api/mockClient';
import type { AdapterKind } from '../config';
import type { PendingCreate } from '../lib/storage';
import { ErrorNotice, Notice } from './common';

// 后端 Mock 支持的场景（cxj/api-server api/MOCK_API.md）
const BACKEND_SCENARIOS: { value: BackendMockScenario; label: string; hint: string }[] = [
  { value: 'normal', label: '正常完成', hint: '正常结束，报告与运行成功同时可用' },
  { value: 'fail', label: '任务失败', hint: '整体失败，未完成来访记为失败，没有报告' },
  { value: 'report_delay', label: '报告延迟', hint: '先显示已完成但报告未就绪，约 3 秒后可读' },
];

interface Props {
  adapter: AdapterKind;
  /** 后端 health 返回的执行方式；只有为 mock 时才显示后端场景选择 */
  healthMode: ExecutionMode | null;
  /** 页面副标题：当前状态的一句话 */
  subtitle: string;
  busy: boolean;
  disabledReason: string | null;
  submitting: boolean;
  error: ApiError | null;
  pending: PendingCreate | null;
  onStart: (split: 'A' | 'B', playbookVersion?: string, backendScenario?: BackendMockScenario) => void;
  onRetry: () => void;
  onDiscard: () => void;
}

/** 运行页的标题区：标题 + 主要操作，下面一行紧凑的运行配置 */
export function RunLauncher(props: Props) {
  const { adapter, healthMode, subtitle, busy, disabledReason, submitting, error, pending, onStart, onRetry, onDiscard } = props;
  const [split, setSplit] = useState<'A' | 'B'>('A');
  const [version, setVersion] = useState('');
  const [scenario, setScenario] = useState<MockScenario>(() => getMockScenario());
  // 后端场景只在本次页面内记住，默认 normal；真实执行时不显示、不发送
  const [backendScenario, setBackendScenario] = useState<BackendMockScenario>('normal');
  const showBackendScenario = adapter === 'http' && healthMode === 'mock';
  const unconfirmed = pending && !submitting && error?.isTransient;
  const disabled = busy || submitting || Boolean(disabledReason) || Boolean(unconfirmed);
  const locked = busy || submitting;

  return (
    <section className="page-head">
      <div className="page-title-row">
        <div>
          <h1>运行与报告</h1>
          <p className="muted">{disabledReason ?? subtitle}</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={disabled}
          onClick={() =>
            onStart(split, version.trim() || undefined, showBackendScenario ? backendScenario : undefined)
          }
        >
          {submitting ? '提交中…' : busy ? '运行进行中' : '开始运行'}
        </button>
      </div>

      <div className="config-line">
        <div className="config-item">
          <span className="config-label" id="split-label">
            来访分组
          </span>
          <div className="seg" role="radiogroup" aria-labelledby="split-label">
            {(['A', 'B'] as const).map((s) => (
              <label key={s} className={split === s ? 'active' : ''}>
                <input
                  type="radio"
                  name="split"
                  value={s}
                  checked={split === s}
                  disabled={locked}
                  onChange={() => setSplit(s)}
                />
                {s} 组
              </label>
            ))}
          </div>
        </div>

        <div className="config-item">
          <label className="config-label" htmlFor="playbook-version">
            playbook 版本
          </label>
          <input
            id="playbook-version"
            className="input-sm"
            type="text"
            autoComplete="off"
            spellCheck={false}
            placeholder="留空 = 后端默认"
            value={version}
            disabled={locked}
            onChange={(e) => setVersion(e.target.value)}
          />
        </div>

        {adapter === 'mock' && (
          <div className="config-item">
            <label className="config-label" htmlFor="mock-scenario">
              模拟场景
            </label>
            <select
              id="mock-scenario"
              className="input-sm"
              value={scenario}
              disabled={locked}
              onChange={(e) => {
                const v = e.target.value as MockScenario;
                setScenario(v);
                setMockScenario(v);
              }}
            >
              {MOCK_SCENARIOS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        )}
        {showBackendScenario && (
          <div className="config-item">
            <label className="config-label" htmlFor="backend-scenario">
              模拟场景 · 后端 Mock 调试
            </label>
            <select
              id="backend-scenario"
              className="input-sm"
              value={backendScenario}
              disabled={locked}
              onChange={(e) => setBackendScenario(e.target.value as BackendMockScenario)}
            >
              {BACKEND_SCENARIOS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <details className="fine-print">
        <summary className="small muted">配置说明</summary>
        <ul className="plain-list small muted">
          <li>一次运行会对一组模拟来访执行完整评测（每个来访两轮会谈）。来访数量与 seed 由后端配置决定。</li>
          <li>C 组仅用于学习门禁，不在此提供。实际使用的版本以后端返回为准；这里可手动指定版本。</li>
          {showBackendScenario && (
            <li>
              后端 Mock 场景（通过请求头 X-Mock-Scenario 传给后端，仅用于调试）：
              {BACKEND_SCENARIOS.find((s) => s.value === backendScenario)?.hint}。后端返回真实执行时不显示此选项。
            </li>
          )}
          {adapter === 'mock' && (
            <>
              <li>模拟数据可用组合：A/v1（运行 1）、B/v1（对照）、B/v2（运行 2）。</li>
              <li>当前场景：{MOCK_SCENARIOS.find((s) => s.value === scenario)?.hint}</li>
            </>
          )}
        </ul>
      </details>

      {unconfirmed && error && (
        <ErrorNotice
          error={error}
          tone="warn"
          title="提交结果未确认"
          action={
            <div className="row">
              <button type="button" className="btn btn-sm" onClick={onRetry}>
                重试提交
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onDiscard}>
                放弃
              </button>
            </div>
          }
        />
      )}
      {unconfirmed && (
        <p className="small muted">
          重试会沿用同一个提交标识（Idempotency-Key），后端若已创建任务会返回同一个运行，不会重复创建。
        </p>
      )}
      {adapter === 'http' && error?.code === 'RUNS_VIA_CLI' && <Notice tone="info" title="请在操作员终端发起运行"><pre className="diff">{error.message}</pre></Notice>}
      {error && error.code !== 'RUNS_VIA_CLI' && !error.isTransient && <ErrorNotice error={error} title="未能创建运行" />}
    </section>
  );
}
