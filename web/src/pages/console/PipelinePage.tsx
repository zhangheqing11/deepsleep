// 全链路演示：一键启动“运行 1 → 学习 → 运行 2 与对照”，并给评委看实时进度。
// 接口见 api/PIPELINE_API.md（非契约）。HTTP 服务本身不调用模型，只启动 engine.demo 子进程并读它写的进度文件。
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { api } from '../../api';
import { toApiError, type ApiError } from '../../api/errors';
import type {
  PipelineBatch,
  PipelineGeneration,
  PipelineLauncher,
  PipelineLaunchRequest,
  PipelineRunResult,
  PipelineSnapshot,
  PipelineStep,
} from '../../api/extensionTypes';
import { Badge, ErrorNotice, Notice, Spinner } from '../../components/common';
import { LiveGenerationCurve } from '../../components/GenerationCurve';
import { HREF } from '../../hooks/useHashRoute';
import { usePipeline, type PipelinePoll } from '../../hooks/usePipeline';
import {
  aboutMinutes,
  CANDIDATE_STATE_LABEL,
  clock,
  continueFromText,
  defaultOpen,
  defaultPreset,
  isResetPreset,
  launchConfirmText,
  lineageConflict,
  orderPresets,
  RESET_TAG,
  deltaPoints,
  displayState,
  outcomeSentence,
  overallProgress,
  PHASE_LABEL,
  PIPELINE_STATE_LABEL,
  rate,
  sessionsText,
  signedPoints,
  STEP_STATE_LABEL,
  stepSessions,
  stepSummary,
  tick,
} from '../../lib/pipeline';
import '../../pipeline.css';

// ---------- 启动 / 停止 ----------

export interface PipelineActions {
  busy: 'launch' | 'stop' | null;
  error: { op: 'launch' | 'stop'; error: ApiError } | null;
  launch: (body: PipelineLaunchRequest) => void;
  stop: () => void;
  dismiss: () => void;
}

function usePipelineActions(refresh: () => void): PipelineActions {
  const [busy, setBusy] = useState<PipelineActions['busy']>(null);
  const [error, setError] = useState<PipelineActions['error']>(null);
  const run = useCallback(
    (op: 'launch' | 'stop', call: () => Promise<unknown>) => {
      setBusy(op);
      setError(null);
      call()
        .then(() => refresh())
        .catch((e) => setError({ op, error: toApiError(e) }))
        .finally(() => setBusy(null));
    },
    [refresh],
  );
  return {
    busy,
    error,
    launch: (body) => run('launch', () => api.launchPipeline(body)),
    stop: () => run('stop', () => api.stopPipeline()),
    dismiss: () => setError(null),
  };
}

/** 进行中每秒在本地走一次表；每次轮询拿到新数据后从服务端的值重新起算 */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [active]);
  return now;
}

export function PipelinePage() {
  const poll = usePipeline();
  const running = displayState(poll.data) === 'running';
  const now = useNow(running);
  const actions = usePipelineActions(poll.refresh);
  return <PipelineView poll={poll} now={now} actions={actions} />;
}

// ---------- 页面 ----------

