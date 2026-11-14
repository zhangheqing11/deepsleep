import type { ReactNode } from 'react';
import { HREF, type UserRoute } from '../hooks/useHashRoute';
import { Moon } from './ConsoleLayout';

/**
 * 用户端外壳：页头与底部导航固定，中间区域由各页面自己安排滚动。
 * “演示 · 未接模型”始终可见；详细说明点开才显示。
 */
export function AppLayout({ route, children }: { route: UserRoute; children: ReactNode }) {
  return (
    <div className="user-app">
      <div className="phone">
        <header className="phone-top">
          <Moon size={22} />
          <div className="phone-title">
            <h1>deepsleep</h1>
            <p className="small muted">睡前，慢慢聊</p>
          </div>
          <details className="demo-tag">
            <summary>演示 · 未接模型</summary>
            <div className="demo-tag-panel" role="note">
              <p>这是交互演示：回复是固定示例，没有连接模型，也没有经过安全层。</p>
              <p>偏好和“我记住的事”只保存在这台设备的浏览器里，不会上传。</p>
            </div>
          </details>
        </header>

        <div className="phone-body">{children}</div>

        <nav className="tabbar" aria-label="用户端导航">
          <a
            href={HREF.chat}
            className={route.name === 'app-chat' ? 'active' : ''}
            aria-current={route.name === 'app-chat' ? 'page' : undefined}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path d="M4 5h16v11H8l-4 4z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
            </svg>
            聊一聊
          </a>
          <a
            href={HREF.settings}
            className={route.name === 'app-settings' ? 'active' : ''}
            aria-current={route.name === 'app-settings' ? 'page' : undefined}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path d="M4 7h10M18 7h2M4 17h4M12 17h8" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
              <circle cx="16" cy="7" r="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
              <circle cx="10" cy="17" r="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
            </svg>
            我的
          </a>
        </nav>
      </div>
    </div>
  );
}
