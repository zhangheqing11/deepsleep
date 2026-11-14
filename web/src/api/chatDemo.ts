// ⚠ 用户端“聊一聊”的交互演示：固定示例回复，没有连接模型，也没有经过安全层。
// - 只能选择预设消息，不开放自由输入（自由输入涉及真实用户数据与安全层，待团队决定）。
// - 回复文案是占位示例，正式文案需按 BACKLOG B 节流程审核。
// - 接口形状是前端占位草案，未与后端确认；后端聊天接口确定后，用同一个 ChatClient 接口换成真实实现。

import { ApiError } from './errors';

export interface Preset {
  id: string;
  text: string;
}

export interface Suggestion {
  id: string;
  title: string;
  body: string;
  /** “换一种”时切换到的建议 */
  alternative_id?: string;
}

export interface MemoryCandidate {
  text: string;
  valid_days: number | null;
}

export interface ChatReply {
  reply_id: string;
  text: string;
  suggestion: Suggestion | null;
  memory_candidate: MemoryCandidate | null;
  quick_replies: Preset[];
}

export interface ChatClient {
  readonly mode: 'demo';
  openingReply(): ChatReply;
  /** client_message_id 用于重试去重：同一个 ID 重发返回同一条回复 */
  send(input: { client_message_id: string; preset_id: string }, opts?: { signal?: AbortSignal; fail?: boolean }): Promise<ChatReply>;
  suggestion(id: string): Suggestion | null;
}

const P = (id: string, text: string): Preset => ({ id, text });

const PRESETS = {
  today: P('today', '想说说今天'),
  bedtime: P('bedtime', '聊聊睡前习惯'),
  racing: P('racing', '躺下就开始想事情'),
  work: P('work', '工作的事还没做完'),
  fine: P('fine', '白天还行，就是晚上睡不着'),
  late: P('late', '十二点躺下，一点多才睡着'),
  phone: P('phone', '睡前一直在刷手机'),
  listen: P('listen', '先听我说说'),
  tip: P('tip', '给我一个小办法'),
  wake: P('wake', '我想固定起床时间'),
  w0730: P('w0730', '7:30'),
  w0700: P('w0700', '7:00'),
};

const SUGGESTIONS: Record<string, Suggestion> = {
  worry_list: {
    id: 'worry_list',
    title: '睡前 15 分钟，把担心的事写下来',
    body: '写下担心的事和明天的第一步，写完就合上本子，告诉自己“明天再处理”。',
    alternative_id: 'breathing',
  },
  breathing: {
    id: 'breathing',
    title: '躺下后做 5 分钟慢呼吸',
    body: '吸气 4 秒、停 2 秒、呼气 6 秒，注意力放在呼气上。',
    alternative_id: 'worry_list',
  },
  get_up: {
    id: 'get_up',
    title: '困了再上床，躺 20 分钟还清醒就先起来',
    body: '离开床做点安静的事，比如翻翻纸质书，等困意回来再躺下。',
    alternative_id: 'fixed_wake',
  },
  fixed_wake: {
    id: 'fixed_wake',
    title: '每天同一时间起床',
    body: '不管前一晚睡得怎样，起床时间都尽量不变，周末也一样。',
    alternative_id: 'get_up',
  },
  phone_away: {
    id: 'phone_away',
    title: '睡前 30 分钟把手机放到够不着的地方',
    body: '不用一下子戒掉，先从今晚这 30 分钟开始。',
    alternative_id: 'sleep_mode',
  },
  sleep_mode: {
    id: 'sleep_mode',
    title: '给手机设一个睡眠模式',
    body: '到点自动静音、屏幕变灰，减少“再刷一会儿”的念头。',
    alternative_id: 'phone_away',
  },
};

interface ScriptNode {
  text: string;
  suggestion?: string;
  memory?: MemoryCandidate;
  next: Preset[];
}

