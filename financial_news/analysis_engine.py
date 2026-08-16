#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analysis engine - uses Gemini (free tier) to summarize, classify, and
predict market impact of collected financial news events.

For each batch of kept events, Gemini produces:
  - category: stock/bond/currency/commodity/geopolitics/mixed
  - severity: 0-3 (0=minor, 3=major)
  - sentiment: positive/negative/neutral
  - related_tickers: affected stocks/indices
  - impact_notes: brief impact explanation
  - outlook: short (1w) / mid (1m) / long (1q) expectation

Usage:
  python analysis_engine.py --batch 20        # analyze next 20 unanalyzed events
  python analysis_engine.py --batch 20 --dry  # show what would be sent
"""
import os
import sys
import re
import json
import time
import argparse
from datetime import datetime, timezone

from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
BATCH_NUM = 8  # events per Gemini call

SYSTEM_PROMPT = """你是一名專業的國際金融分析師。你的任務是分析以下新聞事件，針對台股/美股/全球宏觀投資者提供精簡、可執行的重點。

對每一則事件，輸出嚴格 JSON 格式（不要輸出任何其他文字），格式如下：
{
  "events": [
    {
      "id": <原始ID>,
      "category": "stock" | "bond" | "currency" | "commodity" | "geopolitics" | "macro" | "other",
      "severity": 0-3,
      "sentiment": "positive" | "negative" | "neutral",
      "related_tickers": ["2330", "NVDA", "TSM", "美元指數"],
      "impact_notes": "50字內，說明對股/債/匯/商品市場的影響與連動",
      "outlook": "用一段話給出未來短期(1週)、中短期(1月)、中期(1季)的走勢預期或預測",
      "watch": "正面看好或負面警示的標的，含理由，或寫無"
    }
  ]
}

注意：
- related_tickers 用台股代號或美股代號，無明確標的可留空
- severity 只給 0-3；0=無影響，3=重大事件（戰爭、央行重大決策、系統性風險）
- outlook 必須簡潔具體，不要空泛
- watch 標明是「看好」或「警示」
"""


def _read_key():
    api_key = os.environ.get("GEMINI_API_KEY") or ""
    if not api_key:
        kf = Path.home() / ".gemini_api_key"
        if kf.exists():
            api_key = kf.read_text("utf-8").strip()
    if not api_key:
        raise Exception("GEMINI_API_KEY not found")
    return api_key


def _client():
    if genai is None:
        raise Exception("google-genai not installed")
    return genai.Client(api_key=_read_key())


def _json_from_text(text):
    """Extract JSON array/object from model output."""
    text = text.strip()
    # strip code fences
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.M)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


def analyze_batch(events, model=MODEL, max_attempts=8):
    """Analyze a batch of events via Gemini. Returns list of dict results."""
    if not events:
        return []
    client = _client()
    payload = "\n".join(
        f"[{ev['id']}] ({ev['published']}) {ev['title']}\n"
        f"   來源: {ev.get('link') or ev.get('source') or ''}\n"
        f"   摘要: {ev['summary'][:300]}"
        for ev in events
    )
    prompt = f"請分析以下 {len(events)} 則新聞事件：\n\n{payload}\n\n{EVENT_PROMPT_SUFFIX}"

    last_err = ""
    for attempt in range(max_attempts):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )
            parsed = _json_from_text(resp.text or "")
            if parsed and "events" in parsed:
                return parsed["events"]
            if isinstance(parsed, list):
                return parsed
            last_err = "json format unexpected"
        except Exception as e:
            es = str(e)
            last_err = es[:200]
            if "tokens per day" in es.lower() or "daily tokens" in es.lower():
                print(f"[analysis] 已達 Gemini 每日額度，停止（{es[:120]}）")
                return None
            is_rpm = ("quota exceeded" in es.lower() or "resource_exhausted" in es.lower()) and "retry in" in es.lower()
            retry_sec = 30
            if is_rpm:
                m = re.search(r"retry in ([0-9.]+)s", es)
                if m:
                    retry_sec = int(float(m.group(1))) + 2
            print(f"[analysis] batch fail ({attempt+1}/{max_attempts}): {es[:120]} wait {retry_sec}s")
            time.sleep(retry_sec)
    print(f"[analysis] batch failed permanently: {last_err}")
    return None


EVENT_PROMPT_SUFFIX = (
    "請完整輸出所有事件的 JSON。若某事件資訊不足以判斷影響，impact_notes 請誠實說明『資訊不足』，"
    "outlook 給中性展望，不要編造。"
)


VERIFIER_MODEL = "openai/gpt-oss-120b"  # second model (free, via Groq) for cross-checking
VERIFY_THRESHOLD = 2                 # only cross-verify events Gemini rated >= this severity

VERIFY_SYSTEM_PROMPT = """你是一名獨立的國際金融分析師。你收到一則新聞事件及另一名分析師(Gemini)的分類結果。
請獨立判斷並輸出嚴格 JSON（不要輸出任何其他文字）：
{
  "severity": 0-3,
  "sentiment": "positive" | "negative" | "neutral",
  "disagree": true | false,
  "reason": "若你與 Gemini 判斷不同，用50字內說明為何不同；相同則填『無分歧』"
}
severity: 0=無影響，3=重大事件（戰爭、央行重大決策、系統性風險）。
不要被 Gemini 的判斷影響，請用你自己的專業判斷。"""


def _strip_think(text):
    """Remove Groq <think> blocks, including unclosed ones."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in text:
        idx = text.rfind("<think>")
        text = text[:idx]
    return text.strip()


