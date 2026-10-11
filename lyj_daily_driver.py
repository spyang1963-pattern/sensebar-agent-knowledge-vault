import os, re, subprocess, sys, traceback

ROOT = r"D:\AI-Agent-Workspace\knowledge-base\金融交易\呂佳霖"
BASE = os.path.join(ROOT, "每日盤後分析(原稿)2020-4-16---2021-4-27")
TPL = r"D:\AI-Agent-Workspace\knowledge-base\金融交易\理周學院\林教授\_preview_林教授 量價時間角度的三道菜 課程筆記.docx"
NOTES_PY = r"D:\AI-Agent-Workspace\make_course_note.py"
PY = sys.executable

# Folders to EXCLUDE from monthly books (already covered elsewhere)
EXCL = {
    "!2020年每月線上研討會",
    "2020-09-05(週六)",  # contains 9月份線上分析 -> in teaching book
    "2020-10-07(週三)---10月份線上分析",
    "2020-11-08(週日)--11月份線上教學--扣抵、絕招",
    "2020-12-05(週六)---12月份線上教學--飆股",
    "2021-01-01(週五)---元月份線上教學--飆股",
    "2021-02-06(週六)---2月份線上教學",
    "2021-03-06(週六)---3月份線上教學",
    "2021-04-04(週日)---4月份線上教學",
}
# 2020-07-13 / 2020-08-07 "線上演講會" intentionally NOT excluded (merged into monthly book)

MONTHS = ["2020-04", "2020-05", "2020-06", "2020-07", "2020-08", "2020-09",
          "2020-10", "2020-11", "2020-12", "2021-01", "2021-02", "2021-03", "2021-04"]

ROWS = []
for day in sorted(os.listdir(BASE)):
    dp = os.path.join(BASE, day)
    if not os.path.isdir(dp):
        continue
    if day in EXCL:
        continue
    m = re.match(r"(\d{4})-(\d{2})-\d{2}", day)
    if not m:
        continue
    key = m.group(1) + "-" + m.group(2)
    for f in sorted(os.listdir(dp)):
        if f.lower().endswith(".md"):
            ROWS.append((key, os.path.join(dp, f)))

failed = []
for key in MONTHS:
    files = [p for k, p in ROWS if k == key]
    if not files:
        print(f"[SKIP] {key}: no files", flush=True)
        continue
    ym, mm = key.split("-")
    title = f"呂佳霖 每日盤後分析-{ym}年{int(mm)}月"
    cmd = [PY, "-X", "utf8", NOTES_PY, "--title", title, "--mds"] + files + \
          ["--out", ROOT, "--template", TPL]
    print(f"\n===== {key} {len(files)} files -> {title} =====", flush=True)
    try:
        r = subprocess.run(cmd, timeout=5400)
        if r.returncode != 0:
            failed.append(key)
            print(f"[FAIL] {key} rc={r.returncode}", flush=True)
    except Exception as e:
        failed.append(key)
        print(f"[ERROR] {key}: {e}", flush=True)
        traceback.print_exc()

print("\n=== DONE ===")
print("failed:", failed if failed else "none")