# -*- coding: utf-8 -*-
"""
draw_free.py — 免費 AI 生圖（Pollinations.ai）— 零 API Key、零 GPU
移植自 opencode-draw-free 的 draw-free.ps1，Python 跨平台版

用法：
  python draw_free.py "一隻可愛的水豚在讀書"
  python draw_free.py "演講海報" --size 1536x1024 --name poster
  python draw_free.py "四格分鏡" --n 4 --name storyboard
  python draw_free.py "等距視角的城市" --seed 42 --name city

支援模型：flux / turbo / nanobanana / seedream（建議不指定，自動最快）
"""

import argparse
import os
import random
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path


# 模型說明
MODELS = {
    "flux": "高品質通用",
    "turbo": "快速 5-10 秒",
    "nanobanana": "攝影寫實",
    "seedream": "東方美學",
}


def generate_image(prompt, width=1024, height=1024, model=None, seed=None,
                   outdir=".", name="image", max_retries=4):
    """
    呼叫 Pollinations.ai 生成一張圖片

    Args:
        prompt: 圖片描述
        width: 寬度
        height: 高度
        model: 模型名稱（None = 自動，最快）
        seed: 隨機種子
        outdir: 輸出目錄
        name: 檔名前綴
        max_retries: 最大重試次數

    Returns:
        成功回傳檔名路徑，失敗回傳 None
    """
    # 加入繁體中文後綴
    full_prompt = prompt + "，圖片中的所有文字請使用繁體中文（Traditional Chinese）"
    encoded_prompt = urllib.parse.quote(full_prompt)

    # 建立 URL
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"
    if model:
        url += f"&model={model}"
    if seed is not None:
        url += f"&seed={seed}"

    # 時間戳記
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(outdir) / f"{name}_{stamp}.png"

    # 自動重試
    for retry in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "draw-free-python/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()

            # 檢查檔案大小（太小可能是錯誤）
            if len(data) < 5000:
                content = data.decode("utf-8", errors="ignore")
                if "Queue full" in content or "overloaded" in content:
                    print(f"  [重試 {retry}/{max_retries}] 伺服器佇列已滿，等候 5 秒...")
                    time.sleep(5)
                    continue
                elif "error" in content.lower():
                    print(f"  [重試 {retry}/{max_retries}] 伺服器回傳錯誤，等候 3 秒...")
                    time.sleep(3)
                    continue

            # 儲存
            out_path.write_bytes(data)
            size_kb = len(data) / 1024
            print(f"  [OK] {out_path}（{size_kb:.0f} KB）")
            return str(out_path)

        except Exception as e:
            if retry < max_retries:
                print(f"  [重試 {retry}/{max_retries}] {e}，等候 3 秒...")
                time.sleep(3)
            else:
                print(f"  [FAIL] 失敗：{e}", file=sys.stderr)
                return None

    return None


def main():
    parser = argparse.ArgumentParser(
        description="免費 AI 生圖（Pollinations.ai，零 API Key）",
        epilog="提示：不指定 --model 最快（自動路由，1-3 秒）。指定模型會慢 15-40 倍。"
    )
    parser.add_argument("prompt", nargs="+", help="要畫的內容描述")
    parser.add_argument("--size", default="1024x1024",
                        help="圖片尺寸 WIDTHxHEIGHT（預設：1024x1024）")
    parser.add_argument("--model", default=None,
                        choices=list(MODELS.keys()),
                        help="AI 模型（建議不指定，自動最快）")
    parser.add_argument("--seed", type=int, default=None,
                        help="隨機種子（相同 seed = 相同圖片）")
    parser.add_argument("--n", type=int, default=1, choices=range(1, 9),
                        help="生成張數 1-8（預設：1）")
    parser.add_argument("--name", default="image", help="檔名前綴")
    parser.add_argument("--outdir", default=None, help="輸出目錄（預設：./generated/）")
    args = parser.parse_args()

    # 合併 prompt
    prompt = " ".join(args.prompt)

    # 解析尺寸
    import re
    if re.match(r"^\d+x\d+$", args.size):
        width, height = map(int, args.size.split("x"))
    else:
        print("[X] --size 格式應為 WIDTHxHEIGHT，例如 1024x1024", file=sys.stderr)
        sys.exit(1)

    # 決定輸出目錄
    if args.outdir:
        outdir = args.outdir
    else:
        cwd = Path.cwd()
        slides_dir = cwd / "slides"
        if slides_dir.exists():
            outdir = slides_dir / "generated"
        else:
            outdir = cwd / "generated"
    Path(outdir).mkdir(parents=True, exist_ok=True)

    # 模型標籤
    model_label = args.model if args.model else "自動"
    print(f"免費生圖中（Pollinations.ai, {model_label}, {width}x{height}, n={args.n}）-> {outdir}")
    if args.model:
        print(f"  提示：指定模型會明顯變慢（實測 40 秒以上／張）。不加 --model 最快。")

    # 生成 N 張
    saved_files = []
    for i in range(1, args.n + 1):
        # 計算 seed
        if args.seed is not None:
            current_seed = args.seed + (i - 1)
        else:
            current_seed = random.randint(1, 999999999)

        # 檔名後綴（多張時加 _1, _2...）
        suffix = f"_{i}" if args.n > 1 else ""
        file_name = f"{args.name}{suffix}"

        print(f"  [{i}/{args.n}] 生成中... seed={current_seed}")
        result = generate_image(
            prompt, width, height, args.model, current_seed,
            outdir, file_name
        )
        if result:
            saved_files.append(result)
        else:
            print(f"  [SKIP] 第 {i} 張失敗")

    # 回報結果
    if saved_files:
        print(f"\n完成！共生成了 {len(saved_files)} 張圖片：")
        for f in saved_files:
            print(f"  {f}")
    else:
        print("\n失敗：沒有圖片成功生成", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
