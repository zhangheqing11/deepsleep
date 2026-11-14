import { useEffect } from 'react';
import { api } from './api';
import { SessionView } from './components/SessionView';
import { useConsoleRun } from './hooks/useConsoleRun';
import { isUserRoute, useHashRoute, type ConsoleRoute } from './hooks/useHashRoute';
import { useHealth } from './hooks/useRunData';
import { ConsoleLayout } from './layouts/ConsoleLayout';
import { applyAppearance, useAppearance } from './lib/appearance';
import { BoardPage } from './pages/board/BoardPage';
import { UserApp } from './pages/app/UserApp';
import { DebugPage } from './pages/console/DebugPage';
import { EvolutionPage } from './pages/console/EvolutionPage';
import { RunsPage } from './pages/console/RunsPage';
import { VisitorsPage } from './pages/console/VisitorsPage';

function ConsoleApp({ route }: { route: ConsoleRoute }) {
  const health = useHealth();
  const state = useConsoleRun();
  const mode = health.status === 'ok' ? health.data.execution_mode : null;
  const healthOk = health.status === 'ok';
  const healthChecked = health.status === 'ok' || health.status === 'error';

  let page;
  switch (route.name) {
    case 'console-session':
      page = <SessionView runId={route.runId} visitorId={route.visitorId} adapter={api.adapter} mode={mode} />;
      break;
    case 'console-visitors':
      page = <VisitorsPage state={state} />;
      break;
    case 'console-evolution':
      page = <EvolutionPage />;
      break;
    case 'console-debug':
      page = <DebugPage state={state} health={health} />;
      break;
    default:
      page = <RunsPage state={state} healthOk={healthOk} healthChecked={healthChecked} healthMode={mode} />;
  }

  return (
    <ConsoleLayout route={route} adapter={api.adapter} health={health} onRetryHealth={health.reload}>
      {page}
    </ConsoleLayout>
  );
}

export function App() {
  const route = useHashRoute();
  const appearance = useAppearance();

  // 外观偏好对三套界面都生效
  useEffect(() => {
    applyAppearance(appearance);
  }, [appearance]);

  if (route.name === 'board') return <BoardPage />;
  return isUserRoute(route) ? <UserApp route={route} /> : <ConsoleApp route={route} />;
}
