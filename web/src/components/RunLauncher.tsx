import { useState } from 'react';
import type { ApiError } from '../api/errors';
import { MOCK_SCENARIOS, getMockScenario, setMockScenario, type MockScenario } from '../api/mockClient';
import type { AdapterKind } from '../config';
import type { PendingCreate } from '../lib/storage';
import { Card, ErrorNotice, Notice } from './common';

interface Props {
  adapter: AdapterKind;
  busy: boolean;
  disabledReason: string | null;
  submitting: boolean;
  error: ApiError | null;
  pending: PendingCreate | null;
  onStart: (split: 'A' | 'B', playbookVersion?: string) => void;
  onRetry: () => void;
  onDiscard: () => void;
}

export function RunLauncher(props: Props) {
  const { adapter, busy, disabledReason, submitting, error, pending, onStart, onRetry, onDiscard } = props;
  const [split, setSplit] = useState<'A' | 'B'>('A');
  const [version, setVersion] = useState('');
  const [scenario, setScenario] = useState<MockScenario>(() => getMockScenario());
  const unconfirmed = pending && !submitting && error?.isTransient;
  const disabled = busy || submitting || Boolean(disabledReason) || Boolean(unconfirmed);

  return (
    <Card title="发起一次评测运行">
      <p className="muted">
        一次运行会对一组模拟来访执行完整评测（每个来访两轮会谈）。来访数量、seed 与 playbook 版本由后端配置决定。
      </p>

      <fieldset className="segmented" disabled={busy || submitting}>
        <legend>来访分组</legend>
        {(['A', 'B'] as const).map((s) => (
          <label key={s} className={split === s ? 'active' : ''}>
            <input type="radio" name="split" value={s} checked={split === s} onChange={() => setSplit(s)} />
            {s} 组
          </label>
        ))}
      </fieldset>
      <p className="small muted">C 组仅用于学习门禁，不在此提供。</p>

      <div className="field">
        <label htmlFor="playbook-version">playbook 版本（可选）</label>
        <input
          id="playbook-version"
          type="text"
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          placeholder="留空 = 后端默认版本"
          value={version}
          disabled={busy || submitting}
          onChange={(e) => setVersion(e.target.value)}
        />
        <p className="small muted">
          实际使用的版本以后端返回为准。后端提供版本列表接口前，这里先手动填写。
          {adapter === 'mock' && ' 模拟数据可用组合：A/v1（运行 1）、B/v1（对照）、B/v2（运行 2）。'}
        </p>
      </div>

      {adapter === 'mock' && (
        <div className="field">
          <label htmlFor="mock-scenario">模拟场景（仅前端本地模拟）</label>
          <select
            id="mock-scenario"
            value={scenario}
            disabled={busy || submitting}
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
          <p className="small muted">{MOCK_SCENARIOS.find((s) => s.value === scenario)?.hint}</p>
        </div>
      )}

      <div className="actions">
        <button type="button" className="btn btn-primary" disabled={disabled} onClick={() => onStart(split, version.trim() || undefined)}>
          {submitting ? '提交中…' : busy ? '运行进行中' : '开始运行'}
        </button>
        {disabledReason && !busy && <span className="small muted">{disabledReason}</span>}
      </div>

      {unconfirmed && error && (
        <ErrorNotice
          error={error}
          tone="warn"
          title="提交结果未确认"
          action={
            <div className="btn-row">
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
      {error && !error.isTransient && <ErrorNotice error={error} title="未能创建运行" />}
      {!error && pending && submitting && <Notice tone="info" title="正在提交…" />}
    </Card>
  );
}
