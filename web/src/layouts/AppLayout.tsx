import type { ReactNode } from 'react';
import { HREF, type UserRoute } from '../hooks/useHashRoute';
import { Moon } from './ConsoleLayout';

export function AppLayout({ route, children }: { route: UserRoute; children: ReactNode }) {
  return (
    <div className="user-app">
      <div className="phone">
        <header className="phone-top">
          <a className="brand" href={HREF.chat}>
            <Moon size={20} />
            <span>deepsleep</span>
          </a>
          <span className="badge badge-mock">交互演示</span>
        </header>

        <div className="demo-strip" role="note">
          <span>固定示例内容，未连接模型。所有数据只保存在这台设备的浏览器里。</span>
          <a href={HREF.runs}>开发者控制台</a>
        </div>

        <main className="phone-main">{children}</main>

        <nav className="tabbar" aria-label="用户端导航">
          <a href={HREF.chat} className={route.name === 'app-chat' ? 'active' : ''} aria-current={route.name === 'app-chat' ? 'page' : undefined}>
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <path d="M4 5h16v11H8l-4 4z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            </svg>
            聊一聊
          </a>
          <a href={HREF.settings} className={route.name === 'app-settings' ? 'active' : ''} aria-current={route.name === 'app-settings' ? 'page' : undefined}>
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
              <circle cx="12" cy="8" r="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
              <path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
            我的
          </a>
        </nav>
      </div>
    </div>
  );
}
