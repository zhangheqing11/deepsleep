import { useEffect, useState } from 'react';

export type Route =
  | { name: 'home' }
  | { name: 'session'; runId: string; visitorId: string };

function parse(hash: string): Route {
  const m = hash.match(/^#\/runs\/([^/]+)\/sessions\/([^/]+)\/?$/);
  if (m) {
    try {
      return { name: 'session', runId: decodeURIComponent(m[1]), visitorId: decodeURIComponent(m[2]) };
    } catch {
      return { name: 'home' };
    }
  }
  return { name: 'home' };
}

export function sessionHref(runId: string, visitorId: string): string {
  return `#/runs/${encodeURIComponent(runId)}/sessions/${encodeURIComponent(visitorId)}`;
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}
