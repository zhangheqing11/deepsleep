import { useEffect, useState, type ReactNode } from 'react';
import { HREF } from '../../hooks/useHashRoute';
import { dateTime } from '../../lib/format';
import {
  HABIT_OPTIONS,
  demoFlags,
  isExpired,
  memories,
  savePreferencesDemo,
  useDemoFlags,
  useMemories,
  useSavedPreferences,
  type MemoryItem,
  type Preferences,
} from '../../lib/userDemoStore';

type SaveState = 'idle' | 'saving' | 'saved' | 'failed';

/** 一行设置：标题 + 当前值，点开编辑 */
function Group({ title, value, children }: { title: string; value: ReactNode; children: ReactNode }) {
  return (
    <details className="pref-group">
      <summary>
        <span className="pref-title">{title}</span>
        <span className="pref-value">{value}</span>
      </summary>
      <div className="pref-body">{children}</div>
    </details>
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

function Toggle({
  label,
  checked,
  onChange,
  hint,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <label className={`toggle-row ${disabled ? 'is-disabled' : ''}`}>
      <span>
        {label}
        {hint && <span className="small muted block">{hint}</span>}
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
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
          <div className="row">
            <button
              type="button"
              className="btn btn-sm btn-primary"
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
          <span>{m.text}</span>
          <span className="small muted">
            {m.source} · {dateTime(m.created_at)}
            {m.valid_until && ` · ${expired ? '已过期' : `有效至 ${dateTime(m.valid_until)}`}`}
          </span>
          {confirmDelete ? (
            <span className="row">
              <span className="small">删除后立即生效，确定吗？</span>
              <button type="button" className="btn btn-sm btn-danger" onClick={() => memories.remove(m.id)}>
                删除
              </button>
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => setConfirmDelete(false)}>
                取消
              </button>
            </span>
          ) : (
            <span className="row">
              <button type="button" className="quiet-btn" onClick={() => setEditing(true)}>
                编辑
              </button>
              <button type="button" className="quiet-btn" onClick={() => setConfirmDelete(true)}>
                删除
              </button>
            </span>
          )}
        </>
      )}
    </li>
  );
}

const STYLE_LABEL = { listen_first: '先听你说', brief_advice: '直接给建议' } as const;
const LENGTH_LABEL = { short: '简短', medium: '适中' } as const;
const THEME_LABEL = { system: '跟随系统', light: '日间', dark: '夜间' } as const;
const FONT_LABEL = { standard: '标准字号', large: '大字号' } as const;

