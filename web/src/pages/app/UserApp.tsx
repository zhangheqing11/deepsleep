// 用户端：以一位模拟来访的身份，看同一句心事在学习前后得到的两次回应。
// 没有输入框——页面上的人只是替来访把会谈记录里的下一句「说出来」。
import { useEffect, useMemo, useRef, useState } from 'react';
import { describeError } from '../../api/errors';
import { Compare, Ending, Scales, Transcript } from '../../components/app/Replay';
import { HREF, visitorHref, type UserRoute, type VisitorTab } from '../../hooks/useHashRoute';
import { useCatalog, useSession, type CatalogState } from '../../hooks/useReplay';
import { Moon } from '../../layouts/ConsoleLayout';
import { isDark, setThemeChoice, useAppearance } from '../../lib/appearance';
import {
  advance,
  buildSteps,
  digest,
  headline,
  initialShown,
  openingLine,
  pendingLine,
  sideName,
  sideVersion,
  tally,
  type Catalog,
  type Side,
  type VisitorEntry,
} from '../../lib/replay';
import '../../app.css';

const PAGE = 6;
const signed = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : '0');

function ThemeToggle() {
  const dark = isDark(useAppearance());
  return (
    <button type="button" className="ua-link" onClick={() => setThemeChoice(dark ? 'light' : 'dark')}>
      {dark ? '浅色' : '深色'}
    </button>
  );
}

function Shell({ children, back }: { children: React.ReactNode; back?: boolean }) {
  return (
    <div className="ua">
      <header className="ua-bar">
        <a className="ua-brand" href={HREF.app}>
          <Moon size={20} />
          <span>deepsleep</span>
        </a>
        <nav className="ua-nav" aria-label="页面">
          {back && <a className="ua-link" href={HREF.app}>换一位来访</a>}
          <a className="ua-link" href={HREF.me}>用户视角</a>
          <a className="ua-link" href={HREF.board}>进化看板</a>
          <ThemeToggle />
        </nav>
      </header>
      {children}
      <footer className="ua-foot">
        所有来访和会谈都是模拟数据。页面展示的是建议与干预路径，不能替代专业医疗意见；如有需要，请建议就医。
      </footer>
    </div>
  );
}

// ---------- 首页：选一句心事 ----------

function VisitorCard({ catalog, entry }: { catalog: Catalog; entry: VisitorEntry }) {
  const side = entry.hasBefore ? catalog.before : catalog.after;
  const session = useSession(side?.runId ?? null, entry.id);
  const line = session.status === 'ok' ? openingLine(session.data) : null;
  const change = (s: Side) => {
    const row = s === 'before' ? entry.before : entry.after;
    const has = s === 'before' ? entry.hasBefore : entry.hasAfter;
    if (!has) return null;
    return (
      <span className={s === 'before' ? 'base' : 'lead'}>
        {sideName(catalog, s)} {row ? `${signed(row.isi_change)} 分` : '—'}
      </span>
    );
  };
  return (
    <li>
      <a className={`ua-card${entry.safety ? ' safety' : ''}`} href={visitorHref(entry.id)}>
        <p className="ua-quote">
          {session.status === 'error' ? '这位来访的会谈暂时读不到' : line ?? <span className="ua-skeleton" aria-label="正在读取" />}
        </p>
        <p className="ua-meta">
          <span>来访 {entry.id}</span>
          <span className="ua-isi" title="模拟的四周 ISI 变化，越低越好">四周 ISI {change('before')}{change('after')}</span>
        </p>
      </a>
    </li>
  );
}

