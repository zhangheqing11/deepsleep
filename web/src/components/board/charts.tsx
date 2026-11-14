// 看板的图表：手写 SVG / HTML，不依赖图表库。只画传进来的数据，不计算指标。
// 颜色全部走 CSS 变量：lead = 进化后的版本（--hue），base = 对照（--base）。
import type { ReactNode } from 'react';

export type Tone = 'lead' | 'base';
export interface Point { x: number; y: number }
export interface LineSeries {
  key: string;
  tone: Tone;
  points: Point[];
  /** 画在线尾的标签；不给就不标 */
  endLabel?: string;
}

interface LineChartProps {
  ariaLabel: string;
  series: LineSeries[];
  /** 背景细线（例如每位来访一条），不带标签 */
  faint?: { key: string; tone: Tone; points: Point[] }[];
  xDomain: [number, number];
  yDomain: [number, number];
  xTicks: { x: number; label: string }[];
  yTicks: number[];
  yFormat: (v: number) => string;
  /** 水平参考线，标签写在线的左端上方（右侧留给线尾标签） */
  refs?: { y: number; label: string }[];
  /** 竖直分隔（例如两轮之间），标签写在分隔右侧顶部 */
  dividers?: { x: number; label: string }[];
  /** 起点处的分区标签（第一个分区没有分隔线） */
  firstRegionLabel?: string;
}

const W = 640;
const H = 280;
const M = { l: 46, r: 118, t: 26, b: 30 };

function path(points: Point[], sx: (x: number) => number, sy: (y: number) => number): string {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'}${sx(p.x).toFixed(1)} ${sy(p.y).toFixed(1)}`).join(' ');
}

/** 直线段折线图：横向网格、无 y 轴线、单一参考线；线尾直接标注，不另放图例。 */
export function LineChart(props: LineChartProps) {
  const { series, faint = [], xDomain, yDomain, xTicks, yTicks, yFormat, refs = [], dividers = [] } = props;
  const sx = (x: number) => M.l + ((x - xDomain[0]) / (xDomain[1] - xDomain[0] || 1)) * (W - M.l - M.r);
  const sy = (y: number) => M.t + ((yDomain[1] - y) / (yDomain[1] - yDomain[0] || 1)) * (H - M.t - M.b);

  // 线尾标签：两条线末端太近时上下错开，不让文字相叠。
  const ends = series
    .filter((s) => s.endLabel && s.points.length > 0)
    .map((s) => ({ s, y: sy(s.points[s.points.length - 1].y) }))
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 18) ends[i].y = ends[i - 1].y + 18;

  return (
    <svg className="ch" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={props.ariaLabel}>
      {yTicks.map((t) => (
        <g key={t}>
          <line className="ch-grid" x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} />
          <text className="ch-tick" x={M.l - 8} y={sy(t)} textAnchor="end" dominantBaseline="middle">{yFormat(t)}</text>
        </g>
      ))}
      {xTicks.map((t) => (
        <text key={t.x} className="ch-tick" x={sx(t.x)} y={H - 8} textAnchor="middle">{t.label}</text>
      ))}
      {props.firstRegionLabel && (
        <text className="ch-note" x={M.l + 4} y={M.t - 10}>{props.firstRegionLabel}</text>
      )}
      {dividers.map((d) => (
        <g key={d.x}>
          <line className="ch-divider" x1={sx(d.x)} x2={sx(d.x)} y1={M.t - 4} y2={H - M.b} />
          <text className="ch-note" x={sx(d.x) + 6} y={M.t - 10}>{d.label}</text>
        </g>
      ))}
      {refs.map((r) => (
        <g key={r.label}>
          <line className="ch-ref" x1={M.l} x2={W - M.r} y1={sy(r.y)} y2={sy(r.y)} />
          <text className="ch-note" x={M.l + 4} y={sy(r.y) - 6}>{r.label}</text>
        </g>
      ))}
      {faint.map((f) => (
        <path key={f.key} className={`ch-faint ${f.tone}`} d={path(f.points, sx, sy)} />
      ))}
      {series.map((s) => (
        <path key={s.key} className={`ch-line ${s.tone}`} d={path(s.points, sx, sy)} pathLength={1} />
      ))}
      {ends.map(({ s, y }) => (
        <text key={s.key} className={`ch-end ${s.tone}`} x={W - M.r + 8} y={y} dominantBaseline="middle">{s.endLabel}</text>
      ))}
    </svg>
  );
}

