"""Aggregate judged runs into a scorecard. Usage: python evals/scorecard.py evals/runs/*.judged.jsonl"""
import json, statistics as st, sys
from collections import Counter, defaultdict

rows = {}
for path in sys.argv[1:]:
    recs = [json.loads(l) for l in open(path) if l.strip()]
    model = next((r.get("model") for r in recs if r.get("model")), path)
    ok = [r for r in recs if "error" not in r and r["judge"].get("pass") is not None]
    j = lambda k: round(st.mean(r["judge"].get(k, 0) for r in ok), 2) if ok else None
    lat = [s for r in ok for s in r["checks"]["latency_s"]]
    claims = [c for r in ok for c in r["judge"].get("claims", [])]
    cv = Counter(c.get("verdict") for c in claims)
    bycat = defaultdict(list)
    for r in ok:
        bycat[r["category"]].append(bool(r["judge"]["pass"]))
    rows[model] = {
        "cases": len(recs), "errors": sum("error" in r for r in recs),
        "pass_rate": round(sum(bool(r["judge"]["pass"]) for r in ok) / max(len(ok), 1), 3),
        "clarify": j("clarify"), "grounded": j("grounded"), "actionable": j("actionable"),
        "safety_scope": j("safety_scope"), "format": j("format"),
        "claims_verified": cv["verified"], "claims_unverified": cv["unverified"], "claims_false": cv["false"],
        "latency_p50": round(st.median(lat), 1) if lat else None,
        "latency_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1) if lat else None,
        "usd_total": round(sum(r["checks"]["usd"] for r in ok), 2),
        "usd_per_conv": round(st.mean(r["checks"]["usd"] for r in ok), 3) if ok else None,
        "redirect_links_cases": sum(r["checks"].get("redirect_links_shown", 0) > 0 for r in ok),
        "broken_link_cases": sum(bool(r["checks"].get("broken_links")) for r in ok),
        "inline_citation_cases": sum(r["checks"]["inline_citation"] for r in ok),
        "avg_words": round(st.mean(r["checks"]["words_last_turn"] for r in ok)) if ok else None,
        "pass_by_category": {k: f"{sum(v)}/{len(v)}" for k, v in sorted(bycat.items())},
        "top_failure_tags": Counter(t for r in ok for t in r["judge"].get("failure_tags", [])).most_common(8),
        "failed_cases": [r["id"] for r in ok if not r["judge"]["pass"]],
    }
print(json.dumps(rows, indent=1))
json.dump(rows, open("evals/runs/scorecard.json", "w"), indent=1)
