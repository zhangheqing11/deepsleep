// 四套界面共用的顶栏：左上角品牌（一律回到进化看板）+ 当前界面名称，以及界面切换。
// 界面切换在每个界面都是同样的四项、同样的顺序和文字；当前界面高亮。
// 各界面自己的局部导航（控制台侧栏、来访页标签、用户视角底栏）不放跨界面的链接。
import { HREF, type Route } from '../hooks/useHashRoute';

export type Surface = 'board' | 'app' | 'me' | 'console';

export interface SurfaceEntry {
  key: Surface;
  /** 界面切换里的文字 */
  label: string;
  /** 品牌旁边显示的界面名称 */
  title: string;
  href: string;
}

export const SURFACES: readonly SurfaceEntry[] = [
  { key: 'board', label: '进化看板', title: '进化看板', href: HREF.board },
  { key: 'app', label: '来访视角', title: '来访视角', href: HREF.app },
  { key: 'me', label: '用户视角', title: '用户视角', href: HREF.me },
  { key: 'console', label: '控制台', title: '开发者控制台', href: HREF.console },
];

export function surfaceOf(route: Route): Surface {
  if (route.name === 'board') return 'board';
  if (route.name === 'me') return 'me';
  if (route.name === 'app-home' || route.name === 'app-visitor') return 'app';
  return 'console';
}

export function surfaceTitle(surface: Surface): string {
  return SURFACES.find((s) => s.key === surface)!.title;
}

export function Moon({ size = 22 }: { size?: number }) {
  return (
    <svg className="mark" viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <path d="M20 4a12 12 0 1 0 8 20A10 10 0 0 1 20 4z" fill="currentColor" />
    </svg>
  );
}

/** 品牌：每个界面都指向进化看板 */
export function BrandLink({ className = 'sf-brand' }: { className?: string }) {
  return (
    <a className={className} href={HREF.board} title="回到进化看板">
      <Moon size={20} />
      <span>deepsleep</span>
    </a>
  );
}

/** 品牌旁边的界面名称 */
export function SurfaceName({ surface }: { surface: Surface }) {
  return <span className="sf-name">{surfaceTitle(surface)}</span>;
}

/** 界面切换：四项固定，当前界面 aria-current="page" */
export function SurfaceNav({ current }: { current: Surface }) {
  return (
    <nav className="sf-nav" aria-label="界面切换">
      {SURFACES.map((s) => {
        const active = s.key === current;
        return (
          <a key={s.key} href={s.href} className={active ? 'sf-item active' : 'sf-item'} aria-current={active ? 'page' : undefined}>
            {s.label}
          </a>
        );
      })}
    </nav>
  );
}
