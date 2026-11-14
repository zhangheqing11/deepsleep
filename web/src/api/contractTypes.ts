// 业务数据类型：手写自 contracts/*.schema.json v0.1.0（已合入 main，PR #1）。
// 这里只收录前端会读取的 run_report、session 与 evolution；契约升级（如 v0.1.1）后必须对照 schema 同步。
// 不要在这里加契约里没有的字段。

export type Path = 'P1' | 'P2' | 'P3' | 'P4' | 'P5';
export type Referral = 'R0' | 'R1' | 'R2' | 'R3';
export type CrisisLevel = 'none' | 'passive' | 'active';
export type Split = 'A' | 'B' | 'C' | 'offline' | 'sample';
export type SafetySource =
  | 'none'
  | 'rule_explicit'
  | 'rule_ambiguous'
  | 'judge'
  | 'rule_ambiguous+judge'
  | 'scale_item9';
export type SafetyAction = 'none' | 'history_check' | 'safety_check' | 'crisis_protocol';
export type JudgeStatus = 'ok' | 'timeout' | 'error' | 'skipped';
export type Scale = 'isi' | 'phq9' | 'gad7' | 'stop_bang';
export type Tool = 'screen_mood' | 'screen_osa';
export type Topic =
  | 'schedule_regularity'
  | 'weekend_catchup'
  | 'caffeine_alcohol'
  | 'bed_wakefulness'
  | 'sleep_elsewhere'
  | 'worry_rumination'
  | 'fear_of_sleeplessness'
  | 'chronotype'
  | 'shift_work'
  | 'screen_in_bed'
  | 'revenge_bedtime'
  | 'snoring_breathing'
  | 'daytime_sleepiness'
  | 'leg_discomfort'
  | 'mood'
  | 'anxiety'
  | 'self_harm'
  | 'medication'
  | 'life_constraints'
  | 'health_conditions';
export type Component =
  | 'sleep_hygiene'
  | 'fixed_risetime'
  | 'stimulus_control'
  | 'sleep_restriction'
  | 'cognitive_restructuring'
  | 'worry_time'
  | 'relaxation'
  | 'light_timing'
  | 'schedule_shift'
  | 'digital_curfew'
  | 'referral_advice';
export type FailureTag =
  | 'path_wrong_r1'
  | 'path_wrong_r2'
  | 'referral_missed'
  | 'referral_false_alarm'
  | 'crisis_missed'
  | 'no_isi_response'
  | 'contraindication_violation'
  | 'plan_infeasible'
  | 'screen_missed';
export type VetoCode =
  | 'crisis_missed'
  | 'referral_recall_regressed'
  | 'referral_precision_floor'
  | 'contraindication_violation'
  | 'forbidden_wording';

/** 0–1 */
export type Ratio = number;
/** 0–1 或 null（无法计算） */
export type NullableRatio = number | null;

// ---------- run_report ----------

export interface Metrics {
  isi_response_rate: Ratio;
  mean_isi_change: number;
  path_acc_r1: Ratio;
  path_acc_r2: Ratio;
  /** = r2 − r1，由计分模块给出，取值 −1–1 */
  path_acc_gain: number;
  referral_recall: NullableRatio;
  referral_precision: NullableRatio;
  referral_recall_by_label: { R1: NullableRatio; R2: NullableRatio; R3: NullableRatio };
  crisis_recall: NullableRatio;
  crisis_missed: number;
  contraindication_violations: number;
  screening_coverage: NullableRatio;
}

export interface Veto {
  passed: boolean;
  reasons: { code: VetoCode; message: string }[];
}

export interface PerVisitorRow {
  visitor_id: string;
  main_path: Path;
  path_pred_r1: Path;
  path_pred_r2: Path;
  referral_true: Referral;
  referral_pred: Referral;
  crisis_true: CrisisLevel;
  crisis_pred: CrisisLevel;
  isi_baseline: number;
  /** 第 0–4 周，长度 5 */
  isi_week: number[];
  isi_change: number;
  responder: boolean;
  adherence: Ratio;
  alliance: Ratio;
  failure_tags: FailureTag[];
  /** 文件相对路径，前端不使用，会谈一律走 API */
  session_ref: string;
  prefilled_scales: Scale[];
  screened: Tool[];
}

export interface RunReport {
  schema_version: string;
  run_id: string;
  label: string;
  role: 'run1' | 'run2' | 'control' | 'validation' | 'offline';
  created_at: string;
  /** 秒（契约字段，不改为 _ms） */
  duration_s: number;
  playbook_version: string;
  split: Split;
  n_visitors: number;
  models: { agent: string; visitor: string; judge: string };
  metrics: Metrics;
  veto: Veto;
  safety_summary: {
    judge_provider: string;
    judge_calls: number;
    judge_fallbacks: number;
    safety_checks: number;
    crisis_protocols: number;
  };
  per_visitor: PerVisitorRow[];
}

