// 部分复制自 web/src/lib/labels.ts（main@0732150，2026-11-14）。只保留进化后台用到的文案。
// 遵守项目边界措辞：用“建议”“干预路径”“建议就医”，不出现“诊断”“治疗失眠症”。

export function label(map: Record<string, string>, key: string): string {
  return map[key] ?? key;
}

export const SECTION_LABEL: Record<string, string> = {
  communication_style: '沟通风格',
  questioning_strategy: '提问策略',
  path_discrimination: '路径鉴别',
  plan_rules: '建议规则',
  referral_rules: '转介规则',
};

export const CRITICALITY_LABEL: Record<string, string> = { low: '低', medium: '中', high: '高' };

export const CHANGE_OP_LABEL: Record<string, string> = { add: '新增', modify: '修改', delete: '删除' };

export const VETO_CODE_LABEL: Record<string, string> = {
  crisis_missed: '危机漏报',
  referral_recall_regressed: '转介召回退步',
  referral_precision_floor: '转介精确率低于下限',
  contraindication_violation: '违反禁忌',
  forbidden_wording: '出现禁用措辞',
  hard_rule: '硬规则',
};

export const REVIEW_DECISION_LABEL: Record<string, string> = {
  approve: '同意',
  reject: '否决',
  timeout: '超时（不生效）',
};

export const STAGE_STATE_LABEL: Record<string, string> = {
  pending: '等待',
  running: '进行中',
  done: '完成',
  failed: '失败',
};

export const STAGE_LABEL: Record<string, string> = {
  run1: '运行 1',
  learning: '学习',
  run2: '运行 2 与对照',
  control: '对照',
  done: '已完成',
  failed: '已失败',
};

export const EXECUTION_MODE_LABEL: Record<string, string> = {
  real: '真实模型',
  mock: '后端 Mock（非模型结果）',
};
