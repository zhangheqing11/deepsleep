// 逐代曲线：横轴是 playbook 版本（v1、v2 …），纵轴是留出集 B 组的 ISI 有效率。
// 手写 SVG，与看板图表（components/board/charts.tsx）同一套画法：横向细网格、无 y 轴线、直接标注不另放图例。
// 只画传进来的数，不计算指标；数据整理在 lib/generationCurve.ts。
import offlineFile from '../data/offlineGenerationCurve.json';
import type { PipelineCurve } from '../api/extensionTypes';
import {
  CURVE_CAPTION,
  CURVE_EMPTY,
  formatIncrement,
  incrementTone,
  liveCurveModel,
  offlineCurveModel,
  type ChartModel,
  type OfflineCurveFile,
} from '../lib/generationCurve';
import '../generationCurve.css';

/** viewBox 尺寸：normal 用于宽的面板（看板）；compact 用于窄卡片（全链路页），字号在屏幕上不至于缩得太小 */
const SIZE = { normal: { W: 640, H: 236 }, compact: { W: 440, H: 200 } } as const;
export type CurveSize = keyof typeof SIZE;

/** 版本是类别：每个版本占一格，点画在格子中间。只有一个版本时它在正中间。 */
export function CurveChart({ model, ariaLabel, size = 'normal' }: { model: ChartModel; ariaLabel: string; size?: CurveSize }) {
  const { W, H } = SIZE[size];
  const { versions, points, dots, thin, ceiling, axis } = model;
  const n = Math.max(1, versions.length);
  const M = { l: 40, r: thin.length > 0 ? 44 : 14, t: 24, b: 26 };
  const band = (W - M.l - M.r) / n;
  const sx = (i: number) => M.l + (i + 0.5) * band;
  const sy = (v: number) => M.t + ((axis.max - v * 100) / (axis.max - axis.min || 1)) * (H - M.t - M.b);
  const dense = band < 60;

  const mainPts = points.map((p, i) => (p.mean === null ? null : { i, x: sx(i), y: sy(p.mean), p })).filter((p) => p !== null);
  const line = mainPts.map((p, k) => `${k === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');

  // 同一版本的几次运行左右错开一点，不叠成一个点
  const perIndex = new Map<number, number>();
  for (const d of dots) perIndex.set(d.index, (perIndex.get(d.index) ?? 0) + 1);
  const seenIndex = new Map<number, number>();
  const dotPos = dots.map((d) => {
    const k = seenIndex.get(d.index) ?? 0;
    seenIndex.set(d.index, k + 1);
    const count = perIndex.get(d.index) ?? 1;
    const spread = Math.min(5, band / (count + 2));
    return { ...d, x: sx(d.index) + (k - (count - 1) / 2) * spread, y: sy(d.value) };
  });

  // 单条链的线尾标签：写在最后一个点右侧（让开单次运行的小圆点），两条链末端太近时上下错开
  const thinLines = thin.map((t) => {
    const pts = t.values.map((v, i) => (v === null ? null : { x: sx(i), y: sy(v) })).filter((p) => p !== null);
    const last = pts[pts.length - 1];
    return { key: t.label, pts, label: last ? { x: last.x + 14, y: last.y } : null };
  });
  const labelled = thinLines.filter((t) => t.label).sort((a, b) => a.label!.y - b.label!.y);
  for (let i = 1; i < labelled.length; i++) {
    const gap = labelled[i].label!.y - labelled[i - 1].label!.y;
    if (gap < 14) {
      const shift = (14 - gap) / 2;
      labelled[i - 1].label!.y -= shift;
      labelled[i].label!.y += shift;
    }
  }

  return (
    <svg className="gc-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={ariaLabel}>
      {axis.ticks.map((t) => {
        const y = M.t + ((axis.max - t) / (axis.max - axis.min || 1)) * (H - M.t - M.b);
        return (
          <g key={t}>
            <line className="gc-grid" x1={M.l} x2={W - M.r} y1={y} y2={y} />
            <text className="gc-tick" x={M.l - 7} y={y} textAnchor="end" dominantBaseline="middle">{`${t}%`}</text>
          </g>
        );
      })}
      {versions.map((v, i) => (
        <text key={v} className="gc-tick gc-xtick" x={sx(i)} y={H - 6} textAnchor="middle">{v}</text>
      ))}
      {ceiling && (
        <g>
          <line className="gc-ceiling" x1={M.l} x2={W - M.r} y1={sy(ceiling.value)} y2={sy(ceiling.value)} />
          <text className="gc-note" x={M.l + 4} y={sy(ceiling.value) - 6}>{ceiling.label}</text>
        </g>
      )}
      {thinLines.map((t) => (
        <g key={t.key} className="gc-thin">
          {t.pts.length > 1 && <path d={t.pts.map((p, k) => `${k === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')} />}
          {t.label && <text className="gc-thin-label" x={t.label.x} y={t.label.y} dominantBaseline="middle">{t.key}</text>}
        </g>
      ))}
      {mainPts.length > 1 && <path className="gc-line" d={line} />}
      {mainPts.slice(1).map((p, k) => {
        const prev = mainPts[k];
        const text = formatIncrement(p.p.deltaPp);
        if (!text) return null;
        // 增量写在线段中点的下方
        return (
          <text
            key={`d-${p.p.version}`}
            className={`gc-delta ${incrementTone(p.p.deltaPp)}${dense ? ' dense' : ''}`}
            x={(prev.x + p.x) / 2}
            y={(prev.y + p.y) / 2 + 16}
            textAnchor="middle"
          >
            {text}
          </text>
        );
      })}
      {mainPts.map((p) => (
        <g key={`m-${p.p.version}`}>
          <circle className="gc-mean" cx={p.x} cy={p.y} r={4.5} />
          <text className={`gc-value${dense ? ' dense' : ''}`} x={p.x} y={p.y - 11} textAnchor="middle">
            {`${((p.p.mean as number) * 100).toFixed(1)}%`}
          </text>
        </g>
      ))}
      {/* 单次运行画在最上层：标签不会把它们盖住 */}
      {dotPos.map((d) => (
        <circle key={d.key} className="gc-run" cx={d.x} cy={d.y} r={2.6} />
      ))}
    </svg>
  );
}

