#!/usr/bin/env python3
"""OpenAI gpt-image-2 生圖腳本。"""
import os
import sys
import base64
import argparse
from pathlib import Path
from datetime import datetime

MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "medium"
DEFAULT_N = 1


def load_env_from_file(path: Path):
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_env():
    load_env_from_file(Path.cwd() / ".env")
    load_env_from_file(Path.home() / ".openai.env")


def resolve_outdir(user_outdir: str | None) -> Path:
    if user_outdir:
        return Path(user_outdir)
    cwd = Path.cwd()
    slides_dir = cwd / "slides"
    if slides_dir.exists():
        return slides_dir / "generated"
    return cwd / "generated"


def _save_results(result, name: str, n: int, outdir: Path) -> list[Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved = []
    for i, item in enumerate(result.data):
        suffix = f"_{i + 1}" if n > 1 else ""
        out_path = outdir / f"{name}_{stamp}{suffix}.png"
        png_bytes = base64.b64decode(item.b64_json)
        out_path.write_bytes(png_bytes)
        saved.append(out_path)
        print(f"  [OK] {out_path}")
    return saved


def draw(prompt: str, size: str, quality: str, n: int, name: str, outdir: Path) -> list[Path]:
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        print("錯誤：找不到 OPENAI_API_KEY。", file=sys.stderr)
        sys.exit(1)
    outdir.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    print(f"生圖中（{MODEL}, {size}, {quality}, n={n}） -> {outdir}", file=sys.stderr)
    result = client.images.generate(model=MODEL, prompt=prompt, size=size, quality=quality, n=n)
    return _save_results(result, name, n, outdir)


def edit(prompt: str, image_path: Path, mask_path: Path | None, size: str, quality: str, n: int, name: str, outdir: Path) -> list[Path]:
    from openai import OpenAI
    if not os.getenv("OPENAI_API_KEY"):
        print("錯誤：找不到 OPENAI_API_KEY。", file=sys.stderr)
        sys.exit(1)
    if not image_path.exists():
        print(f"錯誤：找不到來源圖片 {image_path}", file=sys.stderr)
        sys.exit(1)
    outdir.mkdir(parents=True, exist_ok=True)
    client = OpenAI()
    mode = "遮罩改圖" if mask_path else "全圖改圖"
    print(f"改圖中（{mode}, {MODEL}, {size}, {quality}, n={n}） -> {outdir}", file=sys.stderr)
    kwargs = dict(model=MODEL, image=open(image_path, "rb"), prompt=prompt, size=size, quality=quality, n=n)
    if mask_path:
        if not mask_path.exists():
            print(f"錯誤：找不到遮罩圖片 {mask_path}", file=sys.stderr)
            sys.exit(1)
        kwargs["mask"] = open(mask_path, "rb")
    result = client.images.edit(**kwargs)
    return _save_results(result, name, n, outdir)


def main():
    load_env()
    parser = argparse.ArgumentParser(description="AI 生圖/改圖（OpenAI gpt-image-2）")
    parser.add_argument("prompt", nargs="+", help="要畫什麼/如何修改")
    parser.add_argument("--edit", default=None, metavar="IMAGE_PATH", help="改圖模式：來源圖片路徑")
    parser.add_argument("--mask", default=None, metavar="MASK_PATH", help="遮罩圖片路徑")
    parser.add_argument("--size", default=DEFAULT_SIZE, help="1024x1024 / 1536x1024 / 1024x1536 / auto")
    parser.add_argument("--quality", default=DEFAULT_QUALITY, choices=["low", "medium", "high", "auto"])
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="生成張數 1-8")
    parser.add_argument("--name", default="image", help="檔名前綴")
    parser.add_argument("--outdir", default=None, help="輸出目錄")
    args = parser.parse_args()
    prompt = " ".join(args.prompt)
    outdir = resolve_outdir(args.outdir)
    if args.edit:
        edit(prompt, Path(args.edit), Path(args.mask) if args.mask else None,
             args.size, args.quality, args.n, args.name, outdir)
    else:
        draw(prompt, args.size, args.quality, args.n, args.name, outdir)


if __name__ == "__main__":
    main()
