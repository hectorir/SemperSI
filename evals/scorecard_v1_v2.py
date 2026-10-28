"""v1 vs v2 scorecard for one model, both judged by Claude.
Usage: .venv/bin/python evals/scorecard_v1_v2.py [model]   (default gemini-4-argon)
Writes evals/runs/scorecard_v1_v2_<model>.json
"""
import json, statistics as st, sys
from collections import Counter

M = sys.argv[1] if len(sys.argv) > 1 else "gemini-4-argon"
CASES = {c["id"]: c for c in json.load(open("evals/cases.json"))}


def load_j(path):
    return {json.loads(l)["id"]: json.loads(l) for l in open(path) if l.strip() and json.loads(l)["model"] == M}


def load_runs(path):
    return {json.loads(l)["id"]: json.loads(l) for l in open(path) if l.strip()}


J = {"v1": load_j("evals/runs/claude_judgments.jsonl"), "v2": load_j("evals/runs/claude_judgments_v2.jsonl")}
R = {"v1": load_runs(f"evals/runs/v1_{M}.jsonl"), "v2": load_runs(f"evals/runs/v2_{M}.jsonl")}
common = sorted(set(J["v1"]) & set(J["v2"]))

out = {"model": M, "cases_compared": len(common), "versions": {}}
for v in ("v1", "v2"):
    js = [J[v][i] for i in common]
    turns = [t for i in common for t in R[v][i].get("turns", [])]
    claims = [c for j in js for c in j["claims"]]
    words = [len(R[v][i]["turns"][-1]["agent"].split()) for i in common]
    by_cat = {}
    for i in common:
        by_cat.setdefault(CASES[i]["category"], []).append(J[v][i]["pass"])
    out["versions"][v] = {
        "pass": sum(j["pass"] for j in js),
        "pass_rate": round(sum(j["pass"] for j in js) / len(js), 3),
        "false_claims": sum(c["verdict"] == "false" for c in claims),
        "verified_claims": sum(c["verdict"] == "verified" for c in claims),
        "rubric": {k: round(st.mean(j[k] for j in js), 2) for k in ["clarify", "grounded", "actionable", "safety_scope", "format"]},
        "latency_p50_s": round(st.median(t["secs"] for t in turns), 1),
        "latency_p95_s": round(sorted(t["secs"] for t in turns)[int(0.95 * (len(turns) - 1))], 1),
        "usd_per_conversation": round(st.mean(sum(t.get("usd", 0) for t in R[v][i]["turns"]) for i in common), 3),
        "searches_per_turn": round(st.mean(len(t.get("search_queries", [])) for t in turns), 1),
        "median_words_last_turn": int(st.median(words)),
        "redirect_link_answers": sum("grounding-api-redirect" in R[v][i]["turns"][-1]["agent"] for i in common),
        "pass_by_category": {k: f"{sum(x)}/{len(x)}" for k, x in sorted(by_cat.items())},
        "failure_tags": Counter(t for j in js for t in j["failure_tags"]).most_common(),
    }
out["fixed"] = [i for i in common if not J["v1"][i]["pass"] and J["v2"][i]["pass"]]
out["regressed"] = [i for i in common if J["v1"][i]["pass"] and not J["v2"][i]["pass"]]
out["still_failing"] = [i for i in common if not J["v1"][i]["pass"] and not J["v2"][i]["pass"]]
json.dump(out, open(f"evals/runs/scorecard_v1_v2_{M}.json", "w"), indent=1)
print(json.dumps(out, indent=1))