function Home({ state }: { state: CatalogState }) {
  const { catalog, error } = state;
  const [page, setPage] = useState(0);
  const regular = useMemo(() => (catalog?.visitors ?? []).filter((v) => !v.safety), [catalog]);
  const safety = useMemo(() => (catalog?.visitors ?? []).filter((v) => v.safety), [catalog]);
  const pages = Math.max(1, Math.ceil(regular.length / PAGE));
  const current = regular.slice((page % pages) * PAGE, (page % pages) * PAGE + PAGE);
  const t = tally(catalog?.visitors ?? []);

  return (
    <Shell>
      <main className="ua-home">
        <section className="ua-lead">
          <h1>同一句心事，两次回应</h1>
          {catalog === undefined && !error && <p className="ua-sub">正在读取实验…</p>}
          {catalog === undefined && error && (
            <p className="ua-sub negative" role="alert">
              后端不可用：{describeError(error)}。页面会自动重试。
              <button type="button" className="ua-link" onClick={state.reload}>立即重试</button>
            </p>
          )}
          {catalog !== undefined && <p className="ua-sub">{headline(catalog)}</p>}
          {catalog && !catalog.sameVersion && t.paired > 0 && (
            <p className="ua-tally">
              {t.paired} 位来访里，<b className="good">{t.better} 位</b>在学习后四周的睡眠评分降得更多，{t.same} 位一样，
              <b className={t.worse > 0 ? 'bad' : undefined}>{t.worse} 位</b>降得更少。
            </p>
          )}
          {catalog !== undefined && error && <p className="ua-sub negative" role="status">连接中断，显示的是上一次读到的内容。</p>}
        </section>

        {catalog && (catalog.before || catalog.after) && catalog.visitors.length === 0 && (
          <p className="ua-note">这次实验没有可以读取的会谈记录。</p>
        )}

        {current.length > 0 && catalog && (
          <section aria-labelledby="ua-pick">
            <div className="ua-sechead">
              <h2 id="ua-pick">选一位来访，替 TA 说出第一句</h2>
              {pages > 1 && (
                <button type="button" className="ua-link" onClick={() => setPage((p) => (p + 1) % pages)}>
                  换一批（{(page % pages) + 1}/{pages}）
                </button>
              )}
            </div>
            <ul className="ua-cards">
              {current.map((v) => <VisitorCard key={v.id} catalog={catalog} entry={v} />)}
            </ul>
            {t.paired > 0 && (
              <p className="ua-fine">按学习后多降的分数从大到小排列{pages > 1 ? `，换一批可以看到全部 ${regular.length} 位` : ''}。</p>
            )}
          </section>
        )}

        {safety.length > 0 && catalog && (
          <section className="ua-safezone" aria-labelledby="ua-safe">
            <div className="ua-sechead">
              <h2 id="ua-safe">安全线示例</h2>
            </div>
            <p className="ua-sub">这几位来访的话触发了安全层。安全层是固定规则，不参与进化：学习前后它说的话一字不变。</p>
            <ul className="ua-cards">
              {safety.slice(0, PAGE).map((v) => <VisitorCard key={v.id} catalog={catalog} entry={v} />)}
            </ul>
          </section>
        )}
      </main>
    </Shell>
  );
}

// ---------- 来访页：会谈 / 对比 / 自评 ----------

const TABS: { tab: VisitorTab; text: string }[] = [
  { tab: 'talk', text: '会谈' },
  { tab: 'compare', text: '对比' },
  { tab: 'scales', text: '自评' },
];

