import { useEffect } from 'react';
import { HREF } from '../../hooks/useHashRoute';
import { useChat, type AssistantItem, type UserItem } from '../../hooks/useChat';

const NOT_FIT_REASONS = ['太长', '不符合我的作息', '想先被听见'];

function FeedbackBar({ item, onChange }: { item: AssistantItem; onChange: (f: AssistantItem['feedback']) => void }) {
  const f = item.feedback;
  if (f?.value === 'useful') {
    return <div className="feedback small muted">已记录“有用”（仅本次演示，不会改变回复方式）</div>;
  }
  return (
    <div className="feedback">
      {!f && (
        <>
          <button type="button" className="link-btn" onClick={() => onChange({ value: 'useful', reasons: [] })}>
            有用
          </button>
          <span className="muted" aria-hidden="true">·</span>
          <button type="button" className="link-btn" onClick={() => onChange({ value: 'not_fit', reasons: [] })}>
            不太适合
          </button>
        </>
      )}
      {f?.value === 'not_fit' && (
        <div className="feedback-reasons">
          <span className="small muted">哪里不太适合？（可多选）</span>
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
          <span className="small muted">已记录（仅本次演示，不会改变回复方式）</span>
        </div>
      )}
    </div>
  );
}

function SuggestionCard({
  item,
  onAction,
}: {
  item: AssistantItem;
  onAction: (a: 'accept' | 'dismiss' | 'swap') => void;
}) {
  const sg = item.suggestion;
  if (!sg) return null;
  if (sg.state === 'dismissed') return <div className="small muted chat-note">已收起这条建议</div>;
  return (
    <div className={`suggestion ${sg.state === 'accepted' ? 'accepted' : ''}`}>
      <div className="small muted">今晚的一个小建议</div>
      <strong>{sg.s.title}</strong>
      <p>{sg.s.body}</p>
      {sg.state === 'accepted' ? (
        <div className="small ok-text">已加入今晚的约定</div>
      ) : (
        <div className="btn-row">
          <button type="button" className="btn btn-sm btn-primary-soft" onClick={() => onAction('accept')}>
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

function MemoryCard({ item, onAction }: { item: AssistantItem; onAction: (a: 'confirm' | 'decline') => void }) {
  const m = item.memory;
  if (!m) return null;
  if (m.state === 'declined') return <div className="small muted chat-note">好的，这件事不记住</div>;
  return (
    <div className="memory-card">
      {m.state === 'confirmed' ? (
        <>
          <div className="small ok-text">已记住（可在“我的”里修改或删除）</div>
          <strong>{m.c.text}</strong>
        </>
      ) : (
        <>
          <div className="small muted">要记住这件事吗？</div>
          <strong>“{m.c.text}”</strong>
          <div className="small muted">
            来源：本次对话{m.c.valid_days ? ` · ${m.c.valid_days} 天内有效` : ''}
          </div>
          <div className="btn-row">
            <button type="button" className="btn btn-sm btn-primary-soft" onClick={() => onAction('confirm')}>
              记住
            </button>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => onAction('decline')}>
              不用
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function UserBubble({ item, onRetry, onRemove }: { item: UserItem; onRetry: () => void; onRemove: () => void }) {
  return (
    <li className={`msg msg-user ${item.status}`}>
      <div className="msg-bubble">{item.text}</div>
      <div className="msg-status small">
        {item.status === 'sending' && <span className="muted">发送中…</span>}
        {item.status === 'sent' && <span className="muted">已送达</span>}
        {item.status === 'failed' && (
          <span className="failed-row">
            <span className="danger-text">发送失败</span>
            <button type="button" className="link-btn" onClick={onRetry}>
              重试
            </button>
            <button type="button" className="link-btn muted" onClick={onRemove}>
              删除
            </button>
          </span>
        )}
      </div>
    </li>
  );
}

export function ChatPage() {
  const chat = useChat();
  const userSent = chat.items.some((i) => i.kind === 'user' && i.status === 'sent');

  useEffect(() => {
    // 滚到页面最底部：此时吸底的输入区回到正常位置，不会遮住最后一条消息
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: reduce ? 'auto' : 'smooth' });
  }, [chat.items.length, chat.waiting, chat.ended]);

  return (
    <div className="chat-page">
      <ol className="msgs" aria-live="polite">
        {chat.items.map((item) =>
          item.kind === 'user' ? (
            <UserBubble
              key={item.id}
              item={item}
              onRetry={() => chat.retry(item.id)}
              onRemove={() => chat.removeFailed(item.id)}
            />
          ) : (
            <li key={item.id} className="msg msg-assistant">
              <div className="msg-bubble">{item.text}</div>
              {item.id !== 'reply_opening' && (
                <FeedbackBar item={item} onChange={(f) => chat.setFeedback(item.id, f)} />
              )}
              <SuggestionCard item={item} onAction={(a) => chat.suggestionAction(item.id, a)} />
              <MemoryCard item={item} onAction={(a) => chat.memoryAction(item.id, a)} />
            </li>
          ),
        )}
        {chat.waiting && (
          <li className="msg msg-assistant">
            <div className="msg-bubble typing" aria-label="正在回复">
              <span />
              <span />
              <span />
            </div>
          </li>
        )}
      </ol>

      {chat.ended ? (
        <section className="wrap-card" aria-label="今晚的约定">
          <strong>今晚先到这里</strong>
          {chat.accepted.length + chat.remembered.length === 0 ? (
            <p className="muted">今晚没有定下约定也没关系，好好休息。</p>
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
          <button type="button" className="btn btn-sm" onClick={chat.restart}>
            开始新的对话
          </button>
        </section>
      ) : (
        <>
          <div className="composer">
            {chat.quickReplies.length > 0 && (
              <div className="presets" role="group" aria-label="选择一条消息发送">
                {chat.quickReplies.map((p) => (
                  <button key={p.id} type="button" className="preset" onClick={() => chat.send(p)}>
                    {p.text}
                  </button>
                ))}
              </div>
            )}
            <div className="composer-row">
              <div className="composer-input" aria-disabled="true">
                演示版只能选择上面的消息；自由输入需等聊天接口与安全层接入
              </div>
            </div>
          </div>
          {userSent && (
            <button type="button" className="btn btn-ghost btn-sm end-btn" onClick={chat.end} disabled={chat.waiting}>
              今晚先到这里
            </button>
          )}
          <details className="demo-controls">
            <summary className="small muted">演示控制</summary>
            <label className="small">
              <input type="checkbox" checked={chat.failNext} onChange={(e) => chat.setFailNext(e.target.checked)} />{' '}
              下一条消息模拟发送失败
            </label>
            <div className="small muted">
              记住的事可在 <a href={HREF.settings}>我的</a> 里查看。
            </div>
          </details>
        </>
      )}
    </div>
  );
}