// ---------- session ----------

export type SessionStatus = 'completed' | 'crisis_exit' | 'error';

export interface TranscriptTurn {
  turn: number;
  speaker: 'agent' | 'visitor' | 'safety';
  text: string;
  revealed_clue_ids: string[];
}

export interface SessionRound {
  round: 1 | 2;
  transcript: TranscriptTurn[];
  asked_topics: Topic[];
  path_pred: Path;
  path_confidence: NullableRatio;
  referral_pred: Referral;
  crisis_level: CrisisLevel;
}

export interface PlanCard {
  type: 'entertainment_control' | 'smart_home' | 'reminder';
  title: string;
  body: string;
}

export interface Plan {
  bedtime: string;
  risetime: string;
  tib_minutes: number;
  components: Component[];
  rationale_given: boolean;
  contraindications_checked: boolean;
  referral_advice: string | null;
  cards: PlanCard[];
}

export interface Behaviors {
  goal_setting: number;
  reflection: number;
  emotion_response: number;
  rationale_explained: number;
  lecturing: number;
  premature_advice: number;
}

export interface SafetyEvent {
  round: 1 | 2;
  /** 0 = 会谈前自评表 */
  turn: number;
  level: CrisisLevel;
  source: SafetySource;
  action: SafetyAction;
  judge_status: JudgeStatus;
  judge_provider: string;
  judge_probs: { none: number; history: number; passive: number; active: number } | null;
  matched: string;
}

export type ToolResult =
  | { phq9: number; phq9_items: number[]; gad7: number }
  | { stop_bang: number };

export interface ToolCall {
  round: 1 | 2;
  turn: number;
  tool: Tool;
  result: ToolResult;
}

export interface PrefilledScale {
  scale: Scale;
  reported_score: number;
  items: number[] | null;
}

export interface Session {
  schema_version: string;
  /** "<run_id>/<visitor_id>"，含斜杠，不能放进 URL */
  session_id: string;
  run_id: string;
  visitor_id: string;
  playbook_version: string;
  models: { agent: string; visitor: string };
  status: SessionStatus;
  error: string | null;
  context_scales: PrefilledScale[];
  tool_calls: ToolCall[];
  rounds: SessionRound[];
  plan: Plan | null;
  behaviors: Behaviors;
  safety_events: SafetyEvent[];
}

// ---------- evolution ----------

export type PlaybookSection =
  | 'communication_style'
  | 'questioning_strategy'
  | 'path_discrimination'
  | 'plan_rules'
  | 'referral_rules';
export type Criticality = 'low' | 'medium' | 'high';

export interface EvolutionChange {
  id: string;
  op: 'add' | 'modify' | 'delete';
  section: PlaybookSection;
  before: string | null;
  after: string | null;
  reason: string;
  criticality_rule: Criticality;
  criticality_self: Criticality;
  criticality: Criticality;
}

export interface EvolutionCandidate {
  id: 'c1' | 'c2' | 'c3';
  summary: string;
  changes: EvolutionChange[];
  hard_rule_violations: { code: string; change_id: string; message: string }[];
  /** 被硬规则拦下、未跑验证时为 null */
  val_metrics: Metrics | null;
  veto: Veto;
  passed: boolean;
}

export interface HumanFeedback {
  id: string;
  kind: 'correction' | 'score' | 'demonstration';
  source: 'human' | 'auto_critic';
  status: 'approved' | 'rejected' | 'edited' | 'pending' | 'timeout';
  visitor_id: string | null;
  text: string | null;
  score: number | null;
}

export interface Evolution {
  schema_version: string;
  evolution_id: string;
  created_at: string;
  from_version: string;
  /** 全部候选被否决时为 null */
  to_version: string | null;
  outcome: 'committed' | 'kept_previous';
  source_run_id: string;
  val_split: string;
  baseline_val_metrics: Metrics;
  reflector: { model: string; fell_back: boolean; fallback_reason: string | null };
  failures_used: { visitor_id: string; failure_tags: FailureTag[] }[];
  human_feedback: HumanFeedback[];
  candidates: EvolutionCandidate[];
  human_review: {
    change_id: string;
    decision: 'approve' | 'reject' | 'timeout';
    scores: { safety: number; clinical: number; feasibility: number } | null;
    comment: string | null;
  }[];
  chosen: string | null;
  commit: { repo: string; sha: string; author: string; message: string } | null;
  diff: string | null;
}
