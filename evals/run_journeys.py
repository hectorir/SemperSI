"""Run conversations through the agent, track cost, save transcripts as JSONL.

Usage:
  MCCS_MODEL=gemini-4-argon .venv/bin/python evals/run_journeys.py evals/cases.json evals/runs/argon.jsonl
Env:
  EVAL_CONCURRENCY  parallel conversations (default 4)
  EVAL_CAP_USD      hard stop for this run's estimated spend (default 12)
Each case: {"id": str, "category": str, "turns": [str, ...], "expect": str}
"""
import asyncio, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / "mccs_agent" / ".env")

from google.adk.runners import InMemoryRunner
from google.genai import types
from mccs_agent.agent import root_agent, MODEL, PROMPT_PATH

# USD per token / per search query, from the Cloud Billing catalog (2026-10-26, global, online).
PRICES = {
    "gemini-4-argon":   {"in": 4e-6, "out": 20e-6},
    "gemini-3.8-flash": {"in": 2e-6, "out": 8e-6},
}
SEARCH_USD = 0.014  # Web Grounding for Enterprise, per query
CAP = float(os.getenv("EVAL_CAP_USD", "12"))
spent = 0.0


def cost(tin, tout, queries):
    p = PRICES.get(MODEL, {"in": 4e-6, "out": 20e-6})  # unknown model: assume the pricier rate
    return tin * p["in"] + tout * p["out"] + queries * SEARCH_USD


async def run_case(runner, case):
    global spent
    session = await runner.session_service.create_session(app_name=runner.app_name, user_id="eval")
    turns = []
    for text in case["turns"]:
        if spent >= CAP:
            raise RuntimeError(f"spend cap ${CAP} reached")
        t0 = time.time()
        reply, uris, queries, tin, tout = "", [], [], 0, 0
        async for ev in runner.run_async(user_id="eval", session_id=session.id,
                                         new_message=types.Content(role="user", parts=[types.Part(text=text)])):
            if ev.content and ev.content.parts:
                reply += "".join(p.text or "" for p in ev.content.parts if not getattr(p, "thought", False))
            gm = getattr(ev, "grounding_metadata", None)
            if gm:
                uris += [c.web.title or c.web.uri for c in (gm.grounding_chunks or []) if c.web]
                queries += list(gm.web_search_queries or [])
            um = getattr(ev, "usage_metadata", None)
            if um:
                tin += um.prompt_token_count or 0
                tout += (um.candidates_token_count or 0) + (um.thoughts_token_count or 0)
        c = cost(tin, tout, len(queries))
        spent += c
        turns.append({"user": text, "agent": reply, "grounding": uris, "search_queries": queries,
                      "tokens_in": tin, "tokens_out": tout, "usd": round(c, 4), "secs": round(time.time() - t0, 1)})
    return {"id": case["id"], "category": case.get("category", ""), "expect": case.get("expect", ""),
            "model": MODEL, "prompt": PROMPT_PATH.name, "turns": turns}


async def main(cases_path, out_path):
    cases = json.loads(Path(cases_path).read_text())
    runner = InMemoryRunner(agent=root_agent, app_name="mccs")
    sem = asyncio.Semaphore(int(os.getenv("EVAL_CONCURRENCY", "2")))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    f = open(out_path, "w")

    async def one(case):
        async with sem:
            for attempt in range(6):
                try:
                    res = await asyncio.wait_for(run_case(runner, case), timeout=float(os.getenv('EVAL_CASE_TIMEOUT', '360')))
                    break
                except Exception as e:
                    res = {"id": case["id"], "category": case.get("category", ""), "model": MODEL, "error": repr(e)}
                    transient = ("RESOURCE_EXHAUSTED", "429", "ReadError", "RemoteProtocolError",
                                 "ConnectError", "ConnectionError", "Server disconnected", "TimeoutError")
                    if not any(t in repr(e) for t in transient) or "spend cap" in repr(e):
                        break
                    await asyncio.sleep(min(15 * 2 ** attempt, 180))
            f.write(json.dumps(res) + "\n"); f.flush()
            print(f'{case["id"]:32} {"ERR " + res["error"][:80] if "error" in res else "ok"}  run total ${spent:.2f}', flush=True)

    await asyncio.gather(*(one(c) for c in cases))
    f.close()
    print(f"DONE {MODEL}: estimated ${spent:.2f}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
