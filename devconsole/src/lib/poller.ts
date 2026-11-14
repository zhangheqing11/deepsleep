// 串行轮询：上一个请求结束后才安排下一个，请求不会堆积。
// 每次请求有单次超时；stop() 会取消在途请求并不再安排；失败按退避重试。
// 连续失败达到阈值标为 stale（断连 / 数据过期），但保留上次成功的数据并继续重试。
// 到达终态（isTerminal）或遇到不该重试的错误（shouldStop）就停止。
// 计时器和时钟可注入，便于在测试里重放。

import { ApiError, isAbortError, toApiError } from '../api/errors';

export interface PollSnapshot<T> {
  data: T | null;
  error: ApiError | null;
  /** 连续失败次数，成功后清零 */
  failures: number;
  /** 最近一次成功的本机时间（毫秒） */
  lastSuccessAt: number | null;
  /** 连续失败达到阈值：断连 / 数据过期 */
  stale: boolean;
  /** 已到终态或因错误停止，不再请求 */
  done: boolean;
  /** 是否有请求在途 */
  inFlight: boolean;
}

export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

export interface PollerOptions<T> {
  fetch: (signal: AbortSignal) => Promise<T>;
  /** 成功后的下一次间隔 */
  intervalMs: number;
  timeoutMs: number;
  /** 失败后的退避，依次使用，最后一个值重复 */
  backoffMs: number[];
  staleAfter: number;
  isTerminal?: (data: T) => boolean;
  /** 返回 true 表示不再重试（例如 404 运行不存在） */
  shouldStop?: (error: ApiError) => boolean;
  /** 返回自定义重试间隔（例如 409 报告未就绪），null 表示按退避 */
  retryDelay?: (error: ApiError, failures: number) => number | null;
  onUpdate: (snap: PollSnapshot<T>) => void;
  timers?: Timers;
  now?: () => number;
}

const defaultTimers: Timers = {
  setTimeout: (fn, ms) => globalThis.setTimeout(fn, ms),
  clearTimeout: (h) => globalThis.clearTimeout(h as ReturnType<typeof setTimeout>),
};

export function backoffFor(backoffMs: number[], failures: number): number {
  if (backoffMs.length === 0) return 1000;
  return backoffMs[Math.min(Math.max(failures - 1, 0), backoffMs.length - 1)];
}

export class SerialPoller<T> {
  private snap: PollSnapshot<T> = {
    data: null,
    error: null,
    failures: 0,
    lastSuccessAt: null,
    stale: false,
    done: false,
    inFlight: false,
  };
  private stopped = false;
  private timer: unknown = null;
  private controller: AbortController | null = null;
  private readonly timers: Timers;
  private readonly now: () => number;

  constructor(private readonly opts: PollerOptions<T>) {
    this.timers = opts.timers ?? defaultTimers;
    this.now = opts.now ?? (() => Date.now());
  }

  get snapshot(): PollSnapshot<T> {
    return this.snap;
  }

  start(): void {
    if (this.stopped || this.snap.inFlight || this.timer !== null) return;
    void this.tick();
  }

  /** 取消在途请求和下一次安排；之后不会再回调 onUpdate。 */
  stop(): void {
    this.stopped = true;
    if (this.timer !== null) this.timers.clearTimeout(this.timer);
    this.timer = null;
    this.controller?.abort();
    this.controller = null;
  }

  /** 立即重试（例如用户点“重新连接”）；有请求在途时忽略。 */
  retryNow(): void {
    if (this.stopped || this.snap.inFlight) return;
    if (this.timer !== null) this.timers.clearTimeout(this.timer);
    this.timer = null;
    this.snap = { ...this.snap, done: false };
    void this.tick();
  }

  private emit(patch: Partial<PollSnapshot<T>>) {
    this.snap = { ...this.snap, ...patch };
    if (!this.stopped) this.opts.onUpdate(this.snap);
  }

  private schedule(ms: number) {
    if (this.stopped) return;
    this.timer = this.timers.setTimeout(() => {
      this.timer = null;
      void this.tick();
    }, ms);
  }

  private async tick(): Promise<void> {
    if (this.stopped) return;
    const controller = new AbortController();
    this.controller = controller;
    let timedOut = false;
    const timeout = this.timers.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, this.opts.timeoutMs);
    this.emit({ inFlight: true });

    try {
      const data = await this.opts.fetch(controller.signal);
      this.timers.clearTimeout(timeout);
      if (this.stopped) return;
      const terminal = this.opts.isTerminal ? this.opts.isTerminal(data) : false;
      this.emit({
        data,
        error: null,
        failures: 0,
        stale: false,
        lastSuccessAt: this.now(),
        inFlight: false,
        done: terminal,
      });
      if (!terminal) this.schedule(this.opts.intervalMs);
    } catch (e) {
      this.timers.clearTimeout(timeout);
      if (this.stopped) return;
      let error: ApiError;
      if (timedOut) {
        error = new ApiError({ kind: 'network', message: `请求超过 ${this.opts.timeoutMs} 毫秒未响应` });
      } else if (isAbortError(e)) {
        return;
      } else {
        error = toApiError(e);
      }
      const failures = this.snap.failures + 1;
      const stop = this.opts.shouldStop?.(error) ?? false;
      this.emit({
        error,
        failures,
        stale: failures >= this.opts.staleAfter,
        inFlight: false,
        done: stop,
      });
      if (!stop) this.schedule(this.opts.retryDelay?.(error, failures) ?? backoffFor(this.opts.backoffMs, failures));
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }
}
