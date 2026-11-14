import type { ReactNode } from 'react';
import type { HealthResponse } from '../api/draftTypes';
import { DataSourceBanner } from '../components/DataSourceBanner';
import { HealthBar } from '../components/HealthBar';
import { DevconsoleNavLink } from '../components/console/DevconsoleNavLink';
import { SignOutButton } from '../components/SignOutButton';
import { BrandLink, SurfaceName, SurfaceNav } from '../components/SurfaceNav';
import type { AdapterKind } from '../config';
import { HREF, type ConsoleRoute } from '../hooks/useHashRoute';
import type { ResourceState } from '../hooks/useResource';

/** 控制台侧栏：只放控制台自己的页面；跨界面的切换在顶栏 */
export const CONSOLE_NAV: { key: ConsoleRoute['name'][]; href: string; label: string }[] = [
  { key: ['console-pipeline'], href: HREF.pipeline, label: '全链路演示' },
  { key: ['console-runs', 'console-session'], href: HREF.runs, label: '运行与报告' },
  { key: ['console-visitors'], href: HREF.visitors, label: '模拟来访' },
  { key: ['console-evolution'], href: HREF.evolution, label: '进化记录' },
  { key: ['console-debug'], href: HREF.debug, label: '调试与日志' },
];

/** 控制台外壳：窄侧栏 + 一整块连续的白色工作区 */
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
      <BrandLink className="console-brand" />
      <header className="console-bar">
        <div className="sf-left">
          <SurfaceName surface="console" />
          <SurfaceNav current="console" />
        </div>
        <div className="row">
          <HealthBar adapter={adapter} health={health} onRetry={onRetryHealth} />
          <SignOutButton className="quiet-btn small" />
        </div>
      </header>
      <nav className="console-nav" aria-label="控制台导航">
        {CONSOLE_NAV.map((n) => {
          const active = n.key.includes(route.name);
          return (
            <a key={n.href + n.label} href={n.href} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}>
              {n.label}
            </a>
          );
        })}
        <div className="nav-sep" role="presentation" />
        <DevconsoleNavLink />
      </nav>
      <main className="console-sheet">
        <DataSourceBanner adapter={adapter} mode={health.status === 'ok' ? health.data.execution_mode : null} unavailable={health.status === 'error'} />
        {children}
        <p className="sheet-foot small muted">
          所有来访均为模拟数据。页面展示的是干预路径与生活方式建议，不能替代专业医疗意见；如有需要，请建议就医。
        </p>
      </main>
    </div>
  );
}
