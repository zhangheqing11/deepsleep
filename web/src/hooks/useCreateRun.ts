import { useCallback, useRef, useState } from 'react';
import { api } from '../api';
import type { BackendMockScenario, CreateRunRequest, CreateRunResponse } from '../api/draftTypes';
import { ApiError, toApiError } from '../api/errors';
import { newIdempotencyKey, pendingCreateStore, type PendingCreate } from '../lib/storage';

/**
 * 创建运行，处理 Idempotency-Key：
 * - 用户点“开始运行”= 新操作，生成新 key；
 * - 网络失败或 5xx 时保留 key（存 sessionStorage，刷新也在），“重试提交”复用同一个 key；
 * - 收到明确的 2xx / 4xx 后清掉。
 */
export function useCreateRun(onCreated: (res: CreateRunResponse) => void) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState<PendingCreate | null>(() => {
    const p = pendingCreateStore.get();
    return p && p.adapter === api.adapter ? p : null;
  });
  const inFlight = useRef(false);

  const send = useCallback(
    async (p: PendingCreate) => {
      if (inFlight.current) return;
      inFlight.current = true;
      setSubmitting(true);
      setError(null);
      try {
        const res = await api.createRun(p.body, p.idempotency_key, undefined, p.mock_scenario);
        pendingCreateStore.clear();
        setPending(null);
        onCreated(res);
      } catch (e) {
        const err = toApiError(e);
        setError(err);
        if (!err.isTransient) {
          pendingCreateStore.clear();
          setPending(null);
        }
      } finally {
        inFlight.current = false;
        setSubmitting(false);
      }
    },
    [onCreated],
  );

  /** 用户明确发起一次新运行；mockScenario 只在后端为 Mock 时传入 */
  const start = useCallback(
    (body: CreateRunRequest, mockScenario?: BackendMockScenario) => {
      const p: PendingCreate = {
        idempotency_key: newIdempotencyKey(),
        body,
        ...(mockScenario ? { mock_scenario: mockScenario } : {}),
        adapter: api.adapter,
        first_attempt_at: new Date().toISOString(),
      };
      pendingCreateStore.set(p);
      setPending(p);
      void send(p);
    },
    [send],
  );

  /** 重试上一次未确认的提交，沿用同一个 key */
  const retry = useCallback(() => {
    if (pending) void send(pending);
  }, [pending, send]);

  const discard = useCallback(() => {
    pendingCreateStore.clear();
    setPending(null);
    setError(null);
  }, []);

  return { submitting, error, pending, start, retry, discard };
}
