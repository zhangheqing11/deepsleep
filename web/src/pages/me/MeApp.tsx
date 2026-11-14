// 用户视角：一位来访自己打开应用会看到什么——今晚的安排、和教练的对话、自己的自评。
// 数据仍然是实验里一位模拟来访与最新一版教练的会谈；没有输入框，不生成任何教练的话。
import { useEffect, useMemo, useRef, useState } from 'react';
import { dismissWelcome, signOut, useAuth } from '../../api/auth';
import { describeError } from '../../api/errors';
import { Ending, IsiSpark, Scales, Transcript } from '../../components/app/Replay';
import { HREF, meHref, visitorHref, type MeRoute, type MeTab } from '../../hooks/useHashRoute';
import { useCatalog, useSession } from '../../hooks/useReplay';
import { Moon } from '../../layouts/ConsoleLayout';
import { isDark, setThemeChoice, useAppearance } from '../../lib/appearance';
import { CARD_LABEL, COMPONENT_LABEL, label } from '../../lib/labels';
import { advance, buildSteps, digest, initialShown, pendingLine, type Catalog, type Side, type VisitorEntry } from '../../lib/replay';
import '../../app.css';
import '../../me.css';

const NAMES = { agent: '教练', visitor: '我' };
const hours = (min: number) => `${Math.round((min / 60) * 10) / 10} 小时`;

function greeting(now = new Date()): string {
  const h = now.getHours();
  if (h < 5) return '夜深了';
  if (h < 11) return '早上好';
  if (h < 18) return '下午好';
  return '晚上好';
}

/**
 * 默认进入的那位来访：没有触发安全线、和最新一版教练谈过的。
 * 自己注册的账号按账号名固定分到其中一位（同一个账号每次看到的是同一位）；其余情况取第一位。
 */
export function defaultVisitor(catalog: Pick<Catalog, 'visitors'>, accountId: string | null = null): VisitorEntry | null {
  const list = catalog.visitors;
  const eligible = list.filter((v) => !v.safety && v.hasAfter);
  if (accountId && eligible.length > 0) {
    let h = 0;
    for (const ch of accountId) h = (h * 31 + ch.codePointAt(0)!) >>> 0;
    return eligible[h % eligible.length];
  }
  return eligible[0] ?? list.find((v) => !v.safety) ?? list[0] ?? null;
}

const TABS: { tab: MeTab; text: string }[] = [
  { tab: 'tonight', text: '今晚' },
  { tab: 'chat', text: '对话' },
  { tab: 'profile', text: '我的' },
];

function Frame({ children, visitorId, tab, pinned }: { children: React.ReactNode; visitorId: string | null; tab: MeTab; pinned: boolean }) {
  const id = pinned ? visitorId : null;
  return (
    <div className="ua me">
      <div className="me-phone">
        <p className="me-demo">
          演示：这是模拟来访{visitorId ? ` ${visitorId} ` : ''}的数据
          {visitorId && <a href={visitorHref(visitorId)}>评委怎么看这位来访</a>}
        </p>
        <header className="me-top">
          <span className="ua-brand"><Moon size={20} /><span>deepsleep</span></span>
        </header>
        <main className="me-body">{children}</main>
        <nav className="me-tabbar" aria-label="主导航">
          {TABS.map((t) => (
            <a key={t.tab} href={meHref(id, t.tab)} aria-current={t.tab === tab ? 'page' : undefined}>{t.text}</a>
          ))}
        </nav>
      </div>
    </div>
  );
}

