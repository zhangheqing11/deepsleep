import type { DataMode } from '../lib/settings';
import { EXECUTION_MODE_LABEL, label } from '../lib/labels';
import { clockMs } from '../lib/format';
import type { PollSnapshot } from '../lib/poller';
import { signOut, useAuth } from '../api/auth';
import { Badge } from './common';

export function Moon({ size = 22 }: { size?: number }) {
  return (
    <svg className="mark" viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <path d="M20 4a12 12 0 1 0 8 20A10 10 0 0 1 20 4z" fill="currentColor" />
    </svg>
  );
}

/** 三件事分开显示：数据从哪来、连接状态、模型实际执行模式。连通不等于真实模型运行过。 */
export function TopBar({
  mode,
  fixtureLabel,
  connection,
  executionModes,
}: {
  mode: DataMode;
  fixtureLabel: string | null;
  connection: PollSnapshot<unknown> | null;
  executionModes: (string | null)[];
}) {
  return (
    <header className="topbar">
      <div className="brand">
        <Moon />
        <span>deepsleep 进化后台</span>
        <small>只读展示</small>
      </div>
      <div className="topbar-status">
        <SourceBadge mode={mode} fixtureLabel={fixtureLabel} />
        {mode === 'http' && connection && <ConnectionBadge snap={connection} />}
        <ExecutionBadge modes={executionModes} />
        <SignOutButton />
      </div>
    </header>
  );
}

function SourceBadge({ mode, fixtureLabel }: { mode: DataMode; fixtureLabel: string | null }) {
  if (mode === 'mock') return <Badge tone="mock">数据来源：模拟数据{fixtureLabel ? ` · ${fixtureLabel}` : ''}</Badge>;
  if (mode === 'http') return <Badge tone="info">数据来源：实时后端</Badge>;
  return <Badge tone="warn">数据来源：回放（不可用）</Badge>;
}

export function ConnectionBadge({ snap }: { snap: PollSnapshot<unknown> }) {
  if (snap.stale) {
    return (
      <Badge tone="danger">
        断连 · 数据过期{snap.lastSuccessAt !== null ? `（最后更新 ${clockMs(snap.lastSuccessAt)}）` : '（从未连上）'}
      </Badge>
    );
  }
  if (snap.lastSuccessAt === null) {
    return <Badge tone="warn">{snap.error ? `连接失败，重试中（${snap.failures} 次）` : '连接中…'}</Badge>;
  }
  return (
    <Badge tone={snap.error ? 'warn' : 'ok'}>
      {snap.error ? `请求失败，重试中 · 上次更新 ${clockMs(snap.lastSuccessAt)}` : `已连接 · 更新于 ${clockMs(snap.lastSuccessAt)}`}
    </Badge>
  );
}

function ExecutionBadge({ modes }: { modes: (string | null)[] }) {
  const known = Array.from(new Set(modes.filter((m): m is string => m !== null)));
  if (modes.length === 0) return <Badge>执行模式：暂无运行</Badge>;
  if (known.length === 0) return <Badge tone="warn">执行模式：后端未提供</Badge>;
  const text = known.map((m) => label(EXECUTION_MODE_LABEL, m)).join(' / ');
  return <Badge tone={known.every((m) => m === 'real') ? 'ok' : 'mock'}>执行模式：{text}</Badge>;
}

/** 已登录时显示“退出登录”；后端没开登录或使用模拟数据时什么都不渲染。 */
function SignOutButton() {
  const auth = useAuth();
  if (auth.state !== 'signed-in') return null;
  return (
    <button type="button" className="signout" onClick={() => void signOut()}>
      退出登录（{auth.user.display_name}）
    </button>
  );
}