def _groq_client():
    import groq
    api_key = os.environ.get("GROQ_API_KEY") or ""
    if not api_key:
        kf = Path.home() / ".groq_api_key"
        if kf.exists():
            api_key = kf.read_text("utf-8").strip()
    if not api_key:
        raise Exception("GROQ_API_KEY not found")
    return groq.Groq(api_key=api_key, timeout=60, max_retries=0)


def _verify_one_groq(ev, max_attempts=3):
    """Cross-check one event with a second model (Groq qwen). Returns (verified_by, verification, note).

    Retries on 429 rate-limit with backoff so a quota blip doesn't permanently
    mark the event unverified.
    """
    try:
        client = _groq_client()
        prompt = (
            f"[事件 {ev['id']}] ({ev.get('published','')}) {ev['title']}\n"
            f"摘要: {ev.get('summary','')[:300]}\n"
            f"Gemini 判定: severity={ev.get('severity')}, sentiment={ev.get('sentiment')}\n\n"
            "請獨立複核此事件的重要性與情緒方向。"
        )
        last_err = ""
        for attempt in range(max_attempts):
            try:
                resp = client.chat.completions.create(
                    model=VERIFIER_MODEL,
                    messages=[{"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                              {"role": "user", "content": prompt}],
                    max_tokens=600,
                    temperature=0.2,
                )
                raw = resp.choices[0].message.content or ""
                raw = _strip_think(raw)
                parsed = _json_from_text(raw)
                if not parsed:
                    return VERIFIER_MODEL, "unverified", f"verifier JSON parse failed: {raw[:100]}"
                vs = parsed.get("severity")
                vse = parsed.get("sentiment")
                reason = parsed.get("reason") or ""
                gs = ev.get("severity")
                gse = ev.get("sentiment")
                severity_agree = isinstance(vs, int) and isinstance(gs, int) and abs(vs - gs) <= 1
                sent_agree = vse == gse
                if severity_agree and sent_agree:
                    return VERIFIER_MODEL, "verified", reason
                return VERIFIER_MODEL, "conflict", reason
            except Exception as e:
                es = str(e)
                last_err = es[:200]
                if "429" in es or "rate limit" in es.lower():
                    # quota exhausted - wait once then give up this round rather
                    # than stalling the pipeline; next cycle will retry.
                    time.sleep(10 + 5 * attempt)
                    if attempt == max_attempts - 1:
                        return VERIFIER_MODEL, "unverified", f"verifier rate-limited: {last_err}"
                    continue
                break
        return VERIFIER_MODEL, "unverified", f"verifier error: {last_err}"
    except Exception as e:
        return VERIFIER_MODEL, "unverified", f"verifier error: {str(e)[:120]}"


def verify_important(events, results):
    """Cross-verify events Gemini rated as important (severity >= threshold).

    Args:
        events: list of event dicts (as passed to analyze_batch).
        results: list of result dicts returned by analyze_batch.

    Returns:
        List of (event_id, verified_by, verification, note) tuples, or [] if disabled.
    """
    if os.environ.get("NO_CROSS_VERIFY"):
        return []
    important = {r["id"]: r for r in results if int(r.get("severity", 0)) >= VERIFY_THRESHOLD}
    if not important:
        return []
    by_id = {ev["id"]: ev for ev in events}
    outcomes = []
    for eid, r in important.items():
        ev = by_id.get(eid)
        if not ev:
            continue
        # give verifier the full event + gemini judgement
        ev_for_verify = dict(ev, severity=r.get("severity"), sentiment=r.get("sentiment"))
        verified_by, verification, note = _verify_one_groq(ev_for_verify)
        outcomes.append((eid, verified_by, verification, note))
        time.sleep(0.5)
    return outcomes


def _confidence_for(verification):
    """Map verification outcome to a confidence score (see QUALITY_ASSURANCE.md)."""
    if verification == "verified":
        return 0.9
    if verification == "conflict":
        return 0.4
    return 0.6


def backfill_verification(limit=20, time_budget=120):
    """Cross-verify historical important events (severity>=2, no verification).

    Runs on a rolling basis to push coverage toward the target. Returns
    (verified_count, quota_hit).
    """
    conn = db.connect()
    try:
        rows = conn.execute(
            """SELECT id, title, summary, published, severity, sentiment
               FROM events
               WHERE severity>=2 AND verification IS NULL
               ORDER BY published DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return 0, False
    events = [dict(r) for r in rows]
    # re-annotate with the gemini judgement already stored (severity/sentiment
    # came from gemini, so pass them through for the verifier prompt)
    results = [{"id": e["id"], "severity": e["severity"], "sentiment": e["sentiment"]} for e in events]
    done = 0
    quota_hit = False
    t0 = time.time()
    for eid, vby, vres, note in verify_important(events, results):
        if time.time() - t0 > time_budget:
            quota_hit = True
            break
        db.update_verification(int(eid), vby, vres, note)
        db.set_confidence(int(eid), _confidence_for(vres))
        done += 1
        if vres == "unverified" and note.startswith("verifier rate-limited"):
            # quota exhausted for this cycle - stop backfilling now
            quota_hit = True
            break
    db.commit()
    return done, quota_hit


def analyze_pending(batch_size=20, batch_num=BATCH_NUM, dry=False, languages=None,
                    time_budget=None):
    """Analyze unanalyzed kept events. Returns (analyzed, quota_hit).

    time_budget: max seconds for one pass (default 300, or $ANALYSIS_TIME_BUDGET).
    """
    if time_budget is None:
        try:
            time_budget = int(os.environ.get("ANALYSIS_TIME_BUDGET", "300"))
        except ValueError:
            time_budget = 300
    languages = languages or [None]
    total_analyzed = 0
    quota_hit = False
    for lang in languages:
        events = db.unanalyzed(language=lang, limit=batch_size)
        if not events:
            continue
        if dry:
            print(f"[dry] would analyze {len(events)} {lang or 'all'} events")
            for ev in events[:batch_num]:
                print(f"  [{ev['id']}] {ev['title'][:70]}")
            continue
        batch_t0 = time.time()
        for i in range(0, len(events), batch_num):
            # hard stop if the whole pass has run too long (quota/retry storm)
            if time.time() - batch_t0 > time_budget:
                print(f"[analysis] 超過本次 {time_budget} 秒預算，停止（等下次排程）")
                quota_hit = True
                break
            chunk = events[i:i + batch_num]
            results = analyze_batch(chunk)
            if results is None:
                quota_hit = True
                break
            # persist gemini analysis
            for r in results:
                eid = r.get("id")
                if eid is None:
                    continue
                db.update_analysis(
                    int(eid),
                    r.get("category", "other"),
                    int(r.get("severity", 0)),
                    r.get("sentiment", "neutral"),
                    ",".join(r.get("related_tickers", [])),
                    r.get("impact_notes", ""),
                )
                total_analyzed += 1
            db.commit()
            # cross-verify important events with a second model
            try:
                for eid, vby, vres, note in verify_important(chunk, results):
                    db.update_verification(int(eid), vby, vres, note)
                    db.set_confidence(int(eid), _confidence_for(vres))
                    print(f"[verify] 事件 {eid}: {vres}（{vby}）")
                db.commit()
            except Exception as e:
                print(f"[verify] 交叉驗證失敗（不影響分析）: {e}")
            time.sleep(1.0)
        if quota_hit:
            break
    return total_analyzed, quota_hit


def main():
    parser = argparse.ArgumentParser(description="Financial news analysis engine")
    parser.add_argument("--batch", type=int, default=20, help="events per pass")
    parser.add_argument("--dry", action="store_true", help="dry run")
    parser.add_argument("--lang", default=None, help="zh or en")
    parser.add_argument("--model", default=MODEL, help="Gemini model")
    parser.add_argument("--time-budget", type=int, default=None,
                        help="max seconds per pass (default 300 or $ANALYSIS_TIME_BUDGET)")
    parser.add_argument("--backfill-verify", type=int, default=0,
                        help="cross-verify N historical unverified important events")
    args = parser.parse_args()

    if args.backfill_verify:
        done, quota_hit = backfill_verification(limit=args.backfill_verify)
        print(f"backfill_verified={done} quota_hit={quota_hit}")
        return

    analyzed, quota_hit = analyze_pending(
        batch_size=args.batch, dry=args.dry, languages=[args.lang] if args.lang else None,
        time_budget=args.time_budget,
    )
    print(f"analyzed={analyzed} quota_hit={quota_hit}")


if __name__ == "__main__":
    main()