function Tonight({ catalog, entry, side, pinned }: { catalog: Catalog; entry: VisitorEntry; side: Side; pinned: boolean }) {
  const run = side === 'after' ? catalog.after : catalog.before;
  const res = useSession(run?.runId ?? null, entry.id);
  const auth = useAuth();
  const name = auth.state === 'signed-in' && auth.user.role === 'user' ? auth.user.display_name : null;
  const welcome = auth.state === 'signed-in' && auth.fresh === true;
  if (res.status === 'error') {
    return <p className="ua-note negative" role="alert">读不到你和教练的对话：{describeError(res.error)}<button type="button" className="ua-link" onClick={res.reload}>重试</button></p>;
  }
  if (res.status !== 'ok') return <p className="ua-note">正在读取…</p>;
  const session = res.data;
  const d = digest(session, side === 'after' ? entry.after : entry.before);
  const plan = session.plan;
  const lastSafety = [...session.rounds].flatMap((r) => r.transcript).filter((t) => t.speaker === 'safety').pop();
  const learned = side === 'after' && catalog.outcome === 'committed' && !catalog.sameVersion ? catalog.learned.length : 0;

  return (
    <>
      {welcome && (
        <section className="me-welcome" role="status">
          <p><b>注册好了。</b>演示里没有你自己的数据：你会以模拟来访 {entry.id} 的身份，看 TA 和教练谈完之后应用里的样子。</p>
          <button type="button" className="ua-link" onClick={dismissWelcome}>知道了</button>
        </section>
      )}
      <section className="me-hero">
        <span className="ua-who">{greeting()}{name ? `，${name}` : ''}</span>
        {plan ? (
          <h1>今晚 <b>{plan.bedtime}</b> 上床，<br />明早 <b>{plan.risetime}</b> 起床</h1>
        ) : session.status === 'crisis_exit' ? (
          <h1>睡眠的事先放一放</h1>
        ) : (
          <h1>今晚还没有安排</h1>
        )}
        {plan && <p className="ua-sub">留给睡眠的时间是 {hours(plan.tib_minutes)}。这是教练和你谈完两轮之后给的建议。</p>}
        {!plan && session.status === 'completed' && <p className="ua-sub">你和教练的对话还没有形成今晚的安排。</p>}
        {session.status === 'error' && <p className="ua-sub negative">上一次对话中途出错，没有走完。</p>}
      </section>

      {session.status === 'crisis_exit' && lastSafety && (
        <section className="ua-safety me-safety" aria-label="安全层的话">
          <span className="ua-who">安全层 · 固定话术，不随进化改变</span>
          <p>{lastSafety.text}</p>
        </section>
      )}

      {plan && (
        <section className="me-block" aria-labelledby="me-plan">
          <h2 id="me-plan">这一周怎么做</h2>
          {plan.components.length > 0 && (
            <ul className="ua-chips">{plan.components.map((c) => <li key={c}>{label(COMPONENT_LABEL, c)}</li>)}</ul>
          )}
          {plan.referral_advice && <p className="ua-referral">{plan.referral_advice}</p>}
          {plan.cards.map((c, i) => (
            <article key={i} className="ua-plancard">
              <span className="ua-who">{label(CARD_LABEL, c.type)}</span>
              <strong>{c.title}</strong>
              <p>{c.body}</p>
            </article>
          ))}
        </section>
      )}

      {d.isiWeek && (
        <section className="me-block tint" aria-labelledby="me-trend">
          <h2 id="me-trend">照这样过四周（模拟）</h2>
          <p className="ua-figure">
            ISI <b>{d.isiWeek[0]}</b> → <b>{d.isiWeek[4]}</b>
            <span className={d.responder ? 'good' : 'flat'}>{d.responder ? '达到有效线' : '未达到有效线'}</span>
          </p>
          <IsiSpark before={null} after={d.isiWeek} beforeName="" afterName="睡眠评分" />
          <p className="ua-fine">分数越低，睡眠困扰越轻；下降超过 7 分记为有效。由固定的规则模型推算，不是真人的结果。</p>
        </section>
      )}

      <section className="me-block" aria-labelledby="me-coach">
        <h2 id="me-coach">你的教练</h2>
        <p>
          现在用的是手册 <b>{d.version}</b>。
          {learned > 0
            ? `它读完上一批没谈好的会谈后，给自己的手册加了 ${learned} 条规则。`
            : catalog.outcome === 'kept_previous' ? '上一次学习提出的修改没有通过门禁，手册保持原样。' : ''}
        </p>
        <p className="me-links">
          <a className="ua-link" href={meHref(pinned ? entry.id : null, 'chat')}>回看和教练的对话</a>
          <a className="ua-link" href={visitorHref(entry.id, 'compare')}>{learned > 0 ? '它学到了什么' : '对比两场会谈'}</a>
        </p>
      </section>
    </>
  );
}

