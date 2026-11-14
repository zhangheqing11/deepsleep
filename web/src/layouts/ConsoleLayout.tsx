import type { ReactNode } from 'react';
import type { HealthResponse } from '../api/draftTypes';
import { HealthBar } from '../components/HealthBar';
import type { AdapterKind } from '../config';
import { HREF, type ConsoleRoute } from '../hooks/useHashRoute';
import type { ResourceState } from '../hooks/useResource';

const NAV: { key: ConsoleRoute['name'][]; href: string; label: string }[] = [
  { key: ['console-runs', 'console-session'], href: HREF.runs, label: '运行与报告' },
  { key: ['console-visitors'], href: HREF.visitors, label: '模拟来访' },
  { key: ['console-evolution'], href: HREF.evolution, label: '进化记录' },
  { key: ['console-debug'], href: HREF.debug, label: '调试与日志' },
];

export function Moon({ size = 22 }: { size?: number }) {
  return (
    <svg className="mark" viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <path d="M20 4a12 12 0 1 0 8 20A10 10 0 0 1 20 4z" fill="currentColor" />
    </svg>
  );
}

/** 控制台外壳：灰绿窄侧栏 + 一整块连续的白色工作区 */
export function ConsoleLayout({
  route,
  adapter,
  health,
  onRetryHealth,
  children,
}: {
  route: ConsoleRoute;
  adapter: AdapterKind;
  health: ResourceState<HealthResponse>;
  onRetryHealth: () => void;
  children: ReactNode;
}) {
  return (
    <div className="console">
      <a className="console-brand" href={HREF.runs}>
        <Moon size={20} />
        <span>deepsleep</span>
      </a>
      <header className="console-bar">
        <span className="small muted">开发者控制台</span>
        <div className="row">
          <HealthBar adapter={adapter} health={health} onRetry={onRetryHealth} />
          <a className="quiet-link small" href={HREF.chat}>
            用户端演示 →
          </a>
        </div>
      </header>
      <nav className="console-nav" aria-label="控制台导航">
        {NAV.map((n) => {
          const active = n.key.includes(route.name);
          return (
            <a key={n.href} href={n.href} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}>
              {n.label}
            </a>
          );
        })}
      </nav>
      <main className="console-sheet">
        {children}
        <p className="sheet-foot small muted">
          所有来访均为模拟数据。页面展示的是干预路径与生活方式建议，不能替代专业医疗意见；如有需要，请建议就医。
        </p>
      </main>
    </div>
  );
}
