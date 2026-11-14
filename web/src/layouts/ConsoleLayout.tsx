import type { ReactNode } from 'react';
import type { HealthResponse } from '../api/draftTypes';
import { DataSourceBanner } from '../components/DataSourceBanner';
import { HealthBar } from '../components/HealthBar';
import type { AdapterKind } from '../config';
import { HREF, type ConsoleRoute } from '../hooks/useHashRoute';
import type { ResourceState } from '../hooks/useResource';

const NAV: { key: ConsoleRoute['name'][]; href: string; label: string }[] = [
  { key: ['console-runs', 'console-session'], href: HREF.runs, label: '运行与报告' },
  { key: ['console-visitors'], href: HREF.visitors, label: '模拟来访' },
  { key: ['console-evolution'], href: HREF.evolution, label: '进化记录' },
  { key: ['console-debug'], href: HREF.debug, label: '调试' },
];

export function Moon({ size = 22 }: { size?: number }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <path d="M20 4a12 12 0 1 0 8 20A10 10 0 0 1 20 4z" fill="currentColor" />
    </svg>
  );
}

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
  const mode = health.status === 'ok' ? health.data.execution_mode : null;
  return (
    <div className="app console">
      <header className="topbar">
        <a className="brand" href={HREF.runs}>
          <Moon />
          <span>
            deepsleep <span className="brand-sub">控制台</span>
          </span>
        </a>
        <div className="topbar-right">
          <HealthBar adapter={adapter} health={health} onRetry={onRetryHealth} />
          <a className="btn btn-ghost btn-sm" href={HREF.chat}>
            用户端演示 →
          </a>
        </div>
      </header>

      <DataSourceBanner adapter={adapter} mode={mode} />

      <div className="console-body">
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
        <main className="main console-main">{children}</main>
      </div>

      <footer className="footer">
        所有来访均为模拟数据。页面展示的是干预路径与生活方式建议，不能替代专业医疗意见；如有需要，请建议就医。
      </footer>
    </div>
  );
}