function Chat({ catalog, entry, side }: { catalog: Catalog; entry: VisitorEntry; side: Side }) {
  const run = side === 'after' ? catalog.after : catalog.before;
  const res = useSession(run?.runId ?? null, entry.id);
  const session = res.status === 'ok' ? res.data : null;
  const steps = useMemo(() => (session ? buildSteps(session) : []), [session]);
  // 默认把整段对话摆出来（用户回到应用时对话已经发生过）；点“从头走一遍”才逐句来
  const [shown, setShown] = useState<number | null>(null);
  const [typing, setTyping] = useState(false);
  const timer = useRef<number>();
  const tail = useRef<HTMLDivElement>(null);
  const at = shown ?? steps.length;
  const walking = shown !== null;
  const finished = session !== null && at >= steps.length;
  const next = typing ? null : pendingLine(steps, at);

  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => {
    if (walking && at > initialShown(steps)) tail.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [at, typing, steps, walking]);

  const say = () => {
    const target = advance(steps, at);
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || target <= at + 1) return setShown(target);
    setShown(at + 1);
    setTyping(true);
    timer.current = window.setTimeout(() => {
      setTyping(false);
      setShown(target);
    }, 650);
  };
  const restart = () => {
    window.clearTimeout(timer.current);
    setTyping(false);
    setShown(initialShown(steps));
    window.scrollTo(0, 0);
  };
  const showAll = () => {
    window.clearTimeout(timer.current);
    setTyping(false);
    setShown(null);
  };

  if (res.status === 'error') {
    return <p className="ua-note negative" role="alert">读不到这段对话：{describeError(res.error)}<button type="button" className="ua-link" onClick={res.reload}>重试</button></p>;
  }
  if (!session) return <p className="ua-note">正在读取…</p>;
  const d = digest(session, side === 'after' ? entry.after : entry.before);
  return (
    <section className="me-chat" aria-label="和教练的对话">
      <p className="ua-model">
        教练 · 手册 {d.version} · 模型 {d.model}
        {d.mock && <span className="ua-flag">模板生成的回复，不是模型写的</span>}
      </p>
      <Transcript steps={steps} shown={at} typing={typing} names={NAMES} />
      {finished && walking && <Ending session={session} digest={d} />}
      <div ref={tail} className="ua-tail" />
      <div className="ua-composer me-composer">
        {walking && next !== null && (
          <button type="button" className="ua-say" onClick={say}>
            <span className="ua-who">点一下，说这一句</span>
            <span className="ua-line">{next}</span>
          </button>
        )}
        {typing && <p className="ua-wait">教练正在回应…</p>}
        <div className="ua-actions">
          {!walking && <button type="button" className="ua-go" onClick={restart}>从头走一遍这段对话</button>}
          {walking && !finished && !typing && <button type="button" className="ua-link" onClick={showAll}>直接看完</button>}
          {walking && finished && <button type="button" className="ua-link" onClick={restart}>再走一遍</button>}
        </div>
        <p className="ua-fine">这里不能自己打字：对话来自一次已经完成的模拟会谈。</p>
      </div>
    </section>
  );
}

