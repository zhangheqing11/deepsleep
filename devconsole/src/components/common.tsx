// 部分复制自 web/src/components/common.tsx（main@0732150，2026-11-14）。

import type { ReactNode } from 'react';
import { ApiError, describeError } from '../api/errors';

export type Tone = 'neutral' | 'info' | 'ok' | 'warn' | 'danger' | 'mock';

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Notice({ tone, title, children, action }: { tone: Tone; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <div>
        <strong>{title}</strong>
        {children && <div className="notice-text">{children}</div>}
      </div>
      {action && <div className="notice-action">{action}</div>}
    </div>
  );
}

/** 错误说明 + 错误码 + request_id；结构不符时给出字段路径。不展示堆栈。 */
export function errorText(e: ApiError): string {
  const parts = [describeError(e)];
  if (e.kind === 'invalid_response' || (e.kind === 'network' && e.message)) parts.push(e.message);
  if (e.code) parts.push(`错误码 ${e.code}`);
  if (e.requestId) parts.push(`request_id ${e.requestId}`);
  return parts.join(' · ');
}

/** 尚未生成 / 暂无 的统一空态 */
export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}
