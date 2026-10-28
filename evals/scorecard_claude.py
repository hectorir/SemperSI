"""Scorecard from Claude-as-judge verdicts + agreement with the Gemini judge.
Usage: .venv/bin/python evals/scorecard_claude.py
Writes evals/runs/scorecard_claude.json
"""
import json, statistics as st
from collections import Counter, defaultdict

MODELS = ["gemini-4-argon", "gemini-3.8-flash"]
claude = {}
for l in open("evals/runs/claude_judgments.jsonl"):
    r = json.loads(l); claude[(r["id"], r["model"])] = r
runs = {m: {json.loads(l)["id"]: json.loads(l) for l in open(f"evals/runs/v1_{m}.jsonl")} for m in MODELS}
gem = {m: {json.loads(l)["id"]: json.loads(l) for l in open(f"evals/runs/v1_{m}.judged.jsonl")} for m in MODELS}

out = {}
for m in MODELS:
    v = [r for (i, mm), r in claude.items() if mm == m]
    lat = [t["secs"] for r in runs[m].values() for t in r["turns"]]
    usd = [sum(t.get("usd", 0) for t in r["turns"]) for r in runs[m].values()]
    claims = [c for r in v for c in r["claims"]]
    cv = Counter(c["verdict"] for c in claims)
    bycat = defaultdict(list)
    for r in v:
        bycat[runs[m][r["id"]]["category"]].append(r["pass"])
    mean = lambda k: round(st.mean(r[k] for r in v), 2)
    out[m] = {
        "cases": len(v),
        "pass": sum(r["pass"] for r in v),
        "pass_rate": round(sum(r["pass"] for r in v) / len(v), 3),
        "rubric": {k: mean(k) for k in ["clarify", "grounded", "actionable", "safety_scope", "format"]},
        "claims_checked": len(claims),
        "claims_verified": cv["verified"], "claims_unverified": cv["unverified"], "claims_false": cv["false"],
        "latency_p50_s": round(st.median(lat), 1),
        "latency_p95_s": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1),
        "usd_per_conversation": round(st.mean(usd), 3),
        "pass_by_category": {k: f"{sum(x)}/{len(x)}" for k, x in sorted(bycat.items())},
        "failure_tags": Counter(t for r in v for t in r["failure_tags"]).most_common(),
        "failed_cases": sorted(r["id"] for r in v if not r["pass"]),
    }

# Agreement with the Gemini 3.1 Pro judge
pairs = [(bool(gem[m][i]["judge"].get("pass")), claude[(i, m)]["pass"]) for m in MODELS for i in runs[m]]
n = len(pairs)
agree = sum(a == b for a, b in pairs)
pg = sum(a for a, _ in pairs) / n; pc = sum(b for _, b in pairs) / n
pe = pg * pc + (1 - pg) * (1 - pc)
kappa = (agree / n - pe) / (1 - pe)
disagreements = [{"model": m, "id": i, "gemini_pass": bool(gem[m][i]["judge"].get("pass")), "claude_pass": claude[(i, m)]["pass"]}
                 for m in MODELS for i in runs[m] if bool(gem[m][i]["judge"].get("pass")) != claude[(i, m)]["pass"]]
out["judge_agreement"] = {"n": n, "agree": agree, "agreement_rate": round(agree / n, 3), "cohens_kappa": round(kappa, 2),
                          "gemini_stricter": sum(1 for d in disagreements if not d["gemini_pass"]),
                          "claude_stricter": sum(1 for d in disagreements if not d["claude_pass"]),
                          "disagreements": disagreements}
json.dump(out, open("evals/runs/scorecard_claude.json", "w"), indent=1)
print(json.dumps(out, indent=1))