function Profile({ catalog, entry, side }: { catalog: Catalog; entry: VisitorEntry; side: Side }) {
  const run = side === 'after' ? catalog.after : catalog.before;
  const res = useSession(run?.runId ?? null, entry.id);
  const auth = useAuth();
  const dark = isDark(useAppearance());
  const others = catalog.visitors.filter((v) => v.id !== entry.id).slice(0, 12);
  return (
    <>
      <section className="me-block" aria-labelledby="me-account">
        <h2 id="me-account">账号</h2>
        {auth.state === 'signed-in' ? (
          <p className="me-rowline">
            <span>{auth.user.display_name}<span className="ua-who">{auth.user.id}</span></span>
            <button type="button" className="ua-link" onClick={() => void signOut()}>退出登录</button>
          </p>
        ) : (
          <p className="ua-sub">这台后端没有开启登录，任何人打开都能看到这些模拟数据。</p>
        )}
        <p className="me-rowline">
          <span>外观</span>
          <button type="button" className="ua-link" onClick={() => setThemeChoice(dark ? 'light' : 'dark')}>{dark ? '换成浅色' : '换成深色'}</button>
        </p>
      </section>

      <section className="me-block" aria-labelledby="me-scales">
        <h2 id="me-scales">我的自评</h2>
        {res.status === 'ok' ? <Scales session={res.data} /> : res.status === 'error'
          ? <p className="ua-note negative" role="alert">读不到自评：{describeError(res.error)}</p>
          : <p className="ua-note">正在读取…</p>}
      </section>

      <section className="me-block" aria-labelledby="me-switch">
        <h2 id="me-switch">换一位来访的视角</h2>
        <p className="ua-sub">演示用：每一位都是模拟来访。</p>
        <ul className="me-switch">
          {others.map((v) => <li key={v.id}><a href={meHref(v.id, 'tonight')}>{v.id}{v.safety ? ' · 安全线示例' : ''}</a></li>)}
        </ul>
        <p className="me-links">
          <a className="ua-link" href={HREF.app}>所有来访与两次回应</a>
          <a className="ua-link" href={HREF.board}>进化看板</a>
        </p>
      </section>
    </>
  );
}

export function MeApp({ route }: { route: MeRoute }) {
  const state = useCatalog();
  const auth = useAuth();
  const account = auth.state === 'signed-in' && auth.user.role === 'user' ? auth.user.id : null;
  const { catalog } = state;
  const entry = catalog ? (route.visitorId ? catalog.visitors.find((v) => v.id === route.visitorId) ?? null : defaultVisitor(catalog, account)) : null;
  const pinned = route.visitorId !== null;

  if (!catalog || !entry) {
    return (
      <Frame visitorId={null} tab={route.tab} pinned={false}>
        <section className="me-hero">
          <span className="ua-who">{greeting()}</span>
          <h1>{catalog === undefined ? '正在读取…' : route.visitorId && catalog ? '没有这位来访' : '还没有可以看的对话'}</h1>
          {catalog === undefined && state.error && <p className="ua-sub negative" role="alert">后端不可用：{describeError(state.error)}。页面会自动重试。</p>}
          {catalog !== undefined && <p className="ua-sub">实验跑出会谈之后，这里会自动出现一位来访的视角。{route.visitorId && <a className="ua-link" href={meHref(null, 'tonight')}>回到默认的来访</a>}</p>}
        </section>
      </Frame>
    );
  }
  const side: Side = entry.hasAfter ? 'after' : 'before';
  const key = `${catalog.experimentId}/${entry.id}/${side}`;
  return (
    <Frame visitorId={entry.id} tab={route.tab} pinned={pinned}>
      {route.tab === 'tonight' && <Tonight key={key} catalog={catalog} entry={entry} side={side} pinned={pinned} />}
      {route.tab === 'chat' && <Chat key={key} catalog={catalog} entry={entry} side={side} />}
      {route.tab === 'profile' && <Profile key={key} catalog={catalog} entry={entry} side={side} />}
    </Frame>
  );
}
