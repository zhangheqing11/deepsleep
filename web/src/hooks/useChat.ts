import { useCallback, useEffect, useRef, useState } from 'react';
import { chatDemo, type MemoryCandidate, type Preset, type Suggestion } from '../api/chatDemo';
import { isAbortError } from '../api/errors';
import { newIdempotencyKey, readJson, removeKey, writeJson } from '../lib/storage';
import { demoFlags, getSavedPreferences, memories } from '../lib/userDemoStore';

export type UserItem = {
  kind: 'user';
  /** 即 client_message_id，重试时沿用 */
  id: string;
  preset_id: string;
  text: string;
  status: 'sending' | 'sent' | 'failed';
};

export type AssistantItem = {
  kind: 'assistant';
  id: string;
  text: string;
  quick_replies: Preset[];
  feedback: { value: 'useful' | 'not_fit'; reasons: string[] } | null;
  suggestion: { s: Suggestion; state: 'open' | 'accepted' | 'dismissed' } | null;
  memory: { c: MemoryCandidate; state: 'pending' | 'confirmed' | 'declined' } | null;
};

export type ChatItem = UserItem | AssistantItem;

interface Conversation {
  items: ChatItem[];
  ended: boolean;
}

const KEY = 'deepsleep.demo.chat.v1';

function opening(): Conversation {
  const r = chatDemo.openingReply();
  return {
    ended: false,
    items: [
      { kind: 'assistant', id: r.reply_id, text: r.text, quick_replies: r.quick_replies, feedback: null, suggestion: null, memory: null },
    ],
  };
}

function load(): Conversation {
  const saved = readJson<Conversation>('session', KEY);
  if (!saved || !Array.isArray(saved.items) || saved.items.length === 0) return opening();
  // 刷新时还在“发送中”的消息无法确认结果，标为失败，由用户决定是否重试
  return {
    ...saved,
    items: saved.items.map((i) => (i.kind === 'user' && i.status === 'sending' ? { ...i, status: 'failed' } : i)),
  };
}

function memoryAllowed(): boolean {
  const p = getSavedPreferences();
  return p.memory.enabled && !p.memory.paused;
}

export function useChat() {
  const [conv, setConv] = useState<Conversation>(load);
  const controllers = useRef(new Set<AbortController>());

  useEffect(() => {
    writeJson('session', KEY, conv);
  }, [conv]);

  useEffect(() => {
    const set = controllers.current;
    return () => set.forEach((c) => c.abort());
  }, []);

  const patch = useCallback((id: string, fn: (i: ChatItem) => ChatItem) => {
    setConv((c) => ({ ...c, items: c.items.map((i) => (i.id === id ? fn(i) : i)) }));
  }, []);

  const deliver = useCallback(
    async (item: UserItem, fail: boolean) => {
      const controller = new AbortController();
      controllers.current.add(controller);
      try {
        const r = await chatDemo.send(
          { client_message_id: item.id, preset_id: item.preset_id },
          { signal: controller.signal, fail },
        );
        const assistant: AssistantItem = {
          kind: 'assistant',
          id: r.reply_id,
          text: r.text,
          quick_replies: r.quick_replies,
          feedback: null,
          suggestion: r.suggestion ? { s: r.suggestion, state: 'open' } : null,
          // 用户关闭或暂停了记忆时，不提出记忆确认
          memory: r.memory_candidate && memoryAllowed() ? { c: r.memory_candidate, state: 'pending' } : null,
        };
        setConv((c) => ({
          ...c,
          items: [
            ...c.items.map((i) => (i.id === item.id ? { ...i, status: 'sent' as const } : i)),
            ...(c.items.some((i) => i.id === assistant.id) ? [] : [assistant]),
          ],
        }));
      } catch (e) {
        if (isAbortError(e)) return;
        patch(item.id, (i) => ({ ...i, status: 'failed' }) as UserItem);
      } finally {
        controllers.current.delete(controller);
      }
    },
    [patch],
  );

  const send = useCallback(
    (preset: Preset) => {
      const item: UserItem = { kind: 'user', id: newIdempotencyKey(), preset_id: preset.id, text: preset.text, status: 'sending' };
      setConv((c) => ({ ...c, items: [...c.items, item] }));
      void deliver(item, demoFlags.take('chatFailNext'));
    },
    [deliver],
  );

  const retry = useCallback(
    (id: string) => {
      const item = conv.items.find((i): i is UserItem => i.id === id && i.kind === 'user');
      if (!item) return;
      patch(id, (i) => ({ ...i, status: 'sending' }) as UserItem);
      void deliver({ ...item, status: 'sending' }, false);
    },
    [conv.items, deliver, patch],
  );

  const removeFailed = useCallback((id: string) => {
    setConv((c) => ({ ...c, items: c.items.filter((i) => i.id !== id) }));
  }, []);

  const setFeedback = useCallback(
    (id: string, feedback: AssistantItem['feedback']) => patch(id, (i) => ({ ...i, feedback }) as AssistantItem),
    [patch],
  );

  const suggestionAction = useCallback(
    (id: string, action: 'accept' | 'dismiss' | 'swap') => {
      patch(id, (i) => {
        const a = i as AssistantItem;
        if (!a.suggestion) return a;
        if (action === 'accept') return { ...a, suggestion: { ...a.suggestion, state: 'accepted' } };
        if (action === 'dismiss') return { ...a, suggestion: { ...a.suggestion, state: 'dismissed' } };
        const alt = a.suggestion.s.alternative_id ? chatDemo.suggestion(a.suggestion.s.alternative_id) : null;
        return alt ? { ...a, suggestion: { s: alt, state: 'open' } } : a;
      });
    },
    [patch],
  );

  const memoryAction = useCallback(
    (id: string, action: 'confirm' | 'decline') => {
      const item = conv.items.find((i): i is AssistantItem => i.id === id && i.kind === 'assistant');
      if (!item?.memory || item.memory.state !== 'pending') return;
      if (action === 'confirm') {
        const days = item.memory.c.valid_days;
        memories.add({
          text: item.memory.c.text,
          source: '聊一聊（交互演示）',
          valid_until: days ? new Date(Date.now() + days * 86400000).toISOString() : null,
        });
      }
      patch(id, (i) => {
        const a = i as AssistantItem;
        return a.memory ? { ...a, memory: { ...a.memory, state: action === 'confirm' ? 'confirmed' : 'declined' } } : a;
      });
    },
    [conv.items, patch],
  );

  const end = useCallback(() => setConv((c) => ({ ...c, ended: true })), []);
  const restart = useCallback(() => {
    removeKey('session', KEY);
    setConv(opening());
  }, []);

  const last = conv.items[conv.items.length - 1];
  const waiting = conv.items.some((i) => i.kind === 'user' && i.status === 'sending');
  const hasFailed = conv.items.some((i) => i.kind === 'user' && i.status === 'failed');
  const quickReplies = !conv.ended && !waiting && !hasFailed && last?.kind === 'assistant' ? last.quick_replies : [];

  const accepted = conv.items.flatMap((i) =>
    i.kind === 'assistant' && i.suggestion?.state === 'accepted' ? [i.suggestion.s] : [],
  );
  const remembered = conv.items.flatMap((i) =>
    i.kind === 'assistant' && i.memory?.state === 'confirmed' ? [i.memory.c.text] : [],
  );

  return {
    items: conv.items,
    ended: conv.ended,
    waiting,
    quickReplies,
    accepted,
    remembered,
    send,
    retry,
    removeFailed,
    setFeedback,
    suggestionAction,
    memoryAction,
    end,
    restart,
  };
}