export function SettingsPage() {
  const saved = useSavedPreferences();
  const memoryItems = useMemories();
  const flags = useDemoFlags();
  const [draft, setDraft] = useState<Preferences>(saved);
  const [saveState, setSaveState] = useState<SaveState>('idle');

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
    const fail = demoFlags.take('saveFailNext'); // 模拟失败只作用于这一次保存
    try {
      await savePreferencesDemo(draft, { fail });
      setSaveState('saved');
    } catch {
      setSaveState('failed');
    }
  };

  const s = draft.schedule;
  const scheduleValue =
    [s.wake_target ? `${s.wake_target} 起床` : null, s.shift_work ? '倒班' : null, s.habits.length ? `${s.habits.length} 个习惯` : null]
      .filter(Boolean)
      .join(' · ') || '未设置';
  const activeMemories = memoryItems.filter((m) => !isExpired(m)).length;
  const memoryValue = !draft.memory.enabled
    ? '已关闭'
    : draft.memory.paused
      ? `已暂停 · ${memoryItems.length} 条`
      : memoryItems.length
        ? `${activeMemories} 条`
        : '还没有';

  return (
    <div className="settings-page">
      <div className="settings-scroll">
        <h2 className="page-title">我的</h2>
        <p className="small muted">让建议更适合你的生活。你明确填写的内容优先于对话里的推测。</p>

        <div className="pref-list">
          <Group title="作息与习惯" value={scheduleValue}>
            <label className="field-row">
              <span>希望几点起床</span>
              <input type="time" value={s.wake_target} onChange={(e) => set('schedule', { wake_target: e.target.value })} />
            </label>
            <Toggle label="作息需要倒班" checked={s.shift_work} onChange={(v) => set('schedule', { shift_work: v })} />
            <div className="field-col">
              <span>想改善的习惯</span>
              <div className="chips">
                {HABIT_OPTIONS.map((h) => {
                  const on = s.habits.includes(h);
                  return (
                    <button
                      key={h}
                      type="button"
                      className={on ? 'chip active' : 'chip'}
                      aria-pressed={on}
                      onClick={() => set('schedule', { habits: on ? s.habits.filter((x) => x !== h) : [...s.habits, h] })}
                    >
                      {h}
                    </button>
                  );
                })}
              </div>
            </div>
          </Group>

          <Group
            title="交流方式"
            value={`${STYLE_LABEL[draft.communication.style]} · ${LENGTH_LABEL[draft.communication.length]}`}
          >
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
            <Toggle label="睡前提醒" hint="待接入，暂不可用" checked={false} disabled onChange={() => undefined} />
          </Group>

          <Group title="我记住的事" value={memoryValue}>
            <p className="small muted">只有你在对话里点了“记住这件事”的内容才会出现在这里。修改和删除立即生效。</p>
            <Toggle
              label="暂停记忆"
              hint="暂停期间不会提出新的记忆，已记住的保留"
              checked={draft.memory.paused}
              onChange={(v) => set('memory', { paused: v })}
            />
            {memoryItems.length === 0 ? (
              <p className="muted">还没有记住任何事。</p>
            ) : (
              <ul className="memory-list">
                {memoryItems.map((m) => (
                  <MemoryRow key={m.id} m={m} />
                ))}
              </ul>
            )}
          </Group>
        </div>

        <h3 className="list-heading">更多</h3>
        <div className="pref-list">
          <Group title="隐私与数据" value={draft.memory.enabled ? '偏好记忆开启' : '偏好记忆关闭'}>
            <Toggle
              label="偏好记忆"
              hint="关闭后不会提出、也不会使用记住的事"
              checked={draft.memory.enabled}
              onChange={(v) => set('memory', { enabled: v })}
            />
            <div className="field-col">
              <span>对话保留</span>
              <span className="small muted">演示中只保留在当前浏览器标签页，关闭即清除。保留时长设置待接入。</span>
            </div>
            <div className="row">
              <button type="button" className="btn btn-sm" disabled>
                导出我的数据（待接入）
              </button>
              <button type="button" className="btn btn-sm" disabled>
                删除全部数据（待接入）
              </button>
            </div>
          </Group>

          <Group
            title="外观"
            value={`${THEME_LABEL[draft.appearance.theme]} · ${FONT_LABEL[draft.appearance.font]}`}
          >
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
          </Group>

          <Group title="关于这个演示" value="未接模型">
            <p className="small">
              回复是固定示例，没有连接模型，也没有经过安全层。偏好和记忆只保存在这台设备的浏览器里，不会上传。
            </p>
            <p className="small">
              <a href={HREF.runs}>打开开发者控制台 →</a>
            </p>
            <details className="debug-box">
              <summary className="small">演示调试</summary>
              <label className="check-row small">
                <input
                  type="checkbox"
                  checked={flags.chatFailNext}
                  onChange={(e) => demoFlags.set({ chatFailNext: e.target.checked })}
                />
                下一条聊天消息模拟发送失败
              </label>
              <label className="check-row small">
                <input
                  type="checkbox"
                  checked={flags.saveFailNext}
                  onChange={(e) => demoFlags.set({ saveFailNext: e.target.checked })}
                />
                下一次保存偏好模拟失败
              </label>
            </details>
          </Group>
        </div>
      </div>

      {(dirty || saveState !== 'idle') && (
        <div className="save-bar" role="status" aria-live="polite">
          <span className="small">
            {saveState === 'saving'
              ? '保存中…'
              : saveState === 'failed'
                ? '保存失败，修改还在'
                : dirty
                  ? '有未保存的更改'
                  : '已保存到本机'}
          </span>
          {(dirty || saveState === 'failed') && (
            <span className="row">
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
      )}
    </div>
  );
}