function chartLabel(model: ChartModel): string {
  return model.points
    .map((p) => `${p.version} ${p.mean === null ? '—' : `${(p.mean * 100).toFixed(1)}%`}${p.deltaPp === null ? '' : `（${formatIncrement(p.deltaPp)} 个百分点）`}`)
    .join('，');
}

// ---------- 现场：当前进化链 ----------

export function LiveGenerationCurve({ curve, title, size }: { curve: PipelineCurve | null | undefined; title?: string; size?: CurveSize }) {
  const model = liveCurveModel(curve);
  const meta = [
    model.experiments !== null && model.experiments > 0 ? `${model.experiments} 次实验` : null,
    model.mode === 'mock' ? '演练数据 · 未调用模型' : null,
  ].filter(Boolean);
  return (
    <div className="gc gc-live">
      {(title || meta.length > 0) && (
        <div className="gc-head">
          {title && <h3 className="gc-title">{title}</h3>}
          {meta.length > 0 && <p className={`gc-sub${model.mode === 'mock' ? ' gc-mock' : ''}`}>{meta.join(' · ')}</p>}
        </div>
      )}
      {model.empty ? (
        <p className="gc-empty">{CURVE_EMPTY}</p>
      ) : (
        <div className="gc-body">
          <div className="gc-figure">
            <CurveChart model={model} size={size} ariaLabel={`逐代曲线：${chartLabel(model)}`} />
          </div>
          <div className="gc-side">
            <ol className="gc-rows" aria-label="各版本">
              {model.rows.map((r) => (
                <li key={r.version} className="gc-row">
                  <span className="gc-v">{r.version}</span>
                  <span className="gc-mean-text">{r.meanText}</span>
                  {r.deltaText && <span className={`gc-delta-text ${r.deltaTone}`}>{r.deltaText}</span>}
                  <span className="gc-n">{r.runsText}</span>
                  {r.referralText && <span className="gc-ref">{r.referralText}</span>}
                  <span className="gc-learned" title={r.learned}>{r.learned}</span>
                </li>
              ))}
            </ol>
            {model.rejected.length > 0 && (
              <ul className="gc-rejected" aria-label="未采纳新版本的代">
                {model.rejected.map((t, i) => <li key={i}>{t}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}
      <p className="gc-caption">{CURVE_CAPTION}</p>
    </div>
  );
}

// ---------- 离线复测 ----------

export const OFFLINE_MODEL = offlineCurveModel(offlineFile as OfflineCurveFile);

export function OfflineGenerationCurve() {
  const model = OFFLINE_MODEL;
  return (
    <figure className="gc gc-offline">
      <div className="gc-head">
        <h3 className="gc-title">{model.title}</h3>
        <p className="gc-sub">{model.subline}</p>
      </div>
      <CurveChart model={model} ariaLabel={`两条链的平均：${chartLabel(model)}`} />
      <ul className="gc-legend">
        <li><i className="gc-key-line" />两条链的平均</li>
        <li><i className="gc-key-thin" />单条链（{model.thin.map((t) => t.label).join('、')}）</li>
        <li><i className="gc-key-dot" />单次运行</li>
      </ul>
      <figcaption className="gc-sentence">{model.sentence}</figcaption>
    </figure>
  );
}
