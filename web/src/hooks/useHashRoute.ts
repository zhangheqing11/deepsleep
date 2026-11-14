import { useEffect, useState } from 'react';

// 三套界面共用一个 hash 路由：
//   #/             进化看板（评委看的首页；未知地址也回到这里）
//   #/console/...  开发者控制台
//   #/app/...      用户端交互演示
// 旧链接 #/runs/:id/sessions/:vid 仍然可用。

export type ConsoleRoute =
  | { name: 'console-runs' }
  | { name: 'console-session'; runId: string; visitorId: string }
  | { name: 'console-visitors' }
  | { name: 'console-evolution' }
  | { name: 'console-debug' };

export type UserRoute = { name: 'app-chat' } | { name: 'app-settings' };

export type BoardRoute = { name: 'board' };

export type Route = BoardRoute | ConsoleRoute | UserRoute;

function safeDecode(s: string): string | null {
  try {
    return decodeURIComponent(s);
  } catch {
    return null;
  }
}

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, '').replace(/\/+$/, '') || '/';

  const session = path.match(/^(?:\/console)?\/runs\/([^/]+)\/sessions\/([^/]+)$/);
  if (session) {
    const runId = safeDecode(session[1]);
    const visitorId = safeDecode(session[2]);
    if (runId && visitorId) return { name: 'console-session', runId, visitorId };
  }

  switch (path) {
    case '/console':
    case '/console/runs':
      return { name: 'console-runs' };
    case '/console/visitors':
      return { name: 'console-visitors' };
    case '/console/evolution':
      return { name: 'console-evolution' };
    case '/console/debug':
      return { name: 'console-debug' };
    case '/app':
    case '/app/chat':
      return { name: 'app-chat' };
    case '/app/settings':
      return { name: 'app-settings' };
    default:
      return { name: 'board' };
  }
}

export const HREF = {
  board: '#/',
  runs: '#/console',
  visitors: '#/console/visitors',
  evolution: '#/console/evolution',
  debug: '#/console/debug',
  chat: '#/app/chat',
  settings: '#/app/settings',
};

export function sessionHref(runId: string, visitorId: string): string {
  return `#/console/runs/${encodeURIComponent(runId)}/sessions/${encodeURIComponent(visitorId)}`;
}

export function isUserRoute(r: Route): r is UserRoute {
  return r.name === 'app-chat' || r.name === 'app-settings';
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseRoute(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
