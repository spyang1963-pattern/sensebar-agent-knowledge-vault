# -*- coding: utf-8 -*-
"""
overlay-text.py — 在圖片上加對話框與中文字（Pillow 跨平台版）
移植自 opencode-draw-free 的 overlay-text.ps1

用法：
  python overlay-text.py 圖片.png --text "壓力？那能吃嗎？" --subtitle "— 卡皮巴拉的人生哲學"
  python overlay-text.py 圖片.png --text "AI 教學" --output 輸出.png
"""

import argparse
import sys
import os
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("[X] 需要安裝 Pillow：pip install pillow", file=sys.stderr)
    sys.exit(1)


def find_cjk_font():
    """尋找可用的中文字體"""
    # Windows 常見中文字體路徑
    win_fonts = [
        "C:/Windows/Fonts/msjh.ttc",      # 微軟正黑體
        "C:/Windows/Fonts/msyh.ttc",      # 微軟雅黑
        "C:/Windows/Fonts/simhei.ttf",    # 黑體
        "C:/Windows/Fonts/simsun.ttc",    # 宋體
    ]

    # macOS 字體路徑
    mac_fonts = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ]

    # Linux 字體路徑
    linux_fonts = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ]

    for font_path in win_fonts + mac_fonts + linux_fonts:
        if os.path.exists(font_path):
            return font_path

    # 嘗試用系統字體名稱
    try:
        ImageFont.truetype("msjh.ttc", 42)
        return "msjh.ttc"
    except Exception:
        pass

    return None


def draw_rounded_rect(draw, bbox, radius, fill=None, outline=None, width=1):
    """繪製圓角矩形"""
    x1, y1, x2, y2 = bbox
    r = radius

    # 使用 pieslice 繪製四個圓角
    draw.pieslice([x1, y1, x1 + 2 * r, y1 + 2 * r], 180, 270, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - 2 * r, y1, x2, y1 + 2 * r], 270, 360, fill=fill, outline=outline, width=width)
    draw.pieslice([x1, y2 - 2 * r, x1 + 2 * r, y2], 90, 180, fill=fill, outline=outline, width=width)
    draw.pieslice([x2 - 2 * r, y2 - 2 * r, x2, y2], 0, 90, fill=fill, outline=outline, width=width)

    # 填充中間區域
    draw.rectangle([x1 + r, y1, x2 - r, y2], fill=fill)
    draw.rectangle([x1, y1 + r, x2, y2 - r], fill=fill)

    # 繪製邊框
    if outline:
        draw.line([x1 + r, y1, x2 - r, y1], fill=outline, width=width)
        draw.line([x1 + r, y2, x2 - r, y2], fill=outline, width=width)
        draw.line([x1, y1 + r, x1, y2 - r], fill=outline, width=width)
        draw.line([x2, y1 + r, x2, y2 - r], fill=outline, width=width)


def overlay_text(src_path, dst_path, text, subtitle=None, font_size_main=42, font_size_sub=22):
    """
    在圖片上加對話框與文字

    Args:
        src_path: 來源圖片路徑
        dst_path: 輸出圖片路徑
        text: 主文字
        subtitle: 副標題（可選）
        font_size_main: 主文字大小
        font_size_sub: 副標題大小
    """
    # 載入圖片
    img = Image.open(src_path).convert("RGBA")
    W, H = img.size

    # 建立繪圖層
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 尋找字體
    font_path = find_cjk_font()
    if font_path:
        try:
            font_main = ImageFont.truetype(font_path, font_size_main)
            font_sub = ImageFont.truetype(font_path, font_size_sub)
        except Exception:
            font_main = ImageFont.load_default()
            font_sub = ImageFont.load_default()
    else:
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    # === 對話框設定 ===
    bubbleW = 560
    bubbleH = 160
    bubbleX = (W - bubbleW) // 2
    bubbleY = 60
    radius = 30

    # 白色填充 + 黑色邊框
    white = (255, 255, 255, 255)
    black = (0, 0, 0, 255)
    text_color = (60, 60, 60, 255)

    # 繪製圓角矩形對話框
    draw_rounded_rect(draw, (bubbleX, bubbleY, bubbleX + bubbleW, bubbleY + bubbleH),
                      radius, fill=white, outline=black, width=5)

    # 對話框尾巴（三角形）
    tail_start = bubbleX + 180
    tail_pts = [
        (tail_start, bubbleY + bubbleH),
        (tail_start - 50, bubbleY + bubbleH + 70),
        (tail_start + 80, bubbleY + bubbleH),
    ]
    draw.polygon(tail_pts, fill=white, outline=black)

    # 蓋住底部邊框線（用白色矩形）
    draw.rectangle([tail_start - 45, bubbleY + bubbleH - 5, tail_start + 75, bubbleY + bubbleH + 5], fill=white)

    # === 主文字 ===
    # 計算文字大小並置中
    bbox = draw.textbbox((0, 0), text, font=font_main)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = bubbleX + (bubbleW - text_w) // 2
    text_y = bubbleY + (bubbleH - text_h) // 2
    draw.text((text_x, text_y), text, fill=text_color, font=font_main)

    # === 底部副標 ===
    if subtitle:
        sub_bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
        sub_w = sub_bbox[2] - sub_bbox[0]
        sub_h = sub_bbox[3] - sub_bbox[1]
        sub_padding = 15
        sub_rect_w = sub_w + sub_padding * 2
        sub_rect_h = sub_h + sub_padding * 2
        sub_x = (W - sub_rect_w) // 2
        sub_y = H - sub_rect_h - 30

        # 半透明黑色背景
        sub_bg = (0, 0, 0, 120)
        draw_rounded_rect(draw, (sub_x, sub_y, sub_x + sub_rect_w, sub_y + sub_rect_h),
                          12, fill=sub_bg)

        # 白色文字
        sub_text_x = sub_x + (sub_rect_w - sub_w) // 2
        sub_text_y = sub_y + (sub_rect_h - sub_h) // 2
        draw.text((sub_text_x, sub_text_y), subtitle, fill=(255, 255, 255, 255), font=font_sub)

    # 合併
    result = Image.alpha_composite(img, overlay).convert("RGB")

    # 儲存
    result.save(dst_path, "PNG")
    print(f"[OK] 已加上對話框：{dst_path}")


def main():
    parser = argparse.ArgumentParser(description="在圖片上加對話框與中文字")
    parser.add_argument("image", help="來源圖片路徑")
    parser.add_argument("--text", required=True, help="主文字")
    parser.add_argument("--subtitle", default=None, help="副標題（可選）")
    parser.add_argument("--output", "-o", default=None, help="輸出路徑（預設：<檔名>_overlay.png）")
    parser.add_argument("--font-size", type=int, default=42, help="主文字大小（預設：42）")
    parser.add_argument("--sub-font-size", type=int, default=22, help="副標題大小（預設：22）")
    args = parser.parse_args()

    src = os.path.abspath(args.image)
    if not os.path.exists(src):
        print(f"[X] 檔案不存在：{src}", file=sys.stderr)
        sys.exit(1)

    dst = args.output or (os.path.splitext(src)[0] + "_overlay.png")

    overlay_text(src, dst, args.text, args.subtitle, args.font_size, args.sub_font_size)


if __name__ == "__main__":
    main()
