import type { ExecutionMode } from '../api/draftTypes';
import type { AdapterKind } from '../config';
import { Badge } from './common';

/** 页面必须区分“模拟数据”和“真实运行”（历史回放待 GET /runs 列表接口，后续实现） */
export function DataSourceBadge({ adapter, mode }: { adapter: AdapterKind; mode?: ExecutionMode | null }) {
  if (adapter === 'mock') return <Badge tone="mock">模拟数据 · 前端本地</Badge>;
  if (mode === 'mock') return <Badge tone="mock">模拟数据 · 后端 Mock</Badge>;
  if (mode === 'real') return <Badge tone="info">真实运行</Badge>;
  return <Badge>数据来源待确认</Badge>;
}

export function DataSourceBanner({ adapter, mode }: { adapter: AdapterKind; mode?: ExecutionMode | null }) {
  if (adapter === 'mock') {
    return (
      <div className="banner banner-mock" role="note">
        <strong>模拟数据</strong>
        <span>
          当前使用前端本地模拟适配器，没有连接后端。报告与会谈内容取自 contracts 示例 JSON，进度与错误按接口草案模拟。
        </span>
      </div>
    );
  }
  if (mode === 'mock') {
    return (
      <div className="banner banner-mock" role="note">
        <strong>模拟数据</strong>
        <span>后端处于 Mock 模式，返回的是开发用模拟结果。</span>
      </div>
    );
  }
  return null;
}
