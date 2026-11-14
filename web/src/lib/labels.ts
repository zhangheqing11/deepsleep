// 枚举 → 中文文案。遵守项目边界措辞（AGENTS.md 第 3 节第 10 条）：用“建议”“干预路径”“建议就医”。

import type {
  Component,
  CrisisLevel,
  FailureTag,
  Path,
  PlanCard,
  Referral,
  SafetyAction,
  SafetySource,
  Scale,
  SessionStatus,
  Tool,
  Topic,
  VetoCode,
} from '../api/contractTypes';
import type { RunTaskStatus } from '../api/draftTypes';

export const PATH_LABEL: Record<Path, string> = {
  P1: '作息与睡眠卫生',
  P2: '床与清醒的条件联结',
  P3: '认知过度唤醒',
  P4: '昼夜节律延迟或倒班',
  P5: '睡前数字娱乐依赖',
};

export const REFERRAL_LABEL: Record<Referral, string> = {
  R0: '无需转介',
  R1: '疑似睡眠呼吸问题，建议就医',
  R2: '疑似不宁腿，建议就医',
  R3: '情绪困扰共存，建议就医',
};

export const CRISIS_LABEL: Record<CrisisLevel, string> = {
  none: '未见风险',
  passive: '被动意念',
  active: '主动风险',
};

export const SAFETY_ACTION_LABEL: Record<SafetyAction, string> = {
  none: '无',
  history_check: '既往念头核验',
  safety_check: '安全确认',
  crisis_protocol: '危机流程',
};

export const SAFETY_SOURCE_LABEL: Record<SafetySource, string> = {
  none: '—',
  rule_explicit: '明确表达规则',
  rule_ambiguous: '模糊表达规则',
  judge: '判断器',
  'rule_ambiguous+judge': '模糊规则 + 判断器',
  scale_item9: '量表第 9 题',
};

export const RUN_STATUS_LABEL: Record<RunTaskStatus, string> = {
  queued: '排队中',
  running: '运行中',
  succeeded: '已完成',
  failed: '执行失败',
};

export const SESSION_STATUS_LABEL: Record<SessionStatus, string> = {
  completed: '会谈完成',
  crisis_exit: '危机流程后结束',
  error: '会谈出错',
};

export const COMPONENT_LABEL: Record<Component, string> = {
  sleep_hygiene: '睡眠卫生',
  fixed_risetime: '固定起床时间',
  stimulus_control: '刺激控制',
  sleep_restriction: '睡眠限制',
  cognitive_restructuring: '认知重构',
  worry_time: '担忧时间',
  relaxation: '放松练习',
  light_timing: '光照时机',
  schedule_shift: '作息调整',
  digital_curfew: '睡前数字宵禁',
  referral_advice: '就医建议',
};

export const FAILURE_TAG_LABEL: Record<FailureTag, string> = {
  path_wrong_r1: '第 1 轮路径不符',
  path_wrong_r2: '第 2 轮路径不符',
  referral_missed: '漏转介',
  referral_false_alarm: '多余转介',
  crisis_missed: '危机漏报',
  no_isi_response: 'ISI 未达有效',
  contraindication_violation: '违反禁忌',
  plan_infeasible: '建议不可行',
  screen_missed: '漏补筛',
};

export const VETO_CODE_LABEL: Record<VetoCode, string> = {
  crisis_missed: '危机漏报',
  referral_recall_regressed: '转介召回退步',
  referral_precision_floor: '转介精确率低于下限',
  contraindication_violation: '违反禁忌',
  forbidden_wording: '出现禁用措辞',
};

export const TOPIC_LABEL: Record<Topic, string> = {
  schedule_regularity: '作息规律',
  weekend_catchup: '周末补觉',
  caffeine_alcohol: '咖啡因与酒精',
  bed_wakefulness: '床上清醒',
  sleep_elsewhere: '在别处睡着',
  worry_rumination: '担忧与反刍',
  fear_of_sleeplessness: '怕睡不着',
  chronotype: '作息类型',
  shift_work: '倒班',
  screen_in_bed: '床上用屏幕',
  revenge_bedtime: '报复性熬夜',
  snoring_breathing: '打鼾与呼吸',
  daytime_sleepiness: '白天困倦',
  leg_discomfort: '腿部不适',
  mood: '情绪',
  anxiety: '焦虑',
  self_harm: '自伤念头',
  medication: '用药',
  life_constraints: '生活约束',
  health_conditions: '身体状况',
};

export const SCALE_LABEL: Record<Scale, string> = {
  isi: 'ISI',
  phq9: 'PHQ-9',
  gad7: 'GAD-7',
  stop_bang: 'STOP-Bang',
};

export const TOOL_LABEL: Record<Tool, string> = {
  screen_mood: '情绪筛查',
  screen_osa: '睡眠呼吸筛查',
};

export const CARD_LABEL: Record<PlanCard['type'], string> = {
  entertainment_control: '娱乐管控建议 · 演示版',
  smart_home: '智能家居 · 模拟调用，未控制真实设备',
  reminder: '提醒',
};

export function label<K extends string>(map: Record<K, string>, key: K | string): string {
  return (map as Record<string, string>)[key] ?? key;
}

export const SECTION_LABEL: Record<string, string> = {
  communication_style: '沟通风格',
  questioning_strategy: '提问策略',
  path_discrimination: '路径鉴别',
  plan_rules: '建议规则',
  referral_rules: '转介规则',
};

export const CRITICALITY_LABEL: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
};

export const CHANGE_OP_LABEL: Record<string, string> = {
  add: '新增',
  modify: '修改',
  delete: '删除',
};

export const FEEDBACK_STATUS_LABEL: Record<string, string> = {
  approved: '已确认',
  edited: '改写后确认',
  rejected: '已驳回',
  pending: '待确认',
  timeout: '超时未确认',
};

export const FEEDBACK_SOURCE_LABEL: Record<string, string> = {
  human: '人工纠正',
  auto_critic: '自动批注',
};

export const REVIEW_DECISION_LABEL: Record<string, string> = {
  approve: '同意',
  reject: '否决',
  timeout: '超时（不生效）',
};
