import type { ListResponse, SessionListItem } from '../api/draftTypes';
import { sessionHref } from '../hooks/useHashRoute';
import type { ResourceState } from '../hooks/useResource';
import { RUN_STATUS_LABEL, SESSION_STATUS_LABEL } from '../lib/labels';
import { Badge, Card, ErrorNotice, Spinner } from './common';

export function SessionList({
  runId,
  state,
  onReload,
}: {
  runId: string;
  state: ResourceState<ListResponse<SessionListItem>>;
  onReload: () => void;
}) {
  return (
    <Card
      title="会谈记录"
      aside={
        <button type="button" className="btn btn-ghost btn-sm" onClick={onReload}>
          刷新
        </button>
      }
    >
      <p className="small muted">每个来访一次会谈，含第 1 轮与第 2 轮对话。只读展示评测记录，不是实时聊天。</p>
      {state.status === 'loading' && <Spinner label="正在读取会谈列表…" />}
      {state.status === 'error' && <ErrorNotice error={state.error} title="会谈列表读取失败" />}
      {state.status === 'ok' &&
        (state.data.items.length === 0 ? (
          <p className="muted">暂无会谈记录。</p>
        ) : (
          <ul className="session-list">
            {state.data.items.map((item) => (
              <li key={item.visitor_id}>
                {item.session_available ? (
                  <a className="session-item" href={sessionHref(runId, item.visitor_id)}>
                    <SessionItemBody item={item} />
                    <span className="chevron" aria-hidden="true">›</span>
                  </a>
                ) : (
                  <div className="session-item disabled">
                    <SessionItemBody item={item} />
                    <span className="small muted">无记录</span>
                  </div>
                )}
              </li>
            ))}
          </ul>
        ))}
    </Card>
  );
}

function SessionItemBody({ item }: { item: SessionListItem }) {
  return (
    <span className="session-item-body">
      <span className="mono">{item.visitor_id}</span>
      <span className="tags">
        <Badge tone={item.status === 'failed' ? 'danger' : item.status === 'succeeded' ? 'ok' : 'neutral'}>
          {RUN_STATUS_LABEL[item.status]}
        </Badge>
        {item.session_status && (
          <Badge tone={item.session_status === 'crisis_exit' ? 'danger' : item.session_status === 'error' ? 'warn' : 'neutral'}>
            {SESSION_STATUS_LABEL[item.session_status]}
          </Badge>
        )}
      </span>
    </span>
  );
}