export function PipelineView({ poll, now, actions }: { poll: Omit<PipelinePoll, 'refresh'>; now: number; actions: PipelineActions }) {
  const { data, error } = poll;
  const receivedAt = poll.receivedAt ?? now;
  const snap: PipelineSnapshot | null = data && data.available ? data : null;
  const launcher = data?.launcher ?? null;
  const state = displayState(data);
  const running = state === 'running';

  const elapsed = snap ? tick(snap.elapsed_s, receivedAt, now, running, 1) : null;
  const eta = snap && running ? tick(snap.eta_s, receivedAt, now, true, -1) : null;
  const progress = snap ? overallProgress(snap, elapsed, eta) : null;

  return (
    <div className="page pl">
      <section className="pl-head">
        <div className="pl-headline">
          <div className="pl-titles">
            <h1>全链路演示</h1>
            <p className="pl-lede">
              运行 1 用当前手册谈 A 组来访 → 系统读自己没谈好的会谈、改写手册并在验证集上过门禁 → 运行 2 用学到的版本谈 B 组来访，同时用出发时的版本谈同一批作对照。
            </p>
          </div>
          <div className="pl-status">
            {data && <span className={`pl-pill pl-pill-${state}`}>{PIPELINE_STATE_LABEL[state]}</span>}
            {snap?.mode === 'mock' && <Badge tone="mock">演练 · 未调用模型</Badge>}
          </div>
        </div>

        {snap && (
          <div className="pl-clockrow">
            <dl className="pl-clock">
              <div>
                <dt>{state === 'done' ? '总用时' : '已用时间'}</dt>
                <dd className="tabular">{clock(elapsed)}</dd>
              </div>
              <div>
                <dt>预计剩余</dt>
                <dd className="tabular">{running ? clock(eta) : '—'}</dd>
              </div>
            </dl>
            <div className="pl-overall">
              <div
                className={`track pl-track${state === 'failed' ? ' track-failed' : ''}`}
                role="progressbar"
                aria-label="全链路整体进度（按预计时长估算）"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progress === null ? undefined : Math.round(progress * 100)}
              >
                <div className="track-fill" style={{ width: `${(progress ?? 0) * 100}%` }} />
              </div>
              <p className="pl-overall-note">
                <span className="mono">{snap.experiment_id}</span>
                <span>
                  手册 {snap.playbook.from_version}
                  {snap.playbook.current_version !== snap.playbook.from_version ? ` → ${snap.playbook.current_version}` : ''} · 计划学习 {snap.generations_planned} 代
                </span>
              </p>
            </div>
          </div>
        )}

        {error && data && (
          <p className="pl-conn" role="status">
            连接中断，正在重试
          </p>
        )}
      </section>

      {!data && !error && <Spinner label="正在读取全链路进度…" />}
      {!data && error && <ErrorNotice error={error} tone="warn" title="读不到全链路进度，正在重试" />}

      {snap?.state === 'failed' && (
        <Notice tone="danger" title="全链路没有走完">
          {snap.error ?? '后端未提供失败原因'}
        </Notice>
      )}
      {snap?.state === 'done' && (
        <Notice
          tone="ok"
          title="全链路已完成"
          action={
            <span className="pl-done-links">
              <a href={HREF.evolution}>查看进化记录</a>
              <a href={HREF.board}>回到进化看板</a>
            </span>
          }
        >
          运行 2 与对照的结果在下方。
        </Notice>
      )}

      {data && (
        <div className="pl-grid">
          <section className="pl-main" aria-labelledby="pl-steps-title">
            {/* 左栏：步骤，后面是逐代曲线。大屏上两者并排，让整页在 1920×1080 下不用滚动；窄一些时曲线落到步骤下面 */}
            <div className="pl-stepcol">
              <h2 id="pl-steps-title" className="pl-h2">
                步骤
              </h2>
              {snap && snap.steps.length > 0 ? (
                <Stepper steps={snap.steps} receivedAt={receivedAt} now={now} />
              ) : (
                <p className="empty">
                  还没有全链路实验。选好模式后点右侧的启动按钮{launcher?.enabled ? '' : '，或在终端执行 make demo-run1'}。开始后这里会列出全部步骤。
                </p>
              )}
            </div>
            <section className="pl-card pl-curve" aria-labelledby="pl-curve-title">
              <h2 id="pl-curve-title" className="pl-h2">
                逐代曲线
              </h2>
              <LiveGenerationCurve curve={snap?.curve ?? null} size="compact" />
            </section>
          </section>
          {launcher && <Launcher launcher={launcher} snap={snap} actions={actions} />}
          <Results snap={snap} />
          <details className="fold pl-log">
            <summary>运行日志</summary>
            <pre className="pl-logtext">{launcher && launcher.log_tail?.length ? launcher.log_tail.join('\n') : '（暂无输出）'}</pre>
          </details>
        </div>
      )}
    </div>
  );
}

// ---------- 启动控件 ----------

