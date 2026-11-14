import { describeError } from '../../api/errors';
import { EvolutionBoard } from '../../components/board/Board';
import { SignOutButton } from '../../components/SignOutButton';
import { useBoard } from '../../hooks/useBoard';
import { BrandLink, SurfaceName, SurfaceNav } from '../../components/SurfaceNav';
import { EMPTY_BOARD } from '../../lib/board';
import { isDark, setThemeChoice, useAppearance } from '../../lib/appearance';
import '../../board.css';

function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false });
}

function ThemeToggle() {
  const dark = isDark(useAppearance());
  return (
    <button type="button" className="bd-link" onClick={() => setThemeChoice(dark ? 'light' : 'dark')}>
      {dark ? '切到浅色' : '切到深色'}
    </button>
  );
}

/** 评委看的进化看板：应用首页，只读，随实验阶段自动更新。 */
export function BoardPage() {
  const { data, error, updatedAt, reload } = useBoard();
  return (
    <div className="bd">
      <header className="bd-bar">
        <div className="sf-left">
          <BrandLink className="bd-brand" />
          <SurfaceName surface="board" />
          <SurfaceNav current="board" />
        </div>
        <div className="bd-bar-right" aria-live="polite">
          {data?.mock && <span className="bd-pill bd-pill-warning">模拟数据，不代表真实学习效果</span>}
          {error && updatedAt !== null && (
            <span className="bd-pill bd-pill-negative">连接中断，显示的是 {clock(updatedAt)} 的数据</span>
          )}
          {!error && updatedAt !== null && <span className="bd-fresh">更新于 {clock(updatedAt)}</span>}
          <ThemeToggle />
          <SignOutButton className="bd-link" />
        </div>
      </header>
      <main className="bd-main">
        {data === null && error ? (
          <div className="bd-body">
            <div className="bd-title">
              <div>
                <h1>进化实验</h1>
                <p className="bd-finding bd-finding-negative" role="alert">后端不可用：{describeError(error)}。页面会自动重试。</p>
              </div>
              <button type="button" className="bd-button" onClick={reload}>立即重试</button>
            </div>
          </div>
        ) : (
          <EvolutionBoard data={data ?? EMPTY_BOARD} loading={data === null} />
        )}
      </main>
      <footer className="bd-foot">
        所有来访均为模拟数据。页面展示的是干预路径与生活方式建议，不能替代专业医疗意见；如有需要，请建议就医。
      </footer>
    </div>
  );
}