// ---------- 对比条：一行一个指标，对照一个点、运行 2 一个点 ----------

export interface DuoRow {
  key: string;
  title: string;
  /** 0–1 的位置；null 表示该值缺失，不画点 */
  base: number | null;
  lead: number | null;
  /** 背景值（运行 1），画成短竖线 */
  context: number | null;
  /** 零点位置（有正有负的指标才给） */
  zero?: number;
  baseText: string;
  leadText: string;
  diffText: string;
  diffTone: 'up' | 'down' | 'flat';
  ariaLabel: string;
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));
const left = (v: number) => ({ left: `${clamp(v) * 100}%` });

export function DuoChart({ rows, head }: { rows: DuoRow[]; head: [string, string, string] }) {
  return (
    <div className="bd-duo" role="table">
      <div className="bd-duo-row bd-duo-head" role="row">
        <span role="columnheader">指标</span>
        <span role="columnheader" aria-hidden="true" />
        {head.map((h) => <span key={h} role="columnheader" className="num">{h}</span>)}
      </div>
      {rows.map((r) => (
        <div key={r.key} className="bd-duo-row" role="row">
          <span role="rowheader">{r.title}</span>
          <span className="bd-duo-track" role="img" aria-label={r.ariaLabel}>
            {r.zero !== undefined && <i className="zero" style={left(r.zero)} />}
            {r.base !== null && r.lead !== null && (
              <i
                className={`link ${r.diffTone}`}
                style={{ left: `${clamp(Math.min(r.base, r.lead)) * 100}%`, width: `${Math.abs(clamp(r.lead) - clamp(r.base)) * 100}%` }}
              />
            )}
            {r.context !== null && <i className="tick" style={left(r.context)} />}
            {r.base !== null && <i className="dot base" style={left(r.base)} />}
            {r.lead !== null && <i className="dot lead" style={left(r.lead)} />}
          </span>
          <span role="cell" className={`num base${r.base === null ? ' none' : ''}`}>{r.baseText}</span>
          <span role="cell" className={`num${r.lead === null ? ' none' : ''}`}>{r.leadText}</span>
          <span role="cell" className={`num bd-diff ${r.diffTone}`}>{r.diffText}</span>
        </div>
      ))}
    </div>
  );
}

// ---------- 门禁条：每份候选一条，上一代基线是一条贯穿的竖线 ----------

export interface GateRow {
  key: string;
  name: string;
  /** 0–1；null 表示没有跑验证 */
  value: number | null;
  valueText: string;
  verdict: string;
  chosen: boolean;
}

export function GateChart({ rows, baseline, baselineLabel }: { rows: GateRow[]; baseline: number; baselineLabel: ReactNode }) {
  return (
    <div className="bd-gatechart">
      <div className="bd-gate-rows" style={{ ['--baseline' as string]: `${clamp(baseline) * 100}%` }}>
        {rows.map((r) => (
          <div key={r.key} className={`bd-gate-row${r.chosen ? ' chosen' : ''}`}>
            <span className="bd-gate-name">{r.name}</span>
            <span className="bd-gate-track">
              {r.value === null
                ? <i className="bar none" />
                : <i className={`bar${r.chosen ? ' lead' : ''}`} style={{ width: `${clamp(r.value) * 100}%` }} />}
            </span>
            <span className={`num${r.value === null ? ' none' : ''}`}>{r.valueText}</span>
            <span className="bd-gate-verdict">{r.verdict}</span>
          </div>
        ))}
      </div>
      <p className="bd-gate-baseline">{baselineLabel}</p>
    </div>
  );
}