function Launcher({ launcher, snap, actions }: { launcher: PipelineLauncher; snap: PipelineSnapshot | null; actions: PipelineActions }) {
  const presets = orderPresets(launcher.presets);
  const [picked, setPicked] = useState<string | null>(null);
  const [mock, setMock] = useState(false);
  const [confirm, setConfirm] = useState<'launch' | 'stop' | null>(null);
  // 默认是“再进化一代”（后端提供时）；用户点过的优先
  const preset = presets.find((p) => p.key === picked) ?? defaultPreset(presets);
  const continuing = preset !== null && !isResetPreset(preset);
  const conflict = lineageConflict(launcher, preset, mock);

  const pipelineRunning = snap?.state === 'running';
  const ownRunning = launcher.enabled && launcher.state === 'running';
  const busy = actions.busy !== null;
  const canStart = launcher.enabled && !pipelineRunning && !ownRunning && preset !== null && !busy && conflict === null;
  const mismatch = actions.error?.op === 'launch' && actions.error.error.code === 'LINEAGE_MODE_MISMATCH';

  // 状态变了（例如启动成功、进程退出）就收起确认框
  useEffect(() => setConfirm(null), [ownRunning]);

  return (
    <section className="pl-card pl-launch" aria-labelledby="pl-launch-title">
      <h2 id="pl-launch-title" className="pl-h2">
        {ownRunning ? '正在运行' : '启动'}
      </h2>

      {ownRunning ? (
        <div className="pl-running">
          <p>
            {presets.find((p) => p.key === launcher.preset)?.label ?? launcher.preset ?? '全链路'}
            {launcher.pid !== null && <span className="muted">（进程 {launcher.pid}）</span>}
          </p>
          <button type="button" className="btn btn-danger" disabled={busy} onClick={() => setConfirm('stop')}>
            {actions.busy === 'stop' ? '正在停止…' : '停止'}
          </button>
        </div>
      ) : (
        <>
          <fieldset className="pl-presets" disabled={!launcher.enabled || busy || pipelineRunning}>
            <legend className="sr-only">选择模式</legend>
            {presets.map((p) => (
              <label key={p.key} className={`pl-preset${preset?.key === p.key ? ' active' : ''}`}>
                <input type="radio" name="pl-preset" value={p.key} checked={preset?.key === p.key} onChange={() => setPicked(p.key)} />
                <span className="pl-preset-head">
                  <strong>{p.label}</strong>
                  <span className="muted">
                    学习 {p.generations} 代 · {aboutMinutes(p.expected_s)}
                  </span>
                </span>
                <span className={`pl-preset-from${isResetPreset(p) ? ' is-reset' : ''}`}>
                  {isResetPreset(p) ? RESET_TAG : continueFromText(launcher)}
                </span>
                <span className="pl-preset-desc">{p.description}</span>
              </label>
            ))}
            {presets.length === 0 && <p className="muted small">后端没有提供启动预设。</p>}
            <label className="pl-check">
              <input type="checkbox" checked={mock} onChange={(e) => setMock(e.target.checked)} />
              演练（不调用模型）
            </label>
          </fieldset>
          <button type="button" className="btn btn-primary pl-start" disabled={!canStart} onClick={() => setConfirm('launch')}>
            {actions.busy === 'launch' ? '正在启动…' : continuing ? '再进化一代' : '开始全链路'}
          </button>
          {launcher.enabled && conflict && !pipelineRunning && <p className="pl-note pl-conflict">{conflict}</p>}
          {!launcher.enabled && (
            <p className="pl-note">
              此后端未开启一键启动；请在终端执行 <code>make demo-run1</code>
            </p>
          )}
          {launcher.enabled && pipelineRunning && (
            <p className="pl-note">有一场全链路正在进行（不是从这个页面启动的），结束后才能再启动。</p>
          )}
        </>
      )}

      {confirm === 'launch' && preset && (
        <div className="pl-confirm" role="group" aria-label="确认开始">
          <p>{launchConfirmText(preset, launcher)}</p>
          <p className={mock ? 'muted' : 'pl-cost'}>
            {mock ? '演练模式不调用任何模型，不产生费用；会谈内容是模板生成的。' : '真实模式会调用模型 API，会产生费用。'}
          </p>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setConfirm(null);
                actions.launch({ preset: preset.key, mock });
              }}
            >
              确认开始
            </button>
            <button type="button" className="btn" onClick={() => setConfirm(null)}>
              取消
            </button>
          </div>
        </div>
      )}
      {confirm === 'stop' && (
        <div className="pl-confirm" role="group" aria-label="确认停止">
          <p>将终止正在运行的全链路子进程。已完成的步骤会保留，这次实验会记为失败（已手动停止）。</p>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                setConfirm(null);
                actions.stop();
              }}
            >
              确认停止
            </button>
            <button type="button" className="btn" onClick={() => setConfirm(null)}>
              继续运行
            </button>
          </div>
        </div>
      )}

      {actions.error && (
        <ErrorNotice
          error={actions.error.error}
          title={
            mismatch
              ? '没能启动：演练与真实不能接在同一条链上，请先从 v1 重新开始'
              : actions.error.op === 'launch'
                ? '没能启动'
                : '没能停止'
          }
          action={
            <button type="button" className="quiet-btn" onClick={actions.dismiss}>
              知道了
            </button>
          }
        />
      )}
    </section>
  );
}