function Visitor({ catalog, entry, tab }: { catalog: Catalog; entry: VisitorEntry; tab: VisitorTab }) {
  const before = useSession(entry.hasBefore ? catalog.before?.runId ?? null : null, entry.id);
  const after = useSession(entry.hasAfter ? catalog.after?.runId ?? null : null, entry.id);
  const [side, setSide] = useState<Side>(entry.hasBefore ? 'before' : 'after');
  const [shown, setShown] = useState<Record<Side, number | null>>({ before: null, after: null });
  const [typing, setTyping] = useState(false);
  const timer = useRef<number>();
  const tail = useRef<HTMLDivElement>(null);

  const res = side === 'before' ? before : after;
  const session = res.status === 'ok' ? res.data : null;
  const steps = useMemo(() => (session ? buildSteps(session) : []), [session]);
  const at = shown[side] ?? initialShown(steps);
  const next = typing ? null : pendingLine(steps, at);
  const finished = session !== null && at >= steps.length;

  const dBefore = before.status === 'ok' ? digest(before.data, entry.before) : null;
  const dAfter = after.status === 'ok' ? digest(after.data, entry.after) : null;
  const current = side === 'before' ? dBefore : dAfter;
  const opening = (before.status === 'ok' && openingLine(before.data)) || (after.status === 'ok' && openingLine(after.data)) || null;

  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => {
    if (at > initialShown(steps)) tail.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [at, typing, steps]);

  const stop = () => {
    window.clearTimeout(timer.current);
    setTyping(false);
  };
  /** 替来访说出下一句：这句话立刻出现，教练的回应稍后跟上。 */
  const say = () => {
    const target = advance(steps, at);
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce || target <= at + 1) {
      setShown((s) => ({ ...s, [side]: target }));
      return;
    }
    setShown((s) => ({ ...s, [side]: at + 1 }));
    setTyping(true);
    const forSide = side;
    timer.current = window.setTimeout(() => {
      setTyping(false);
      setShown((s) => ({ ...s, [forSide]: target }));
    }, 650);
  };
  const jump = (to: number) => {
    stop();
    setShown((s) => ({ ...s, [side]: to }));
  };
  const pick = (s: Side) => {
    stop();
    setSide(s);
  };

  const sides: Side[] = [...(entry.hasBefore ? (['before'] as const) : []), ...(entry.hasAfter ? (['after'] as const) : [])];
  const other: Side | null = sides.length === 2 ? (side === 'before' ? 'after' : 'before') : null;

  return (
    <Shell back>
      <main className="ua-visitor" data-tab={tab}>
        <section className="ua-opening">
          <span className="ua-who">来访 {entry.id}{entry.safety ? ' · 安全线示例' : ''}</span>
          <h1>{opening ? `“${opening}”` : <span className="ua-skeleton" aria-label="正在读取" />}</h1>
        </section>

        <nav className="ua-tabs" aria-label="这位来访">
          {TABS.map((t) => (
            <a key={t.tab} href={visitorHref(entry.id, t.tab)} aria-current={t.tab === tab ? 'page' : undefined}>{t.text}</a>
          ))}
        </nav>

        <section className="ua-panel ua-talk" aria-label="会谈">
          <div className="ua-switch" role="group" aria-label="看哪一场会谈">
            {sides.map((s) => (
              <button key={s} type="button" className={s === 'before' ? 'base' : 'lead'} aria-pressed={s === side} onClick={() => pick(s)}>
                {sideName(catalog, s)}<b>{sideVersion(catalog, s)}</b>
              </button>
            ))}
          </div>
          {current && (
            <p className="ua-model">
              教练模型：{current.model}
              {current.mock && <span className="ua-flag">模板生成的回复，不是模型写的</span>}
            </p>
          )}
          {res.status === 'loading' && <p className="ua-note">正在读取这场会谈…</p>}
          {res.status === 'error' && (
            <p className="ua-note negative" role="alert">
              这场会谈读不到：{describeError(res.error)}
              <button type="button" className="ua-link" onClick={res.reload}>重试</button>
            </p>
          )}
          {session && (
            <>
              <Transcript steps={steps} shown={at} typing={typing} />
              {finished && current && <Ending session={session} digest={current} />}
              <div ref={tail} className="ua-tail" />
              <div className="ua-composer">
                {next !== null && (
                  <button type="button" className="ua-say" onClick={say}>
                    <span className="ua-who">替来访说</span>
                    <span className="ua-line">{next}</span>
                  </button>
                )}
                {typing && <p className="ua-wait">教练正在回应…</p>}
                <div className="ua-actions">
                  {!finished && !typing && <button type="button" className="ua-link" onClick={() => jump(steps.length)}>直接看完这一场</button>}
                  {finished && <button type="button" className="ua-link" onClick={() => jump(initialShown(steps))}>从头再放</button>}
                  {finished && other && (
                    <button type="button" className="ua-go" onClick={() => pick(other)}>
                      同一句话，换成{sideName(catalog, other)}的教练
                    </button>
                  )}
                  {finished && <a className="ua-link ua-narrow" href={visitorHref(entry.id, 'compare')}>看两场的差别</a>}
                </div>
              </div>
            </>
          )}
        </section>

        <section className="ua-panel ua-side" aria-label="对比与自评">
          <div className="ua-block ua-compare-block">
            <h2>两场会谈差在哪</h2>
            {dBefore || dAfter ? (
              <Compare
                before={dBefore}
                after={dAfter}
                beforeName={sideName(catalog, 'before')}
                afterName={sideName(catalog, 'after')}
                sameVersion={catalog.sameVersion}
                learned={catalog.learned}
                learnedSummary={catalog.learnedSummary}
                outcome={catalog.outcome}
              />
            ) : (
              <p className="ua-note">正在读取…</p>
            )}
          </div>
          <div className="ua-block ua-scales-block">
            <h2>这位来访的自评</h2>
            {session ? <Scales session={session} /> : <p className="ua-note">正在读取…</p>}
          </div>
        </section>
      </main>
    </Shell>
  );
}

export function UserApp({ route }: { route: UserRoute }) {
  const state = useCatalog();
  if (route.name === 'app-home') return <Home state={state} />;
  const { catalog } = state;
  const entry = catalog?.visitors.find((v) => v.id === route.visitorId);
  if (!catalog || !entry) {
    return (
      <Shell back>
        <main className="ua-home">
          <section className="ua-lead">
            <h1>{catalog === undefined ? '正在读取…' : '没有这位来访的会谈'}</h1>
            {catalog === undefined && state.error && <p className="ua-sub negative" role="alert">后端不可用：{describeError(state.error)}。页面会自动重试。</p>}
            {catalog !== undefined && <p className="ua-sub">实验可能已经重置。<a className="ua-link" href={HREF.app}>回到来访列表</a></p>}
          </section>
        </main>
      </Shell>
    );
  }
  // 换一位来访或实验重置时整页重建，回放进度不串到别人身上
  return <Visitor key={`${catalog.experimentId}/${entry.id}`} catalog={catalog} entry={entry} tab={route.tab} />;
}
