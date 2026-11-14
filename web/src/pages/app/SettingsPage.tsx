import { useEffect, useState, type ReactNode } from 'react';
import { dateTime } from '../../lib/format';
import {
  HABIT_OPTIONS,
  isExpired,
  memories,
  savePreferencesDemo,
  useMemories,
  useSavedPreferences,
  type MemoryItem,
  type Preferences,
} from '../../lib/userDemoStore';

type SaveState = 'idle' | 'saving' | 'saved' | 'failed';

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="pref-section">
      <h2>{title}</h2>
      {hint && <p className="small muted">{hint}</p>}
      {children}
    </section>
  );
}

function Segmented<T extends string>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={value === o.value ? 'active' : ''}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="toggle-row">
      <span>
        {label}
        {hint && <span className="small muted block">{hint}</span>}
      </span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

function MemoryRow({ m }: { m: MemoryItem }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(m.text);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const expired = isExpired(m);

  return (
    <li className={`memory-row ${expired ? 'expired' : ''}`}>
      {editing ? (
        <div className="memory-edit">
          <input type="text" value={text} onChange={(e) => setText(e.target.value)} aria-label="编辑记住的内容" />
          <div className="btn-row">
            <button
              type="button"
              className="btn btn-sm btn-primary-soft"
              disabled={!text.trim()}
              onClick={() => {
                memories.update(m.id, text.trim());
                setEditing(false);
              }}
            >
              保存这条
            </button>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => {
                setText(m.text);
                setEditing(false);
              }}
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <>
          <strong>{m.text}</strong>
          <div className="small muted">
            来源：{m.source} · {dateTime(m.created_at)}
            {m.valid_until && ` · ${expired ? '已过期' : `有效至 ${dateTime(m.valid_until)}`}`}
          </div>
          {confirmDelete ? (
            <div className="btn-row">
              <span className="small">确定删除这条？</span>
              <button type="button" className="btn btn-sm btn-danger-soft" onClick={() => memories.remove(m.id)}>
                删除
              </button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setConfirmDelete(false)}>
                取消
              </button>
            </div>
          ) : (
            <div className="btn-row">
              <button type="button" className="link-btn" onClick={() => setEditing(true)}>
                编辑
              </button>
              <button type="button" className="link-btn" onClick={() => setConfirmDelete(true)}>
                删除
              </button>
            </div>
          )}
        </>
      )}
    </li>
  );
}

