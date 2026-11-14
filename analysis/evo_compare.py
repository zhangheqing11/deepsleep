"""Compare lab runs: python cmp_runs.py <lab_dir> <visitors_dir> runA,runB,... [--vs runC,runD]
Prints per-run metrics, per-visitor stability across the first group, and (with --vs) a paired comparison
of pooled responder outcomes between the two groups (same visitor ids)."""
import json, sys, random
from pathlib import Path
from collections import Counter

lab, vdir = Path(sys.argv[1]), Path(sys.argv[2])
g1 = sys.argv[3].split(",")
g2 = sys.argv[sys.argv.index("--vs") + 1].split(",") if "--vs" in sys.argv else []


def load(run):
    r = json.loads((lab / run / "run_report.json").read_text(encoding="utf-8"))
    return r["metrics"], {row["visitor_id"]: row for row in r["per_visitor"]}


def card(vid):
    for p in vdir.rglob(f"{vid}.json"):
        if "interim" not in p.parts:
            return json.loads(p.read_text(encoding="utf-8"))


KEYS = ("isi_response_rate", "path_acc_r1", "path_acc_r2", "referral_recall", "referral_precision", "screening_coverage")
runs = {}
for run in g1 + g2:
    m, rows = load(run)
    runs[run] = rows
    print(f"{run:28s} n={len(rows)} " + " ".join(f"{k.split('_')[0][:4]}{k[-3:]}={m[k]:.3f}" if m[k] is not None else f"{k}=NA" for k in KEYS))

ids = sorted(set.intersection(*(set(runs[r]) for r in g1 + g2)))
resp = lambda run, vid: bool(runs[run][vid]["responder"])
refok = lambda run, vid: runs[run][vid]["referral_pred"] == runs[run][vid]["referral_true"]

# ceiling: visitors that cannot respond under the frozen model whatever the playbook
unreach = []
for vid in ids:
    c = card(vid)
    if c and (c["persona"]["adherence_tendency"] < 0.469 or c["crisis"]["level"] == "active"):
        unreach.append(vid)
print(f"\ncommon visitors {len(ids)}; structurally unreachable (tendency<0.469 or active crisis): {len(unreach)} -> ceiling {(len(ids)-len(unreach))/len(ids):.3f}")

if len(g1) > 1:
    c = Counter(sum(resp(r, v) for r in g1) for v in ids)
    print(f"stability over {len(g1)} runs of group1 (responder count -> visitors):", dict(sorted(c.items())))
    always_fail = [v for v in ids if not any(resp(r, v) for r in g1)]
    learnable = [v for v in always_fail if v not in unreach]
    print("always-fail:", len(always_fail), "of which reachable:", len(learnable))
    for v in learnable:
        row = runs[g1[0]][v]
        print(f"   {v}: true {row['main_path']}/{row['referral_true']}  preds r2 {[runs[r][v]['path_pred_r2'] for r in g1]} ref {[runs[r][v]['referral_pred'] for r in g1]}")

if g2:
    def pooled(group, f):
        return {v: sum(f(r, v) for r in group) / len(group) for v in ids}
    for name, f in (("responder", resp), ("referral_correct", refok)):
        a, b = pooled(g1, f), pooled(g2, f)
        diff = [b[v] - a[v] for v in ids]
        mean = sum(diff) / len(diff)
        rng = random.Random(20261114)
        boots = sorted(sum(rng.choice(diff) for _ in diff) / len(diff) for _ in range(10000))
        up, down = sum(d > 0 for d in diff), sum(d < 0 for d in diff)
        print(f"\n{name}: group1 {sum(a.values())/len(ids):.3f} -> group2 {sum(b.values())/len(ids):.3f}  paired diff {mean:+.3f} "
              f"CI95 [{boots[250]:+.3f}, {boots[9750]:+.3f}]  visitors up {up} / down {down}")
    reach = [v for v in ids if v not in unreach]
    a, b = pooled(g1, resp), pooled(g2, resp)
    print(f"responder among reachable ({len(reach)}): {sum(a[v] for v in reach)/len(reach):.3f} -> {sum(b[v] for v in reach)/len(reach):.3f}")
    by = Counter()
    for v in ids:
        t = runs[g1[0]][v]["referral_true"]
        by[(t, "g1")] += sum(refok(r, v) for r in g1) / len(g1)
        by[(t, "g2")] += sum(refok(r, v) for r in g2) / len(g2)
        by[(t, "n")] += 1
    print("referral correct by true label (g1 -> g2):", {t: f"{by[(t,'g1')]/by[(t,'n')]:.2f}->{by[(t,'g2')]/by[(t,'n')]:.2f} (n={by[(t,'n')]})" for t in ("R0", "R1", "R2", "R3")})