// ---------- 步骤 ----------

const MARK: Record<PipelineStep['state'], string> = {
  pending: '',
  running: '',
  done: '✓',
  failed: '✕',
  skipped: '–',
};

function Stepper({ steps, receivedAt, now }: { steps: PipelineStep[]; receivedAt: number; now: number }) {
  // 用户手动展开 / 收起的记录；没有记录的步骤按状态决定（进行中、失败展开）
  const [manual, setManual] = useState<Record<string, boolean>>({});
  return (
    <ol className="pl-steps">
      {steps.map((step, i) => {
        const expandable = step.state !== 'pending';
        const open = expandable && (manual[step.key] ?? defaultOpen(step));
        return (
          <StepRow
            key={step.key}
            index={i + 1}
            step={step}
            open={open}
            expandable={expandable}
            onToggle={() => setManual((m) => ({ ...m, [step.key]: !open }))}
            receivedAt={receivedAt}
            now={now}
          />
        );
      })}
    </ol>
  );
}

function StepRow({
  index,
  step,
  open,
  expandable,
  onToggle,
  receivedAt,
  now,
}: {
  index: number;
  step: PipelineStep;
  open: boolean;
  expandable: boolean;
  onToggle: () => void;
  receivedAt: number;
  now: number;
}) {
  const live = step.state === 'running';
  const elapsed = tick(step.elapsed_s, receivedAt, now, live, 1);
  const eta = live ? tick(step.eta_s, receivedAt, now, true, -1) : null;
  const tally = stepSessions(step);
  const id = `pl-step-${step.key}`;

  const head = (
    <>
      <span className="pl-step-title">
        <strong>{step.label}</strong>
        <span className={`pl-step-state is-${step.state}`}>{STEP_STATE_LABEL[step.state]}</span>
      </span>
      <span className="pl-step-detail">{step.detail}</span>
      {!open && <span className="pl-step-summary">{stepSummary(step)}</span>}
    </>
  );

  return (
    <li className={`pl-step is-${step.state}`}>
      <span className="pl-marker" aria-hidden="true">
        {MARK[step.state] || (step.state === 'pending' ? index : '')}
      </span>
      <div className="pl-step-body">
        {expandable ? (
          <button type="button" className="pl-step-head" aria-expanded={open} aria-controls={id} onClick={onToggle}>
            {head}
            <span className="pl-chevron" aria-hidden="true" />
          </button>
        ) : (
          <div className="pl-step-head">{head}</div>
        )}

        {open && (
          <div className="pl-step-more" id={id}>
            <div className="pl-progress">
              <div className="pl-progress-line">
                <span>
                  {sessionsText(tally)}
                  {tally.failed > 0 && <span className="danger-text">（{tally.failed} 场出错）</span>}
                </span>
                <span className="pl-times tabular">
                  用时 {clock(elapsed)}
                  {live && <> · 预计剩余 {clock(eta)}</>}
                </span>
              </div>
              {tally.ratio !== null && <Bar ratio={tally.ratio} failed={step.state === 'failed'} label={`${step.label} 会谈进度`} />}
            </div>

            {step.kind === 'generation' && <GenerationView gen={step.generation ?? null} running={live} />}

            {step.batches.length > 0 && (
              <ul className="pl-batches" aria-label="批次">
                {step.batches.map((b) => (
                  <BatchRow key={b.run_id} batch={b} />
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function Bar({ ratio, failed = false, label }: { ratio: number; failed?: boolean; label: string }) {
  return (
    <div
      className={`track${failed ? ' track-failed' : ''}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(ratio * 100)}
    >
      <div className="track-fill" style={{ width: `${ratio * 100}%` }} />
    </div>
  );
}

function BatchRow({ batch: b }: { batch: PipelineBatch }) {
  const done = b.completed + b.failed;
  const ratio = b.total > 0 ? Math.min(1, done / b.total) : 0;
  return (
    <li className={`pl-batch is-${b.state}`}>
      <span className="pl-batch-label">{b.label}</span>
      <span className="pl-batch-meta mono">
        {b.version} · {b.split} 组
      </span>
      <Bar ratio={ratio} failed={b.state === 'failed'} label={`${b.label} 进度`} />
      <span className="pl-batch-count tabular">
        {b.completed}/{b.total}
        {b.failed > 0 && <span className="danger-text"> · 出错 {b.failed}</span>}
      </span>
      <span className="pl-batch-isi tabular">{b.isi_response_rate !== null ? `ISI ${rate(b.isi_response_rate)}` : b.state === 'failed' ? '失败' : ''}</span>
    </li>
  );
}

function GenerationView({ gen, running }: { gen: PipelineGeneration | null; running: boolean }) {
  if (!gen) return <p className="muted">{running ? '正在准备这一代的学习…' : '这一代没有记录。'}</p>;
  const sentence = outcomeSentence(gen);
  return (
    <div className="pl-gen">
      <div className="pl-gen-facts">
        <p>
          <span className="pl-k">反思器</span>
          <span className="mono">{gen.reflector?.model ?? '—'}</span>
          <span className="muted"> · {gen.reflector ? (gen.reflector.state === 'running' ? '反思中' : '已完成') : '尚未开始'}</span>
          {gen.reflector?.fell_back && <Badge tone="warn">已自动降级为备用模型</Badge>}
        </p>
        <p>
          <span className="pl-k">阶段</span>
          {gen.phase ? PHASE_LABEL[gen.phase] ?? gen.phase : '—'}
        </p>
        <p>
          <span className="pl-k">上一代基线</span>
          {gen.from_version} · ISI 有效率 <b className="tabular">{rate(gen.baseline_isi)}</b>
        </p>
        {sentence && <p className={`pl-outcome is-${gen.outcome}`}>{sentence}</p>}
      </div>
      <div className="table-wrap">
        <table className="table pl-cands">
          <thead>
            <tr>
              <th scope="col">候选</th>
              <th scope="col">状态</th>
              <th scope="col">ISI 有效率</th>
              <th scope="col">门禁</th>
            </tr>
          </thead>
          <tbody>
            {gen.candidates.map((c) => (
              <tr key={c.id} className={gen.chosen === c.id ? 'pl-chosen' : undefined}>
                <td className="mono">{c.id}</td>
                <td>{CANDIDATE_STATE_LABEL[c.state] ?? c.state}</td>
                <td className="tabular">{rate(c.isi)}</td>
                <td>{c.passed === null ? '—' : c.passed ? <span className="pl-pass">通过</span> : <span className="pl-fail">未通过</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- 结果 ----------

function Results({ snap }: { snap: PipelineSnapshot | null }) {
  const result = snap?.result ?? null;
  const from = snap?.playbook.from_version ?? 'v1';
  const current = snap?.playbook.current_version ?? from;
  const delta = deltaPoints(result);
  const run2Version = result?.run2?.playbook_version ?? (current !== from ? current : '新版本');
  return (
    <section className="pl-results" aria-labelledby="pl-results-title">
      <h2 id="pl-results-title" className="pl-h2">
        结果
      </h2>
      <div className="pl-cards">
        <ResultCard title="运行 1" sub={`${result?.run1?.playbook_version ?? from} · A 组`} r={result?.run1 ?? null} />
        <ResultCard title="对照" sub={`${result?.control?.playbook_version ?? from} · B 组`} r={result?.control ?? null} tone="base" />
        <ResultCard title="运行 2" sub={`${run2Version} · B 组`} r={result?.run2 ?? null} tone="lead">
          <p className={`pl-delta${delta !== null && delta > 0 ? ' up' : delta !== null && delta < 0 ? ' down' : ''}`}>
            比对照 <b className="tabular">{signedPoints(delta)}</b>
          </p>
        </ResultCard>
      </div>
      <p className="pl-fine">ISI 为规则状态模型的四周模拟值，所有来访均为模拟数据。</p>
    </section>
  );
}

function ResultCard({
  title,
  sub,
  r,
  tone,
  children,
}: {
  title: string;
  sub: string;
  r: PipelineRunResult | null;
  tone?: 'base' | 'lead';
  children?: ReactNode;
}) {
  return (
    <article className={`pl-result${tone ? ` is-${tone}` : ''}`}>
      <h3>
        {title}
        <span className="muted">（{sub}）</span>
      </h3>
      {r ? (
        <>
          <p className="pl-metric">
            <span className="pl-k">ISI 有效率</span>
            <b className="tabular">{rate(r.isi_response_rate)}</b>
          </p>
          <p className="pl-submetric tabular">
            转介召回 {rate(r.referral_recall)} / 精确率 {rate(r.referral_precision)}
            <span className="muted"> · {r.n} 位来访</span>
          </p>
        </>
      ) : (
        <p className="pl-metric pl-none">
          <span className="pl-k">ISI 有效率</span>
          <b>尚未生成</b>
        </p>
      )}
      {children}
    </article>
  );
}
