"""Infer restriction only from disclosed TIB evidence and explicit prescription text.

This is an engine adapter for the existing domain vetoes, not a new clinical rule.
Unknown/ambiguous schedules stay unknown; visitor hidden fields are never consulted.
"""
import re
import unicodedata

_NUMBER = r'(?:\d+(?:\.\d+)?|[零一二两三四五六七八九十]+)'
_CLOCK = rf'(?:[01]?\d|2[0-3]):[0-5]\d|{_NUMBER}点(?:半|{_NUMBER}分?)?'
_BED = r'(?:上床|卧床|躺下)'
_RISE = r'(?:起床|起来)'
_DURATION = re.compile(rf'(?:卧床|在床上|在床)(?:时间)?(?:近|快|约|大约|差不多|将近)?({_NUMBER})(?:个)?小时(半)?')
_RESTRICTION = re.compile(
    r'(?:缩短|减少|压缩|收紧)(?:夜间|每晚)?(?:的)?(?:卧床|在床|躺床)(?:时间|时长)?'
    r'|(?:卧床|在床|躺床)(?:时间|时长)?(?:缩短|减少|压缩|收紧|压到|缩到)'
    r'|把[^，。；！？!?;\n]{0,20}(?:卧床|在床)[^，。；！？!?;\n]{0,8}(?:缩|压|减|收)(?:到|至|短|少|紧)'
)
_NEGATION = re.compile(r'(?:不|不要|不能|无需|不必|避免|禁止|不宜|先不|暂不)(?:再|要|建议|贸然)?$|(?:再决定|考虑|评估|确认)(?:是否|要不要)$')


def _number(text):
    if re.fullmatch(r'\d+(?:\.\d+)?', text):
        return float(text)
    digits = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4,
              '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
    if '十' in text:
        a, b = text.split('十', 1)
        return (digits.get(a, 1) * 10) + digits.get(b, 0)
    return digits.get(text)


def _clock(text, *, bedtime=False, prefix=''):
    if ':' in text:
        h, m = map(int, text.split(':'))
    else:
        h, rest = text.split('点', 1)
        h = _number(h)
        m = 30 if rest == '半' else _number(rest.removesuffix('分')) if rest else 0
        if h is None or m is None:
            return None
        if h < 12 and re.search(r'晚上|晚间|下午|傍晚', prefix):
            h += 12
        elif bedtime and h < 12 and not re.search(r'凌晨|早上|上午|中午', prefix):
            return None  # e.g. 九点: morning shift or evening is ambiguous
    return int(h * 60 + m) if 0 <= h < 24 and 0 <= m < 60 else None


def time_in_bed(bedtime, risetime):
    return (_clock(risetime) - _clock(bedtime)) % 1440


def _schedule_time(text, label, *, bedtime=False):
    # Both "22:40上床" and "上床约22:40" occur in real session memory.
    for pattern in (rf'(?P<clock>{_CLOCK})(?:左右|就|再)?{label}',
                    rf'{label}(?:时间)?(?:是|为|在|约|大概|差不多|仍|固定在)*?(?P<clock>{_CLOCK})'):
        match = re.search(pattern, text)
        if match:
            return _clock(match['clock'], bedtime=bedtime, prefix=text[max(0, match.start()-4):match.start()])
    return None


def _baseline_text(text):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    bed = _schedule_time(text, _BED, bedtime=True)
    rise = _schedule_time(text, _RISE)
    if bed is not None and rise is not None and (rise - bed) % 1440:
        return (rise - bed) % 1440
    match = _DURATION.search(text)
    if match:
        minutes = _number(match[1]) * 60 + (30 if match[2] else 0)
        if 0 < minutes < 1440:
            return int(minutes)
    return None


def disclosed_tib(entries, memories):
    """Latest disclosed schedule first, then factual memory (never open questions)."""
    bed, rise, sources = None, None, []
    for entry in reversed(entries):
        if entry['speaker'] == 'visitor':
            text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', entry['text']))
            source = {'source': 'visitor', 'round': entry['round'], 'turn': entry['turn']}
            next_bed = _schedule_time(text, _BED, bedtime=True)
            next_rise = _schedule_time(text, _RISE)
            if bed is None and next_bed is not None:
                bed = next_bed
                sources.append(source)
            if rise is None and next_rise is not None:
                rise = next_rise
                if source not in sources:
                    sources.append(source)
            if bed is not None and rise is not None and (rise - bed) % 1440:
                return (rise - bed) % 1440, {'source': 'visitor', 'entries': sources}
            minutes = _baseline_text(text)
            if minutes is not None:
                return minutes, source
    for number in sorted(memories, reverse=True):
        memory = memories[number]
        for text in ['。'.join(memory.get('facts', [])), memory.get('summary', '')]:
            minutes = _baseline_text(text)
            if minutes is not None:
                return minutes, {'source': 'memory', 'round': number}
    return None, None


def explicit_restriction(text):
    text = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    return any(not _NEGATION.search(text[max(0, match.start()-12):match.start()])
               for match in _RESTRICTION.finditer(text))


def annotate_restriction(plan, extras, entries, memories):
    """Mutate only the component list; return local trace evidence for each candidate."""
    baseline, evidence = disclosed_tib(entries, memories)
    planned = time_in_bed(plan['bedtime'], plan['risetime'])
    shortened = baseline is not None and baseline - planned >= 30
    texts = [extras['closing_message'], plan['referral_advice'] or '']
    texts += [c['title'] + '。' + c['body'] for c in plan['cards']]
    explicit = any(explicit_restriction(text) for text in texts)
    warnings = []
    if baseline is None:
        warnings.append('tib_baseline_unknown')
    if explicit and ('sleep_restriction' not in plan['components'] or not shortened
                     or plan['tib_minutes'] != planned):
        warnings.append('sleep_restriction_inconsistent')
    if shortened or explicit:
        if 'sleep_restriction' not in plan['components']:
            plan['components'].append('sleep_restriction')
    return dict(baseline_minutes=baseline, baseline_evidence=evidence, planned_minutes=planned,
                inferred_from_schedule=shortened, explicit_restriction=explicit, warnings=warnings)
