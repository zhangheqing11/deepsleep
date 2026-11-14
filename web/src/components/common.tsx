import type { ReactNode } from 'react';
import { ApiError, describeError } from '../api/errors';

export type Tone = 'neutral' | 'info' | 'ok' | 'warn' | 'danger' | 'mock';

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Card({
  title,
  aside,
  children,
  className = '',
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || aside) && (
        <header className="card-head">
          {title && <h2>{title}</h2>}
          {aside && <div className="card-aside">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Notice({
  tone,
  title,
  children,
  action,
}: {
  tone: Tone;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <div className="notice-body">
        <strong>{title}</strong>
        {children && <div className="notice-text">{children}</div>}
      </div>
      {action && <div className="notice-action">{action}</div>}
    </div>
  );
}

/** 展示错误：中文说明 + 错误码 + request_id（供排查），不展示堆栈 */
export function ErrorNotice({
  error,
  title,
  tone = 'danger',
  action,
}: {
  error: ApiError;
  title?: string;
  tone?: Tone;
  action?: ReactNode;
}) {
  const meta = [error.status ? `HTTP ${error.status}` : null, error.code ?? null].filter(Boolean).join(' · ');
  return (
    <Notice tone={tone} title={title ?? describeError(error)} action={action}>
      {title && <div>{describeError(error)}</div>}
      {error.kind === 'http' && error.message && error.message !== describeError(error) && (
        <div className="small">{error.message}</div>
      )}
      {error.details && error.details.length > 0 && (
        <ul className="plain-list">
          {error.details.map((d, i) => (
            <li key={i}>{d.field ? `${d.field}：${d.message}` : d.message}</li>
          ))}
        </ul>
      )}
      {(meta || error.requestId) && (
        <div className="mono small muted">
          {meta}
          {error.requestId && <> · request_id: {error.requestId}</>}
        </div>
      )}
    </Notice>
  );
}

export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (
        <div key={i} className="kv-row">
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="spinner-row" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
