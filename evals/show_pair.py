"""Print both models' transcripts for given case ids (for Claude/human judging).
Env RUN=v1|v2 (default v1). Flags Source links outside the approved domain list."""
import json, os, re, sys
RUN = os.getenv("RUN", "v1")
APPROVED = ("usmc-mccs.org", ".mil", "militaryonesource.mil", "militarychildcare.com", "tricare.mil",
            "veteranscrisisline.net", "988lifeline.org", "safehelpline.org", "fvap.gov", "dmdc.osd.mil")
URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
ids = sys.argv[1:]
data = {m: {json.loads(l)["id"]: json.loads(l) for l in open(f"evals/runs/{RUN}_{m}.jsonl")} for m in os.getenv("MODELS", "gemini-4-argon,gemini-3.8-flash").split(",")}
for i in ids:
    print(f"\n{'='*20} {i} :: EXPECT: {next(iter(data.values()))[i].get('expect')}")
    for m, d in data.items():
        r = d[i]; print(f"\n--- {m} ({RUN}) ---")
        if "error" in r: print("ERROR", r["error"]); continue
        for t in r["turns"]:
            a = re.sub(r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/\S+?\)", "<REDIRECT>)", t["agent"])
            a = re.sub(r"\n\s*\n", "\n", a)
            urls = set(u.rstrip(".,") for u in URL_RE.findall(t["agent"]))
            off = [u for u in urls if not any(d in u.split("/")[2] for d in APPROVED)]
            home = [u for u in urls if re.fullmatch(r"https?://[^/]+/?", u)]
            print(f"U: {t['user']}\nA [{t['secs']}s, {len(t['search_queries'])}q, {len(a.split())}w"
                  f"{', OFF-LIST: ' + str(off) if off else ''}{', HOMEPAGE-LINKS: ' + str(len(home)) if home else ''}]: {a}")
