"""Append Claude-as-judge verdicts. stdin: JSON list of verdicts.
Each: {"id","model","clarify","grounded","actionable","safety_scope","format","claims":[...],"failure_tags":[...],"pass":bool,"rationale"}"""
import json, sys
from pathlib import Path
import os
out = Path(os.getenv("JUDGMENTS", "evals/runs/claude_judgments.jsonl"))
existing = {}
if out.exists():
    for l in out.read_text().splitlines():
        if l.strip():
            r = json.loads(l); existing[(r["id"], r["model"])] = r
for v in json.load(sys.stdin):
    existing[(v["id"], v["model"])] = v
out.write_text("\n".join(json.dumps(r) for r in existing.values()) + "\n")
print(f"{len(existing)} verdicts recorded")
