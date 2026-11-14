import type { ExperimentManifest } from '../api/extensionTypes';
import type { ExperimentData } from '../hooks/useExperimentData';
import { versionInfo } from '../model/overview';
import { Badge } from './common';

/** ③ 怎么回退：版本链来自数据；只展示命令，不提供回退按钮（进化后台只读）。 */
export function RollbackPanel({ m, data }: { m: ExperimentManifest; data: ExperimentData }) {
  const evo = data.evolution.data;
  const v = versionInfo(m, data.status.data, evo);
  const commit = evo?.outcome === 'committed' ? evo.commit : null;
  return (
    <section className="panel" aria-labelledby="q3">
      <h2 id="q3">
        <span className="q">③</span>怎么回退
      </h2>
      <div className="versions" aria-label="playbook 版本">
        {v.previous && (
          <>
            <span className="version">{v.previous}</span>
            <span aria-hidden="true">→</span>
          </>
        )}
        <span className="version version-head">
          {v.current ?? '暂无'}
          {v.current && <small>当前</small>}
        </span>
      </div>
      <p className="small muted">来源：{v.source}</p>
      {commit && (
        <p className="small">
          提交 <code>{commit.sha.slice(0, 7)}</code> · {commit.author || '作者未记录'}
          {commit.message && <span className="muted"> · {commit.message}</span>}
        </p>
      )}
      {evo?.outcome === 'kept_previous' && <p className="small">本次学习自动保留了上一代，没有产生新版本。</p>}

      <ul className="guarantees">
        <li>
          <Badge tone="info">门禁</Badge> 每份改动先在验证集 C 上验证，主指标不高于上一代就不提交
        </li>
        <li>
          <Badge tone="info">人工</Badge> 高关键度改动有审核窗口，人只能否决，不能放行被拦下的改动
        </li>
        <li>
          <Badge tone="info">安全</Badge> 危机识别是冻结的规则层，不参与进化
        </li>
      </ul>

      <div className="rollback">
        <p className="small">playbook 存在独立的 git 版本库里，每一代都是一次提交。回退也是一次新提交，历史保留：</p>
        {v.previous ? (
          <pre className="cmd">python -m engine.evolve rollback {v.previous}</pre>
        ) : (
          <p className="small muted">还没有可回退的上一代版本。</p>
        )}
        <p className="small muted">进化后台只读，不提供回退按钮；回退由操作员在终端执行。</p>
      </div>
    </section>
  );
}
