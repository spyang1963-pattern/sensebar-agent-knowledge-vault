# -*- coding: utf-8 -*-
"""
Build static site from the KB financial reports and push to GitHub Pages.

Reads:
  knowledge-base/金融/每日報告/YYYY-MM-DD.md
  knowledge-base/金融/深度報告/深度分析報告 YYYY-MM-DD 早上/傍晚.md

Writes into publisher/repo/ (a git checkout of financial-reports) and pushes.

Usage:
  python -m publisher.build            # build + push
  python -m publisher.build --no-push  # build only
"""
import os
import re
import sys
import glob
import shutil
import argparse
import subprocess
from datetime import datetime, timedelta, timezone

import markdown
from jinja2 import Environment, FileSystemLoader

from publisher import market_calendar

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(ROOT, "..", "knowledge-base", "金融")
DAILY_DIR = os.path.join(KB, "每日報告")
DEEP_DIR = os.path.join(KB, "深度報告")
PUB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repo")

TZ = timezone(timedelta(hours=8))
HTML_MD = markdown.Markdown(extensions=["tables", "fenced_code", "toc"])
ENV = Environment(loader=FileSystemLoader(os.path.dirname(os.path.abspath(__file__))))


def _sanitize_links(html):
    """Unwrap anchors whose href is not a real URL/path (LLM occasionally
    writes a link label in place of a URL, e.g. [x](Google News 聚合...))."""
    def repl(m):
        href = m.group(1)
        if "://" not in href and not href.startswith(("/", "#", "mailto:", ".")):
            if " " in href or any(ord(c) > 127 for c in href):
                return m.group(2)
        return m.group(0)
    return re.sub(r'<a href="([^"]+)">(.*?)</a>', repl, html, flags=re.S)


def _day_key(name):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else "0000-00-00"


def _fmt_label(fname):
    """Parse a daily/deep report filename into (day, slot_label)."""
    day = _day_key(fname)
    slot = ""
    if "早上" in fname:
        slot = "早上"
    elif "傍晚" in fname or "晚上" in fname:
        slot = "傍晚"
    return day, slot


def collect_reports():
    """Return list of {day, slot, kind, title, url, mtime, md_text} sorted desc."""
    items = []
    for path in sorted(glob.glob(os.path.join(DAILY_DIR, "*.md"))):
        with open(path, encoding="utf-8") as f:
            md_text = f.read()
        day = _day_key(os.path.basename(path))
        items.append({
            "day": day, "slot": "", "kind": "daily",
            "title": f"每日報告 {day}",
            "slug": f"daily/{day}",
            "mtime": os.path.getmtime(path),
            "md_text": md_text,
        })
    for path in sorted(glob.glob(os.path.join(DEEP_DIR, "深度分析報告 *.md"))):
        with open(path, encoding="utf-8") as f:
            md_text = f.read()
        base = os.path.basename(path)
        day, slot = _fmt_label(base)
        items.append({
            "day": day, "slot": slot, "kind": "deep",
            "title": f"深度分析報告 {day} {slot}".strip(),
            "slug": f"deep/{day}{('-am' if slot == '早上' else '-pm') if slot else ''}",
            "mtime": os.path.getmtime(path),
            "md_text": md_text,
        })
    # Chinese slot strings sort "早上" > "傍晚" (Unicode), which would put the
    # morning report ahead of the evening one. Rank the slot numerically so the
    # evening report (newer) sorts first under reverse=True.
    items.sort(key=lambda x: (x["day"], {"": 0, "早上": 0, "傍晚": 1}.get(x["slot"], 0)), reverse=True)
    return items


def build():
    items = collect_reports()
    out_root = os.path.join(PUB_DIR, "site")
    if os.path.exists(out_root):
        shutil.rmtree(out_root)
    os.makedirs(os.path.join(out_root, "daily"), exist_ok=True)
    os.makedirs(os.path.join(out_root, "deep"), exist_ok=True)
    tpl = ENV.get_template("template.html")

    by_day = {}
    for it in items:
        by_day.setdefault(it["day"], []).append(it)
    day_list = sorted(by_day.keys(), reverse=True)

    latest_daily = next((it for it in items if it["kind"] == "daily"), None)
    latest_deep = next((it for it in items if it["kind"] == "deep"), None)
    deep_by_day = {}
    for it in items:
        if it["kind"] == "deep":
            deep_by_day.setdefault(it["day"], []).append(it)
    deep_days = sorted(deep_by_day.keys(), reverse=True)
    deep_day_slug = {
        d: sorted(x["slug"] for x in deep_by_day[d])[-1] for d in deep_by_day
    }
    nav = {
        "latest_daily_day": latest_daily["day"] if latest_daily else "",
        "latest_deep_slug": latest_deep["slug"] if latest_deep else "",
        "deep_days": deep_days,
        "deep_day_slug": deep_day_slug,
    }

    for it in items:
        html_body = _sanitize_links(HTML_MD.convert(it["md_text"]))
        HTML_MD.reset()
        html = tpl.render(
            title=it["title"],
            day=it["day"],
            slot=it["slot"],
            kind=it["kind"],
            body=html_body,
            day_list=day_list,
            items=items,
            current_slug=it["slug"],
            up="../",
            **nav,
        )
        out = os.path.join(out_root, it["slug"].replace("/", os.sep) + ".html")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)

    # Index page (latest daily + deep)
    index_html = tpl.render(
        title="金融情報系統報告",
        day="", slot="", kind="index", body="",
        day_list=day_list, items=items, current_slug="index",
        latest_daily=latest_daily, latest_deep=latest_deep,
        up="", **nav,
    )
    with open(os.path.join(out_root, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # Market calendar page
    cal = market_calendar.build_calendar()
    cal_tpl = ENV.get_template("calendar.html")
    cal_html = cal_tpl.render(
        title="市場行事曆",
        day="", slot="", kind="calendar", body="",
        day_list=day_list, items=items, current_slug="calendar",
        cal=cal, up="", **nav,
    )
    with open(os.path.join(out_root, "calendar.html"), "w", encoding="utf-8") as f:
        f.write(cal_html)
    print(f"built {len(items)} reports + calendar -> {out_root}")
    return items


def push():
    if not os.path.isdir(os.path.join(PUB_DIR, ".git")):
        subprocess.run(["git", "init"], cwd=PUB_DIR, check=True)
        subprocess.run(["git", "remote", "add", "origin",
                        "https://github.com/spyang1963-pattern/financial-reports.git"],
                       cwd=PUB_DIR, check=True)
    # Move site content to repo root so GitHub Pages serves it. Remove stale
    # published files first (keep .git) to avoid move conflicts.
    site = os.path.join(PUB_DIR, "site")
    if os.path.exists(site):
        for entry in os.listdir(PUB_DIR):
            if entry in (".git", "site"):
                continue
            p = os.path.join(PUB_DIR, entry)
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
        for entry in os.listdir(site):
            shutil.move(os.path.join(site, entry), os.path.join(PUB_DIR, entry))
        shutil.rmtree(site)
    subprocess.run(["git", "add", "-A"], cwd=PUB_DIR, check=True)
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    subprocess.run(["git", "commit", "-m", f"chore: update reports {now}", "--allow-empty"],
                   cwd=PUB_DIR, check=True)
    subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=PUB_DIR, check=True)
    print("pushed to GitHub Pages")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    build()
    if not args.no_push:
        push()


if __name__ == "__main__":
    main()
