import { useEffect, useState } from 'react';
import { DEVCONSOLE_LINK } from '../../config';
import { probeDevconsole, type ProbeResult } from '../../lib/devconsoleLink';

/**
 * 侧栏的“进化后台”入口：普通链接，新标签页打开，原控制台当前页面和运行不受影响。
 * 未配置 / 配置有误 / 目标不是进化后台时明确显示，不给出会跳错的链接。
 */
export function DevconsoleNavLink() {
  const link = DEVCONSOLE_LINK;
  const href = link.state === 'configured' ? link.href : null;
  const [probe, setProbe] = useState<ProbeResult | 'checking'>('checking');

  useEffect(() => {
    if (!href) return;
    let ctrl = new AbortController();
    const check = () => {
      ctrl.abort();
      ctrl = new AbortController();
      const mine = ctrl;
      void probeDevconsole(href, (i, init) => fetch(i, init), mine.signal).then((r) => {
        if (!mine.signal.aborted) setProbe(r);
      });
    };
    check();
    // 回到这个标签页时重新检测（例如进化后台刚部署好）
    const onVisible = () => document.visibilityState === 'visible' && check();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      ctrl.abort();
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [href]);

  if (link.state === 'unconfigured') {
    return (
      <span className="nav-external nav-disabled" aria-disabled="true" title="在 web/.env.local 设置 VITE_DEVCONSOLE_URL">
        进化后台
        <small>尚未配置</small>
      </span>
    );
  }
  if (link.state === 'invalid') {
    return (
      <span className="nav-external nav-disabled" aria-disabled="true" title={`VITE_DEVCONSOLE_URL=${link.raw}：${link.reason}`}>
        进化后台
        <small>地址配置有误</small>
      </span>
    );
  }
  if (probe === 'not_deployed') {
    return (
      <span className="nav-external nav-disabled" aria-disabled="true" title={`${link.href} 不是进化后台（标识文件不存在或不匹配）`}>
        进化后台
        <small>待部署</small>
      </span>
    );
  }
  return (
    <a className="nav-external" href={link.href} target="_blank" rel="noopener noreferrer">
      <span>
        进化后台 <span aria-hidden="true">↗</span>
        <span className="sr-only">（在新标签页打开）</span>
      </span>
      <small>
        {probe === 'unreachable' ? '未能确认是否已启动' : probe === 'checking' ? '检测中…' : '实时指标与学习过程'}
      </small>
    </a>
  );
}
