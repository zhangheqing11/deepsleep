import { useState, type FormEvent } from 'react';
import { signIn, type AuthState } from '../../api/auth';
import { describeError, toApiError } from '../../api/errors';
import { Moon } from '../../layouts/ConsoleLayout';
import '../../login.css';

const REASON: Record<Extract<AuthState, { state: 'signed-out' }>['reason'], string | null> = {
  required: null,
  expired: '登录已失效，请重新登录。',
  left: '已退出登录。',
};

/** 登录页：后端开启登录（API_AUTH_MODE=demo）时，三套界面都要先过这里。 */
export function LoginPage({ reason }: { reason: keyof typeof REASON }) {
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

  return (
    <div className="lg">
      <main className="lg-card">
        <div className="lg-brand">
          <Moon size={22} />
          <span>deepsleep</span>
        </div>
        <h1>登录</h1>
        <p className="lg-sub">会自己改写 playbook 的睡眠管家</p>
        {REASON[reason] && !error && <p className="lg-note" role="status">{REASON[reason]}</p>}
        <form onSubmit={submit} noValidate>
          <label className="lg-field">
            <span>账号</span>
            <input
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              maxLength={64}
            />
          </label>
          <label className="lg-field">
            <span>密码</span>
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              maxLength={256}
            />
          </label>
          {error && <p className="lg-error" role="alert">{error}</p>}
          <button type="submit" className="lg-submit" disabled={busy || !username.trim() || !password}>
            {busy ? '正在登录…' : '登录'}
          </button>
        </form>
        <p className="lg-fine">这是本地演示账号，由启动后端的人设置；没有注册入口。登录状态只保存在这个标签页里。</p>
      </main>
      <footer className="lg-foot">所有来访均为模拟数据。页面展示的是建议与干预路径，不能替代专业医疗意见。</footer>
    </div>
  );
}
