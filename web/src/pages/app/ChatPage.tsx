import { useEffect, useRef, useState } from 'react';
import { useChat, type AssistantItem, type UserItem } from '../../hooks/useChat';

const NOT_FIT_REASONS = ['太长', '不符合我的作息', '想先被听见'];

/** 反馈默认收起成一个低对比入口，点开才出现选项 */
function Feedback({ item, onChange }: { item: AssistantItem; onChange: (f: AssistantItem['feedback']) => void }) {
  const [open, setOpen] = useState(false);
  const f = item.feedback;

  if (f?.value === 'useful') return <p className="feedback-done">已记录“有用”</p>;
  if (!open && !f) {
    return (
      <button type="button" className="quiet-btn" aria-expanded="false" onClick={() => setOpen(true)}>
        反馈
      </button>
    );
  }
  return (
    <div className="feedback">
      {!f ? (
        <div className="row">
          <button type="button" className="quiet-btn" onClick={() => onChange({ value: 'useful', reasons: [] })}>
            有用
          </button>
          <button type="button" className="quiet-btn" onClick={() => onChange({ value: 'not_fit', reasons: [] })}>
            不太适合
          </button>
          <button type="button" className="quiet-btn" onClick={() => setOpen(false)} aria-label="收起反馈">
            收起
          </button>
        </div>
      ) : (
        <>
          <span className="small muted">哪里不太适合？可多选</span>
          <div className="chips">
            {NOT_FIT_REASONS.map((r) => {
              const on = f.reasons.includes(r);
              return (
                <button
                  key={r}
                  type="button"
                  className={on ? 'chip active' : 'chip'}
                  aria-pressed={on}
                  onClick={() =>
                    onChange({ value: 'not_fit', reasons: on ? f.reasons.filter((x) => x !== r) : [...f.reasons, r] })
                  }
                >
                  {r}
                </button>
              );
            })}
          </div>
          <span className="small muted">已记录，只用于本次演示，不会改变回复方式。</span>
        </>
      )}
    </div>
  );
}

function SuggestionNote({ item, onAction }: { item: AssistantItem; onAction: (a: 'accept' | 'dismiss' | 'swap') => void }) {
  const sg = item.suggestion;
  if (!sg) return null;
  if (sg.state === 'dismissed') return <p className="small muted">已收起这条建议。</p>;
  return (
    <div className={`side-note ${sg.state === 'accepted' ? 'done' : ''}`}>
      <span className="small muted">{sg.state === 'accepted' ? '已加入今晚的约定' : '今晚的一个小建议'}</span>
      <strong className="side-note-title">{sg.s.title}</strong>
      <p>{sg.s.body}</p>
      {sg.state === 'open' && (
        <div className="row">
          <button type="button" className="btn btn-sm btn-primary" onClick={() => onAction('accept')}>
            想试试
          </button>
          {sg.s.alternative_id && (
            <button type="button" className="btn btn-sm" onClick={() => onAction('swap')}>
              换一种
            </button>
          )}
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => onAction('dismiss')}>
            暂时不用
          </button>
        </div>
      )}
    </div>
  );
}

function MemoryNote({ item, onAction }: { item: AssistantItem; onAction: (a: 'confirm' | 'decline') => void }) {
  const m = item.memory;
  if (!m) return null;
  if (m.state === 'declined') return <p className="small muted">好的，这件事暂时不记住。</p>;
  if (m.state === 'confirmed') {
    return (
      <div className="side-note done">
        <span className="small muted">已记住，可在“我的”里修改或删除</span>
        <p>{m.c.text}</p>
      </div>
    );
  }
  return (
    <div className="side-note">
      <span className="small muted">要为你记住吗？</span>
      <p>{m.c.text}</p>
      <span className="small muted">来自本次对话{m.c.valid_days ? ` · ${m.c.valid_days} 天内有效` : ''}</span>
      <div className="row">
        <button type="button" className="btn btn-sm" onClick={() => onAction('confirm')}>
          记住这件事
        </button>
        <button type="button" className="btn btn-sm btn-ghost" onClick={() => onAction('decline')}>
          暂时不用
        </button>
      </div>
    </div>
  );
}

function UserMessage({ item, onRetry, onRemove }: { item: UserItem; onRetry: () => void; onRemove: () => void }) {
  return (
    <li className={`msg msg-user ${item.status}`}>
      <div className="msg-bubble">{item.text}</div>
      {item.status === 'sending' && <span className="msg-status small muted">发送中…</span>}
      {item.status === 'failed' && (
        <span className="msg-status small" role="alert">
          <span className="danger-text">没有发出去</span>
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            重试
          </button>
          <button type="button" className="quiet-btn" onClick={onRemove}>
            删除
          </button>
        </span>
      )}
    </li>
  );
}

export function ChatPage() {
  const chat = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);
  const userSent = chat.items.some((i) => i.kind === 'user' && i.status === 'sent');

  // 消息区独立滚动：有新内容时滚到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? 'auto' : 'smooth' });
  }, [chat.items, chat.waiting, chat.ended]);

  return (
    <div className="chat-page">
      <div className="chat-scroll" ref={scrollRef}>
        <p className="small muted">示例对话 · 未连接模型</p>
        <ol className="msgs" role="log" aria-live="polite">
          {chat.items.map((item) =>
            item.kind === 'user' ? (
              <UserMessage
                key={item.id}
                item={item}
                onRetry={() => chat.retry(item.id)}
                onRemove={() => chat.removeFailed(item.id)}
              />
            ) : (
              <li key={item.id} className="msg msg-assistant">
                <p className="msg-text">{item.text}</p>
                <SuggestionNote item={item} onAction={(a) => chat.suggestionAction(item.id, a)} />
                <MemoryNote item={item} onAction={(a) => chat.memoryAction(item.id, a)} />
                {item.id !== 'reply_opening' && (
                  <Feedback item={item} onChange={(f) => chat.setFeedback(item.id, f)} />
                )}
              </li>
            ),
          )}
          {chat.waiting && (
            <li className="msg msg-assistant">
              <span className="typing" aria-label="正在回复">
                <span />
                <span />
                <span />
              </span>
            </li>
          )}
        </ol>

        {chat.ended && (
          <section className="side-note done wrap-up" aria-label="今晚的约定">
            <strong className="side-note-title">今晚先到这里</strong>
            {chat.accepted.length + chat.remembered.length === 0 ? (
              <p>今晚没有定下约定也没关系，好好休息。</p>
            ) : (
              <ul className="plain-list">
                {chat.accepted.map((s) => (
                  <li key={s.id}>{s.title}</li>
                ))}
                {chat.remembered.map((t) => (
                  <li key={t}>已记住：{t}</li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>

      <div className="chat-footer">
        {chat.ended ? (
          <button type="button" className="btn btn-primary btn-block" onClick={chat.restart}>
            开始新的对话
          </button>
        ) : (
          <>
            <div className="chat-footer-head">
              <span className="small muted">选择一条示例消息</span>
              {userSent && (
                <button type="button" className="quiet-btn" onClick={chat.end} disabled={chat.waiting}>
                  今晚先到这里
                </button>
              )}
            </div>
            <div className="presets" role="group" aria-label="示例消息">
              {chat.quickReplies.length > 0 ? (
                chat.quickReplies.map((p) => (
                  <button key={p.id} type="button" className="preset" onClick={() => chat.send(p)}>
                    {p.text}
                  </button>
                ))
              ) : (
                <span className="small muted">
                  {chat.waiting ? '等待回复…' : '先处理上面没发出去的消息'}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
