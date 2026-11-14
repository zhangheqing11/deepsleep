"""Generation curve on a held-out cohort: level, first difference, second difference.

    python analysis/evo_curve.py var/lab "v1=X-v1-B,X-v1-Bc-r1,X-v1-Bc-r2" "v2=X-E11v2-B-r1,..." "v3=..." "v4=..."

Each argument after the lab directory is ``label=run,run,...`` (replicates of one playbook version on the same
visitors), in generation order. Per visitor the responder / referral-correct outcome is averaged over the
replicates; differences between consecutive versions are paired by visitor and bootstrapped over visitors.
The second difference is (v[i+1] - v[i]) - (v[i] - v[i-1]): negative means the gain per generation is shrinking.
"""
import json
import random
import sys
from pathlib import Path

lab = Path(sys.argv[1])
groups = [(arg.split("=", 1)[0], arg.split("=", 1)[1].split(",")) for arg in sys.argv[2:]]


def load(run):
    report = json.loads((lab / run / "run_report.json").read_text(encoding="utf-8"))
    return report["metrics"], {row["visitor_id"]: row for row in report["per_visitor"]}


runs = {run: load(run) for _, names in groups for run in names}
ids = sorted(set.intersection(*(set(rows) for _, rows in runs.values())))
OUTCOMES = {"responder": lambda row: bool(row["responder"]),
            "referral_correct": lambda row: row["referral_pred"] == row["referral_true"]}


def pooled(names, outcome):
    return {v: sum(outcome(runs[r][1][v]) for r in names) / len(names) for v in ids}


def interval(values, seed=20261115):
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(10000))
    return sum(values) / len(values), boots[250], boots[9750]


print(f"visitors {len(ids)}; replicates per version: " + ", ".join(f"{label}={len(names)}" for label, names in groups))
for name, outcome in OUTCOMES.items():
    level = [pooled(names, outcome) for _, names in groups]
    print(f"\n== {name}")
    for (label, names), values in zip(groups, level):
        singles = [runs[r][0]["isi_response_rate"] for r in names] if name == "responder" else []
        mean, low, high = interval(list(values.values()))
        extra = "  runs [" + " ".join(f"{x * 100:.1f}" for x in singles) + "]" if singles else ""
        print(f"  level {label}: {mean * 100:5.1f}%  CI95 [{low * 100:.1f}, {high * 100:.1f}]{extra}")
    first = []
    for i in range(1, len(groups)):
        diff = [level[i][v] - level[i - 1][v] for v in ids]
        first.append(diff)
        mean, low, high = interval(diff)
        print(f"  first difference {groups[i - 1][0]}->{groups[i][0]}: {mean * 100:+5.1f}pp  CI95 [{low * 100:+.1f}, {high * 100:+.1f}]")
    for i in range(1, len(first)):
        diff = [b - a for a, b in zip(first[i - 1], first[i])]
        mean, low, high = interval(diff)
        print(f"  second difference at {groups[i][0]}: {mean * 100:+5.1f}pp  CI95 [{low * 100:+.1f}, {high * 100:+.1f}]")
