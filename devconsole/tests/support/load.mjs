// 用 Vite 自带的 esbuild 把 tests/support/entry.ts（真实源码）打包成 ESM 后导入，供 node --test 使用。
// 不新增依赖；每个测试文件各自加载一份，互不共享模块状态。
import { build } from 'esbuild';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
export const CONTRACT_EXAMPLES = join(here, '..', '..', '..', 'contracts', 'examples');

export function example(name) {
  return JSON.parse(readFileSync(join(CONTRACT_EXAMPLES, name), 'utf-8'));
}

export async function loadModules(env = {}) {
  globalThis.window = globalThis;
  const result = await build({
    entryPoints: [join(here, 'entry.ts')],
    bundle: true,
    format: 'esm',
    platform: 'browser',
    write: false,
    logLevel: 'silent',
    define: {
      'import.meta.env': JSON.stringify({ PROD: false, ...env }),
      'process.env.NODE_ENV': '"test"',
    },
  });
  const dir = mkdtempSync(join(tmpdir(), 'ds-devconsole-test-'));
  const file = join(dir, 'bundle.mjs');
  writeFileSync(file, result.outputFiles[0].text);
  return import(pathToFileURL(file).href);
}

/** 可手动推进的计时器：advance(ms) 依次执行到期的回调。 */
export class FakeTimers {
  constructor() {
    this.now = 0;
    this.seq = 0;
    this.queue = new Map();
  }
  setTimeout(fn, ms) {
    const id = ++this.seq;
    this.queue.set(id, { at: this.now + ms, fn });
    return id;
  }
  clearTimeout(id) {
    this.queue.delete(id);
  }
  pending() {
    return [...this.queue.values()].map((t) => t.at - this.now).sort((a, b) => a - b);
  }
  async advance(ms) {
    const target = this.now + ms;
    // 先让已完成的 Promise 回调跑完，和真实事件循环一致（微任务先于计时器）。
    await flush();
    for (;;) {
      const due = [...this.queue.entries()].filter(([, t]) => t.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      this.queue.delete(due[0]);
      this.now = due[1].at;
      due[1].fn();
      await flush();
    }
    this.now = target;
    await flush();
  }
}

export async function flush() {
  for (let i = 0; i < 10; i += 1) await new Promise((r) => setImmediate(r));
}
