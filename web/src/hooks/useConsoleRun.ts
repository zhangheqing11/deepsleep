import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { CreateRunResponse } from '../api/draftTypes';
import { currentRunStore, runHistoryStore, type RunHistoryEntry, type SavedRun } from '../lib/storage';
import { useCreateRun } from './useCreateRun';
import { useReport, useSessionList } from './useRunData';
import { useResource } from './useResource';
import { useRunPoller } from './useRunPoller';

function loadSavedRun(): SavedRun | null {
  const saved = currentRunStore.get();
  // 不同数据来源的运行编号互不通用
  return saved && saved.adapter === api.adapter ? saved : null;
}

/**
 * 控制台的“当前运行”状态。放在控制台外壳里，切换控制台页面（含会谈详情）时轮询不中断。
 */
export function useConsoleRun() {
  const [saved, setSaved] = useState<SavedRun | null>(loadSavedRun);
  const [history, setHistory] = useState<RunHistoryEntry[]>(() => runHistoryStore.list(api.adapter));
  const runId = saved?.run_id ?? null;

  const refreshHistory = useCallback(() => setHistory(runHistoryStore.list(api.adapter).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))), []);

  const poller = useRunPoller(runId, () => {
    currentRunStore.clear();
    if (runId) {
      runHistoryStore.upsert({ run_id: runId, adapter: api.adapter, status: 'not_found' });
      refreshHistory();
    }
  });
  // 切换运行的那一次渲染里，poller 还拿着上一个运行的状态；只采用 run_id 一致的状态，
  // 避免用旧状态提前为新运行请求报告和会谈列表
  const run = poller.run && poller.run.run_id === runId ? poller.run : null;
  const terminal = run?.status === 'succeeded' || run?.status === 'failed';
  const remoteHistory = useResource(`runs:${runId ?? ''}:${run?.status ?? ''}`, (signal) => api.listRuns(50, signal));
  const serverHistory: RunHistoryEntry[] | null = remoteHistory.status === 'ok' ? remoteHistory.data.items.map((item) => ({
    run_id: item.run_id, adapter: api.adapter, created_at: item.created_at, split: item.split ?? '',
    playbook_version: item.playbook_version, status: item.status === 'completed' ? 'succeeded' : item.status,
  })) : null;
  useEffect(() => {
    if (remoteHistory.status === 'ok') {
      runHistoryStore.cache(api.adapter, remoteHistory.data.items.map((item) => ({
        run_id: item.run_id, adapter: api.adapter, created_at: item.created_at, split: item.split ?? '',
        playbook_version: item.playbook_version, status: item.status === 'completed' ? 'succeeded' : item.status,
      })));
      refreshHistory();
    }
  }, [remoteHistory.status === 'ok' ? remoteHistory.data : null, refreshHistory]);

  const report = useReport(runId, Boolean(run?.report_available));
  const sessions = useSessionList(runId, terminal);

  // 拿到后端的运行状态后，用实际的分组、版本、状态更新本机历史
  useEffect(() => {
    if (!run) return;
    runHistoryStore.upsert({
      run_id: run.run_id,
      adapter: api.adapter,
      split: run.split,
      playbook_version: run.playbook_version,
      status: run.status,
    });
    refreshHistory();
  }, [run?.run_id, run?.status, run?.playbook_version, run?.split, refreshHistory]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectRun = useCallback((id: string) => {
    const next: SavedRun = { run_id: id, adapter: api.adapter, saved_at: new Date().toISOString() };
    currentRunStore.set(next);
    setSaved(next);
  }, []);

  const onCreated = useCallback(
    (res: CreateRunResponse) => {
      runHistoryStore.upsert({ run_id: res.run_id, adapter: api.adapter, status: res.status });
      refreshHistory();
      selectRun(res.run_id);
    },
    [refreshHistory, selectRun],
  );
  const create = useCreateRun(onCreated);

  const clearRun = useCallback(() => {
    currentRunStore.clear();
    setSaved(null);
  }, []);

  const forgetRun = useCallback(
    (id: string) => {
      runHistoryStore.remove(api.adapter, id);
      refreshHistory();
      if (id === runId) clearRun();
    },
    [runId, clearRun, refreshHistory],
  );

  const busy = Boolean(runId) && poller.stop === null && !terminal;

  const sessionVisitors = useMemo(() => {
    if (sessions.status !== 'ok') return new Set<string>();
    return new Set(sessions.data.items.filter((i) => i.session_available).map((i) => i.visitor_id));
  }, [sessions]);

  return {
    runId,
    poller,
    run,
    terminal,
    busy,
    report,
    sessions,
    sessionVisitors,
    create,
    history: serverHistory ?? (remoteHistory.status === 'error' ? history : []),
    historyResource: remoteHistory,
    historyFromServer: serverHistory !== null,
    selectRun,
    clearRun,
    forgetRun,
  };
}

export type ConsoleRunState = ReturnType<typeof useConsoleRun>;
