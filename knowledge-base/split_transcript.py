#!/usr/bin/env python3
"""將完整逐字稿依主題拆分，讓 Obsidian 每個主題都有完整內容。"""
import re
from pathlib import Path

KB_DIR = Path(__file__).parent / "traditional-kline"
TRANSCRIPT = KB_DIR / "2022_08_06-傳統K線-逐字稿.md"

# 讀取完整逐字稿
content = TRANSCRIPT.read_text(encoding="utf-8")
# 移除 header（前 8 行）
lines = content.split("\n")
body_start = 0
for i, line in enumerate(lines):
    if line.strip() == "---":
        body_start = i + 1
        break
body = "\n".join(lines[body_start:])

# 主題與關鍵字對應（用來定位段落）
topics = [
    ("01", "多頭戰車", ["多頭戰車", "戰車型態", "休息K棒"]),
    ("02", "紅黑紅型態", ["紅黑紅", "中繼K線", "轉浪"]),
    ("03", "三個買進位置", ["底部區", "行進間", "轉讓區", "買進位置"]),
    ("04", "成交量分析", ["成交量", "量增", "量縮", "凹洞量"]),
    ("05", "潮汐理論", ["潮汐", "潮汐1", "潮汐2", "潮汐3"]),
    ("06", "推浪三部曲", ["推浪三部曲", "一部曲", "二部曲", "三部曲", "3C"]),
    ("07", "槓桿測量法", ["槓桿", "箱子", "一寶二兔", "等幅"]),
    ("08", "支撐與壓力", ["支撐", "壓力", "關卡", "頸線"]),
    ("09", "均線應用", ["均線", "10MA", "5MA", "21MA", "移動式停利"]),
    ("10", "停損停利策略", ["停損", "停利", "出場"]),
    ("11", "存股策略", ["存股", "長期投資", "殖利率"]),
    ("12", "非常態頭部", ["非常態頭部", "陌生浪", "反轉"]),
]

# 將逐字稿分段（每空行一段）
paragraphs = re.split(r"\n\s*\n", body)
paragraphs = [p.strip() for p in paragraphs if p.strip()]

# 為每個主題找對應段落
for num, title, keywords in topics:
    matched = []
    for para in paragraphs:
        if any(kw in para for kw in keywords):
            matched.append(para)
    
    if not matched:
        # 如果沒匹配到，取前後段落
        continue
    
    # 組合成 Markdown
    md = f"# {num}. {title} — 完整逐字稿\n\n"
    md += f"**講師：** 黃偉忠（三師爸）\n\n"
    md += f"---\n\n"
    md += "\n\n".join(matched)
    
    out_path = KB_DIR / f"{num}-{title}-逐字稿.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"[OK] {out_path.name}（{len(matched)} 段）")

print("\n完成！")