const OPENING: ScriptNode = {
  text: '晚上好。今晚想先聊点什么？选一个就好。',
  next: [PRESETS.today, PRESETS.bedtime, PRESETS.racing],
};

const SCRIPT: Record<string, ScriptNode> = {
  today: { text: '好呀。今天哪件事现在还占着你的注意力？说一件就好。', next: [PRESETS.work, PRESETS.fine] },
  work: {
    text: '听起来工作一直跟着你回到了床上。今晚先不急着解决它，我们只给它在睡前找个去处。',
    suggestion: 'worry_list',
    next: [PRESETS.wake],
  },
  fine: { text: '白天还行、晚上却睡不着，确实让人着急。你一般几点躺下，几点真正睡着？', next: [PRESETS.late, PRESETS.bedtime] },
  late: {
    text: '从躺下到睡着要一个多小时。有一个小办法可以试试。',
    suggestion: 'get_up',
    next: [PRESETS.wake],
  },
  bedtime: { text: '睡前一小时，你通常在做什么？', next: [PRESETS.phone, PRESETS.late] },
  phone: {
    text: '很多人都会这样，刷着刷着就晚了。今晚可以先试一个小改变。',
    suggestion: 'phone_away',
    next: [PRESETS.wake],
  },
  racing: {
    text: '躺下脑子就停不下来，确实很累。你想先说说在想什么，还是先要一个小办法？',
    next: [PRESETS.listen, PRESETS.tip],
  },
  listen: { text: '好，我在听。不用说得很完整，想到哪说到哪。', next: [PRESETS.work, PRESETS.fine] },
  tip: {
    text: '一个常用的小办法是给担心的事留一个固定的时间和地方。',
    suggestion: 'worry_list',
    next: [PRESETS.wake],
  },
  wake: { text: '固定起床时间是很稳的一步。你希望几点起？', next: [PRESETS.w0730, PRESETS.w0700] },
  w0730: {
    text: '好，先以 07:30 为目标。起不来也没关系，我们再一起调整。',
    memory: { text: '希望每天 07:30 起床', valid_days: 14 },
    next: [PRESETS.racing, PRESETS.bedtime],
  },
  w0700: {
    text: '好，先以 07:00 为目标。起不来也没关系，我们再一起调整。',
    memory: { text: '希望每天 07:00 起床', valid_days: 14 },
    next: [PRESETS.racing, PRESETS.bedtime],
  },
};

function toReply(node: ScriptNode, replyId: string): ChatReply {
  return {
    reply_id: replyId,
    text: node.text,
    suggestion: node.suggestion ? SUGGESTIONS[node.suggestion] : null,
    memory_candidate: node.memory ?? null,
    quick_replies: node.next,
  };
}

const sent = new Map<string, ChatReply>();

export const chatDemo: ChatClient = {
  mode: 'demo',
  openingReply: () => toReply(OPENING, 'reply_opening'),
  suggestion: (id) => SUGGESTIONS[id] ?? null,
  send({ client_message_id, preset_id }, opts = {}) {
    return new Promise((resolve, reject) => {
      const { signal, fail } = opts;
      const t = window.setTimeout(() => {
        if (fail) {
          reject(new ApiError({ kind: 'network', message: '模拟：发送失败' }));
          return;
        }
        const cached = sent.get(client_message_id);
        if (cached) return resolve(cached);
        const node = SCRIPT[preset_id];
        if (!node) {
          reject(new ApiError({ kind: 'http', status: 422, code: 'VALIDATION_ERROR', message: '没有这个预设消息' }));
          return;
        }
        const reply = toReply(node, `reply_${client_message_id}`);
        sent.set(client_message_id, reply);
        resolve(reply);
      }, 900);
      signal?.addEventListener('abort', () => {
        window.clearTimeout(t);
        reject(new ApiError({ kind: 'aborted', message: '请求已取消' }));
      });
    });
  },
};
