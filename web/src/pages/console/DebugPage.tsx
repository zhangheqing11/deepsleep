import { useState } from 'react';
import type { HealthResponse } from '../../api/draftTypes';
import { describeError } from '../../api/errors';
import { requestLog, useRequestLog } from '../../api/requestLog';
import { Badge, Card, KeyValue, Notice } from '../../components/common';
import { API_ADAPTER, API_BASE_URL, CONTRACTS_VERSION, POLL_INTERVAL_MS } from '../../config';
import type { ConsoleRunState } from '../../hooks/useConsoleRun';
import type { ResourceState } from '../../hooks/useResource';
import { ms } from '../../lib/format';

export function CopyButton({ value, label = '复制' }: { value: string; label?: string }) {
  const [done, setDone] = useState<'idle' | 'ok' | 'fail'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setDone('ok');
    } catch {
      setDone('fail');
    }
    window.setTimeout(() => setDone('idle'), 1500);
  };
  return (
    <button type="button" className="btn btn-ghost btn-sm" onClick={copy} aria-label={`${label} ${value}`}>
      {done === 'ok' ? '已复制' : done === 'fail' ? '复制失败' : label}
    </button>
  );
}

export function DebugPage({
  state,
  health,
}: {
  state: ConsoleRunState;
  health: ResourceState<HealthResponse>;
}) {
  const log = useRequestLog();
  const { runId, run, poller } = state;

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <h1>调试与日志</h1>
          <p className="muted">把网络错误与执行失败分开排查。</p>
        </div>
      </div>
      <Card title="服务与配置">
        <KeyValue
          items={[
            ['数据来源', API_ADAPTER === 'mock' ? '前端本地模拟适配器' : '后端 HTTP'],
            ['API 基础地址', <span className="mono">{API_BASE_URL}</span>],
            ['轮询间隔', ms(POLL_INTERVAL_MS)],
            ['前端对照的契约版本', CONTRACTS_VERSION],
            [
              '服务状态',
              health.status === 'ok' ? (
                <span className="tags">
                  <Badge tone="ok">{health.data.status}</Badge>
                  <Badge>{health.data.execution_mode}</Badge>
                  {health.data.contracts_version && <Badge>{`契约 ${health.data.contracts_version}`}</Badge>}
                </span>
              ) : health.status === 'error' ? (
                <Badge tone="danger">{describeError(health.error)}</Badge>
              ) : (
                '检查中…'
              ),
            ],
          ]}
        />
      </Card>

      <Card title="当前运行">
        {runId ? (
          <KeyValue
            items={[
              [
                'run_id',
                <span className="tags">
                  <span className="mono">{runId}</span>
                  <CopyButton value={runId} />
                </span>,
              ],
              ['运行状态', run?.status ?? '—'],
              ['轮询', poller.polling ? '进行中' : poller.stop ? `已停止（${poller.stop}）` : '未开始'],
              ['最近一次查询失败', poller.transientError ? describeError(poller.transientError) : '无'],
              ['运行错误', run?.error ? `${run.error.code}：${run.error.message}` : '无'],
            ]}
          />
        ) : (
          <p className="muted">没有选中的运行。</p>
        )}
      </Card>

      <Card
        title="请求记录"
        aside={
          <button type="button" className="btn btn-ghost btn-sm" onClick={requestLog.clear}>
            清空
          </button>
        }
      >
        <p className="small muted">
          只保存在当前页面内存里（最近 60 条），刷新即清空。“网络”表示没连上后端；“HTTP”表示后端返回了错误；“取消”是切换页面时主动中止，不算失败。
        </p>
        {log.length === 0 ? (
          <Notice tone="neutral" title="还没有请求" />
        ) : (
          <div className="table-wrap" tabIndex={0} aria-label="请求记录">
            <table className="table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>接口</th>
                  <th>对象</th>
                  <th>结果</th>
                  <th>耗时</th>
                  <th>request_id</th>
                </tr>
              </thead>
              <tbody>
                {log.map((e) => (
                  <tr key={e.seq}>
                    <td className="nowrap">{new Date(e.at).toLocaleTimeString('zh-CN', { hour12: false })}</td>
                    <td className="mono">{e.op}</td>
                    <td className="mono">{e.target || '—'}</td>
                    <td>
                      {e.ok ? (
                        <Badge tone="ok">{e.status ? `成功 ${e.status}` : '成功'}</Badge>
                      ) : e.aborted ? (
                        <Badge>取消</Badge>
                      ) : (
                        <span className="tags">
                          <Badge tone={e.kind === 'network' ? 'warn' : 'danger'}>
                            {e.kind === 'network' ? '网络' : e.kind === 'http' ? `HTTP ${e.status ?? ''}` : e.kind}
                          </Badge>
                          {e.code && <span className="mono small">{e.code}</span>}
                        </span>
                      )}
                    </td>
                    <td className="nowrap">{ms(e.duration_ms)}</td>
                    <td>
                      {e.request_id ? (
                        <span className="tags">
                          <span className="mono small">{e.request_id}</span>
                          <CopyButton value={e.request_id} />
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
