import { useState, type FormEvent } from 'react';
import { signIn, type SignedOutReason } from '../api/auth';
import { describeError, toApiError } from '../api/errors';
import { Moon } from '../components/TopBar';

const REASON: Record<SignedOutReason, string | null> = {
  required: null,
  expired: '登录已失效，请重新登录。',
  left: '已退出登录。',
};

/** 后端开启登录（API_AUTH_MODE=demo）时，进化后台先过这里。账号由启动后端的人设置，这里不提供注册。 */
export function LoginPage({ reason }: { reason: SignedOutReason }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(username.trim(), password);
    } catch (err) {
      const api = toApiError(err);
      setError(api.code === 'INVALID_CREDENTIALS' ? '账号或密码不对。' : `登录没有成功：${describeError(api)}`);
      setBusy(false);
    }
  }

  const note = REASON[reason];
  return (
    <main className="login">
      <form className="login-card" onSubmit={submit}>
        <div className="login-brand">
          <Moon />
          <span>deepsleep 进化后台</span>
        </div>
        <h1>登录</h1>
        <p className="login-sub">只读展示，需要先用演示账号登录才能读取实验数据。</p>
        {note && !error && (
          <p className="login-note" role="status">
            {note}
          </p>
        )}
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <label className="login-field">
          <span>账号</span>
          <input
            name="username"
            autoComplete="username"
            autoFocus
            required
            maxLength={64}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label className="login-field">
          <span>密码</span>
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={256}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button type="submit" className="login-submit" disabled={busy || !username.trim() || !password}>
          {busy ? '正在登录…' : '登录'}
        </button>
        <p className="login-fine">登录状态只保存在这个标签页里；账号由启动后端的人设置。</p>
      </form>
    </main>
  );
}
