import { useState, type FormEvent } from 'react';
import { registrationProblem, signIn, signUp, type AuthState } from '../../api/auth';
import { describeError, toApiError, type ApiError } from '../../api/errors';
import { HREF } from '../../hooks/useHashRoute';
import { Moon } from '../../components/SurfaceNav';
import '../../login.css';

const REASON: Record<Extract<AuthState, { state: 'signed-out' }>['reason'], string | null> = {
  required: null,
  expired: '登录已失效，请重新登录。',
  left: '已退出登录。',
};

type Mode = 'login' | 'register';

function explain(mode: Mode, e: ApiError): string {
  if (e.code === 'INVALID_CREDENTIALS') return '账号或密码不对。';
  if (e.code === 'USERNAME_TAKEN') return '这个账号已经有人用了，换一个试试。';
  if (e.code === 'REGISTRATION_FULL') return '演示账号的数量到上限了，请用已有的账号登录。';
  if (mode === 'register' && e.status === 422) return '账号用 3–32 位字母、数字或 _ . -，密码至少 6 位。';
  if (mode === 'register' && (e.status === 404 || e.status === 405)) return '这台后端还不支持注册，请用已有的账号登录。';
  return `${mode === 'register' ? '注册' : '登录'}没有成功：${describeError(e)}`;
}

/** 登录与注册：后端开启登录（API_AUTH_MODE=demo）时，所有界面都要先过这里。 */
export function LoginPage({ reason, initialMode = 'login' }: { reason: keyof typeof REASON; initialMode?: Mode }) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const registering = mode === 'register';

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const name = username.trim();
    if (registering) {
      const problem = registrationProblem(name, password);
      if (problem) return setError(problem);
    }
    setBusy(true);
    setError(null);
    try {
      if (registering) {
        await signUp(name, password, displayName);
        // 新注册的人直接进入用户视角
        window.location.hash = HREF.me;
      } else {
        await signIn(name, password);
      }
    } catch (err) {
      setError(explain(mode, toApiError(err)));
      setBusy(false);
    }
  }

  function switchTo(next: Mode) {
    setMode(next);
    setError(null);
    setPassword('');
  }

  return (
    <div className="lg">
      <main className="lg-card">
        <div className="lg-brand">
          <Moon size={22} />
          <span>deepsleep</span>
        </div>
        <h1>{registering ? '注册' : '登录'}</h1>
        <p className="lg-sub">会自己改写 playbook 的睡眠管家</p>
        {!registering && REASON[reason] && !error && <p className="lg-note" role="status">{REASON[reason]}</p>}
        <form onSubmit={submit} noValidate>
          {registering && (
            <label className="lg-field">
              <span>怎么称呼你（可不填）</span>
              <input name="display_name" autoComplete="nickname" value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={20} />
            </label>
          )}
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
              maxLength={registering ? 32 : 64}
            />
            {registering && <span className="lg-hint">3–32 位字母、数字或 _ . -</span>}
          </label>
          <label className="lg-field">
            <span>密码</span>
            <input
              name="password"
              type="password"
              autoComplete={registering ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              maxLength={256}
            />
            {registering && <span className="lg-hint">至少 6 位。请不要用你在别处用的密码。</span>}
          </label>
          {error && <p className="lg-error" role="alert">{error}</p>}
          <button type="submit" className="lg-submit" disabled={busy || !username.trim() || !password}>
            {busy ? (registering ? '正在注册…' : '正在登录…') : registering ? '注册并进入' : '登录'}
          </button>
        </form>
        <p className="lg-switch">
          {registering ? '已经有账号？' : '第一次来？'}
          <button type="button" onClick={() => switchTo(registering ? 'login' : 'register')}>{registering ? '去登录' : '注册一个演示账号'}</button>
        </p>
        <p className="lg-fine">
          {registering
            ? '这是演示账号：只存在后端的内存里，后端一重启就清空。注册后你会以一位模拟来访的身份体验，不会收集你的睡眠或健康信息。'
            : '登录状态只保存在这个标签页里。'}
        </p>
      </main>
      <footer className="lg-foot">所有来访均为模拟数据。页面展示的是建议与干预路径，不能替代专业医疗意见。</footer>
    </div>
  );
}
