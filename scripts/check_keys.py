#!/usr/bin/env python3
"""Check root .env without disclosing values or provider response bodies."""
import asyncio
import contextlib
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
TEXT = '最近睡不好，躺下脑子停不下来'
TIMEOUT = 15
PROVIDERS = {
    'ds_flash': ('DS_API_KEY', 'DS_BASE_URL', 'DS_MODEL'),
    'jev': ('TYPESAFE_API_KEY',),
    'gemini_decision': ('GEMINI_API_KEY',),
    'startlux': ('STARTLUX_API_KEY',),
    'anthropic': ('ANTHROPIC_API_KEY',),
}


def read_env(path):
    if not path.exists():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        # Single-line KEY=value, optional export, quotes and inline comments.
        result = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$', line)
            if not match:
                continue
            key, value = match.groups()
            if value.startswith(('"', "'")):
                quote = value[0]
                end = value.find(quote, 1)
                if end < 0:
                    raise ValueError('Invalid dotenv quoting')
                value = value[1:end]
            else:
                value = re.split(r'\s+#', value, maxsplit=1)[0].strip()
                if value.startswith('#'):
                    value = ''
            result[key] = value
        return result
    # Do not expand values from the shell; report only this file's configuration.
    return dict(dotenv_values(path, interpolate=False))


async def probe(provider):
    if provider == 'anthropic':
        from anthropic import AsyncAnthropic
        async with AsyncAnthropic(api_key=os.environ['ANTHROPIC_API_KEY'],
                                  timeout=TIMEOUT, max_retries=0) as client:
            await client.messages.create(
                model=os.getenv('REFLECTOR_MODEL') or 'claude-opus-5-5',
                max_tokens=5, messages=[{'role': 'user', 'content': TEXT}],
            )
        return 'ok', '-'
    sys.path.insert(0, str(ROOT))
    from safety.judges import DsFlashJudge, JevJudge, GeminiDecisionJudge, StartLuxJudge
    cls = {'ds_flash': DsFlashJudge, 'jev': JevJudge,
           'gemini_decision': GeminiDecisionJudge, 'startlux': StartLuxJudge}[provider]
    judge = cls({'judge_timeout_s': TIMEOUT, 'judge_timeout_overrides': {}})
    predict = judge._predict
    error_type = '-'

    async def capture(text):
        nonlocal error_type
        try:
            return await predict(text)
        except Exception as exc:
            error_type = type(exc).__name__
            raise

    # classify deliberately hides exceptions; observe only their class names.
    judge._predict = capture
    result = await judge.classify(TEXT)
    if result.status == 'timeout':
        error_type = 'TimeoutError'
    elif result.status == 'error' and error_type == '-':
        error_type = 'ResponseValidationError'
    return result.status, error_type


def worker(provider):
    # Suppress SDK logs, stdout and stderr, including native writes. Only the
    # structured status below is returned; no response or exception text escapes.
    logging.disable(logging.CRITICAL)
    output = os.dup(1)
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        try:
            status, error = asyncio.run(probe(provider))
        except ImportError:
            status, error = 'sdk_missing', 'ImportError'
        except Exception as exc:
            status, error = 'error', type(exc).__name__
        print(json.dumps([status, error]), file=os.fdopen(output, 'w'), flush=True)


def main():
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            expected = read_env(ROOT / '.env.example')
            values = read_env(ROOT / '.env')
    except Exception as exc:
        print(f'配置读取失败：{type(exc).__name__}')
        return 1
    if not (ROOT / '.env').exists():
        print('.env 不存在；所有项按空处理，不发请求。')
    for key in expected:
        print(f'{key}: {"已填" if (values.get(key) or "").strip() else "空"}')
    env = os.environ.copy()
    for key in {*expected, 'GOOGLE_API_KEY', 'ANTHROPIC_BASE_URL'}:
        env.pop(key, None)
    env.update({key: values.get(key) or '' for key in expected})
    print('\nprovider | status | 延迟 ms | 错误类型')
    failed = False
    for provider, required in PROVIDERS.items():
        if not all((values.get(key) or '').strip() for key in required):
            print(f'{provider} | skipped | 0 | MissingConfiguration')
            continue
        start = perf_counter()
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), '--worker', provider],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=TIMEOUT,
            )
            status, error = json.loads(result.stdout) if result.returncode == 0 else ('error', 'WorkerError')
            if status not in {'ok', 'error', 'timeout', 'sdk_missing'} or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*|-', error):
                status, error = 'error', 'WorkerProtocolError'
        except subprocess.TimeoutExpired:
            status, error = 'timeout', 'TimeoutError'
        except Exception as exc:
            status, error = 'error', type(exc).__name__
        elapsed = (perf_counter() - start) * 1000
        print(f'{provider} | {status} | {elapsed:.0f} | {error}')
        if status == 'sdk_missing':
            print('  SDK 未安装：Jev/Gemini 见 requirements-optional.txt；Anthropic 需安装 anthropic。')
        failed |= status != 'ok'
    return int(failed)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker' and sys.argv[2] in PROVIDERS:
        worker(sys.argv[2])
    else:
        raise SystemExit(main())
