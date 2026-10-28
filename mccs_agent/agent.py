"""MCCS Discovery Assistant: digital twin of the GenAI.mil Agent Builder agent.

The prompt file and model are chosen with environment variables, so evals can
run the same agent against different prompt versions and models:
  MCCS_PROMPT  path to prompt file (default: prompts/v1_baseline.md)
  MCCS_MODEL   Vertex model id (default: gemini-4-argon)
  MCCS_SEARCH  "enterprise" (Enterprise Web Search, matches original) or "google"
  MCCS_RESOLVE_LINKS  "1" (default) rewrites grounding-redirect links to real URLs

Prompt placeholders:
  {today}  replaced with the current date on every model call
"""
import asyncio
import datetime as dt
import os
import re
from functools import lru_cache
from pathlib import Path

import requests
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import enterprise_web_search, google_search

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = Path(os.getenv("MCCS_PROMPT", ROOT / "prompts" / "v1_baseline.md"))
MODEL = os.getenv("MCCS_MODEL", "gemini-4-argon")
SEARCH = enterprise_web_search if os.getenv("MCCS_SEARCH", "enterprise") == "enterprise" else google_search
RESOLVE_LINKS = os.getenv("MCCS_RESOLVE_LINKS", "1") == "1"
PROMPT_TEXT = PROMPT_PATH.read_text()

REDIRECT_RE = re.compile(r"https://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[A-Za-z0-9_\-=]+")


def instruction(_ctx) -> str:
    """Instruction provider: injects today's date. (A callable also bypasses ADK's {state} templating.)"""
    return PROMPT_TEXT.replace("{today}", dt.date.today().strftime("%A, %B %-d, %Y"))


@lru_cache(maxsize=2048)
def _resolve(url: str) -> str:
    """Grounding redirects answer with a 302 to the real page; read Location without fetching the page."""
    try:
        r = requests.get(url, allow_redirects=False, timeout=8)
        return r.headers.get("Location") or url
    except requests.RequestException:
        return url


async def resolve_source_links(callback_context: CallbackContext, llm_response: LlmResponse):
    """C1: replace opaque grounding-redirect URLs in the answer with the real destination URLs."""
    if not RESOLVE_LINKS or not llm_response.content or not llm_response.content.parts:
        return None
    changed = False
    for part in llm_response.content.parts:
        if part.text and "grounding-api-redirect" in part.text:
            urls = set(REDIRECT_RE.findall(part.text))
            resolved = await asyncio.gather(*(asyncio.to_thread(_resolve, u) for u in urls))
            for u, real in zip(urls, resolved):
                if real != u:
                    part.text = part.text.replace(u, real)
                    changed = True
    return llm_response if changed else None


root_agent = Agent(
    name="mccs_discovery_assistant",
    model=MODEL,
    description=(
        "Helps Marines and families discover installation-specific MCCS "
        "programs, services, facilities, and activities."
    ),
    instruction=instruction,
    tools=[SEARCH],
    after_model_callback=resolve_source_links,
)