export function SettingsPage() {
  const saved = useSavedPreferences();
  const memoryItems = useMemories();
  const [draft, setDraft] = useState<Preferences>(saved);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [failNextSave, setFailNextSave] = useState(false);

  // 已保存的偏好在别处变化时（例如另一个标签页），没有未保存修改才跟着刷新
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  useEffect(() => {
    if (!dirty) setDraft(saved);
  }, [saved]); // eslint-disable-line react-hooks/exhaustive-deps

  // “已保存”提示 2.5 秒后自动收起
  useEffect(() => {
    if (saveState !== 'saved') return;
    const t = window.setTimeout(() => setSaveState('idle'), 2500);
    return () => window.clearTimeout(t);
  }, [saveState]);

  const set = <K extends keyof Preferences>(k: K, v: Partial<Preferences[K]>) => {
    setDraft((d) => ({ ...d, [k]: { ...d[k], ...v } }));
    if (saveState !== 'saving') setSaveState('idle');
  };

  const save = async () => {
    setSaveState('saving');
    // 模拟失败只作用于这一次保存
    const fail = failNextSave;
    setFailNextSave(false);
    try {
      await savePreferencesDemo(draft, { fail });
      setSaveState('saved');
    } catch {
      setSaveState('failed');
    }
  };

  const habits = draft.schedule.habits;

  return (
    <div className="settings-page">
      <Section title="作息与生活约束" hint="都可以跳过。你明确填写的内容优先于对话里的推测。">
        <label className="field-row">
          <span>起床目标</span>
          <input
            type="time"
            value={draft.schedule.wake_target}
            onChange={(e) => set('schedule', { wake_target: e.target.value })}
          />
        </label>
        <Toggle label="作息需要倒班" checked={draft.schedule.shift_work} onChange={(v) => set('schedule', { shift_work: v })} />
        <div className="field-col">
          <span>想改善的习惯</span>
          <div className="chips">
            {HABIT_OPTIONS.map((h) => {
              const on = habits.includes(h);
              return (
                <button
                  key={h}
                  type="button"
                  className={on ? 'chip active' : 'chip'}
                  aria-pressed={on}
                  onClick={() => set('schedule', { habits: on ? habits.filter((x) => x !== h) : [...habits, h] })}
                >
                  {h}
                </button>
              );
            })}
          </div>
        </div>
      </Section>

      <Section title="交流偏好">
        <div className="field-col">
          <span>希望我先</span>
          <Segmented
            name="交流方式"
            value={draft.communication.style}
            options={[
              { value: 'listen_first', label: '听你说' },
              { value: 'brief_advice', label: '直接给建议' },
            ]}
            onChange={(v) => set('communication', { style: v })}
          />
        </div>
        <div className="field-col">
          <span>回复长度</span>
          <Segmented
            name="回复长度"
            value={draft.communication.length}
            options={[
              { value: 'short', label: '简短' },
              { value: 'medium', label: '适中' },
            ]}
            onChange={(v) => set('communication', { length: v })}
          />
        </div>
        <Toggle label="睡前提醒" checked={draft.communication.reminders} onChange={(v) => set('communication', { reminders: v })} hint="演示中不会真的发送提醒" />
      </Section>

      <Section title="我记住的事" hint="只有你在对话里点了“记住”的内容才会出现在这里。修改和删除立即生效（仅本机）。">
        <Toggle
          label="暂停记忆"
          hint="暂停期间不会再提出新的记忆，已记住的内容保留"
          checked={draft.memory.paused}
          onChange={(v) => set('memory', { paused: v })}
        />
        {memoryItems.length === 0 ? (
          <p className="muted small">还没有记住任何事。</p>
        ) : (
          <ul className="memory-list">
            {memoryItems.map((m) => (
              <MemoryRow key={m.id} m={m} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="隐私与数据">
        <Toggle
          label="偏好记忆"
          hint="关闭后不会提出、也不会使用记住的事"
          checked={draft.memory.enabled}
          onChange={(v) => set('memory', { enabled: v })}
        />
        <div className="field-col">
          <span>对话保留</span>
          <Segmented
            name="对话保留"
            value={draft.privacy.retention}
            options={[
              { value: 'session', label: '仅本次' },
              { value: 'days_7', label: '7 天' },
              { value: 'days_30', label: '30 天' },
            ]}
            onChange={(v) => set('privacy', { retention: v })}
          />
          <span className="small muted">演示中对话只保存在当前浏览器标签页，关闭即清除；此选项待接入后生效。</span>
        </div>
        <div className="btn-row">
          <button type="button" className="btn btn-sm" disabled>
            导出我的数据（待接入）
          </button>
          <button type="button" className="btn btn-sm" disabled>
            删除全部数据（待接入）
          </button>
        </div>
      </Section>

      <Section title="外观">
        <div className="field-col">
          <span>主题</span>
          <Segmented
            name="主题"
            value={draft.appearance.theme}
            options={[
              { value: 'system', label: '跟随系统' },
              { value: 'light', label: '日间' },
              { value: 'dark', label: '夜间' },
            ]}
            onChange={(v) => set('appearance', { theme: v })}
          />
        </div>
        <div className="field-col">
          <span>字号</span>
          <Segmented
            name="字号"
            value={draft.appearance.font}
            options={[
              { value: 'standard', label: '标准' },
              { value: 'large', label: '大' },
            ]}
            onChange={(v) => set('appearance', { font: v })}
          />
        </div>
      </Section>

      <details className="demo-controls">
        <summary className="small muted">演示控制</summary>
        <label className="small">
          <input type="checkbox" checked={failNextSave} onChange={(e) => setFailNextSave(e.target.checked)} /> 下一次保存模拟失败
        </label>
      </details>

      <div className={`save-bar ${dirty || saveState !== 'idle' ? 'show' : ''}`} role="status" aria-live="polite">
        <span className="small">
          {saveState === 'saving'
            ? '保存中…'
            : saveState === 'failed'
              ? '保存失败，修改还在，可以重试'
              : dirty
                ? '有未保存的更改'
                : saveState === 'saved'
                  ? '已保存到本机（演示）'
                  : ''}
        </span>
        {(dirty || saveState === 'failed') && (
          <span className="btn-row">
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              disabled={saveState === 'saving'}
              onClick={() => {
                setDraft(saved);
                setSaveState('idle');
              }}
            >
              撤销
            </button>
            <button type="button" className="btn btn-sm btn-primary" disabled={saveState === 'saving'} onClick={save}>
              {saveState === 'failed' ? '重试保存' : '保存偏好'}
            </button>
          </span>
        )}
      </div>
    </div>
  );
}
