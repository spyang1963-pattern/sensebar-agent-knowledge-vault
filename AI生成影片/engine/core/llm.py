"""engine.core.llm - generic Gemini text helper (pack-agnostic).

Copied out of the brand-specific script engine so any Pack / ad-hoc flow
can call an LLM without importing project code.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

MODEL = "gemini-3.8-flash"


def load_key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    p = Path.home() / ".gemini_api_key"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    sys.exit("[ERR] 找不到 Gemini API Key（~/.gemini_api_key 或 GEMINI_API_KEY）")


def call_gemini(prompt, model=MODEL, temperature=0.9, retries=2):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=load_key())
    last = None
    for i in range(retries + 1):
        try:
            r = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            return (r.text or "").strip()
        except Exception as e:      # transient 503 etc.
            last = e
            if i < retries:
                time.sleep(3 * (i + 1))
    raise last


def parse_json(text):
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    return json.loads(t[i:j + 1])


if __name__ == "__main__":
    print("key found:", bool(load_key()))
    print(parse_json('```json\n{"a": 1}\n```'))
