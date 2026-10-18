"""
Extract original photos embedded in the LE portfolio PDF into an asset library.

Deduplicates by md5, skips tiny images (icons/decor), and writes a manifest
that maps each page to its extracted files for later per-project grouping.
"""
import fitz
import hashlib
import json
import time
from pathlib import Path

SRC = Path(r"D:\!!AI agent 工作指南\3師爸近期影音repo彙整\樂之作品\2024LE作品集 Copy.pdf")
OUT = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi\assets\photos")
MIN = 800  # ignore images smaller than this on either side


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(SRC)
    seen: dict[str, str] = {}
    manifest = []
    t0 = time.time()

    for i in range(doc.page_count):
        page = doc[i]
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
            except Exception as exc:  # noqa: BLE001
                manifest.append({"page": i + 1, "xref": xref, "error": str(exc)})
                continue
            data = base["image"]
            w, h, ext = base["width"], base["height"], base["ext"]
            if w < MIN or h < MIN:
                continue
            hsh = hashlib.md5(data).hexdigest()[:12]
            if hsh in seen:
                manifest.append({"page": i + 1, "xref": xref, "dup_of": seen[hsh]})
                continue
            name = f"p{i + 1:02d}_{hsh}_{w}x{h}.{ext}"
            (OUT / name).write_bytes(data)
            seen[hsh] = name
            manifest.append({"page": i + 1, "xref": xref, "file": name, "w": w, "h": h, "bytes": len(data)})
            print(f"saved {name} ({len(data) // 1024} KB)", flush=True)

    (OUT.parent / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = sum(m.get("bytes", 0) for m in manifest) // (1024 * 1024)
    print(f"\nunique={len(seen)} total~{total}MB elapsed={time.time() - t0:.0f}s")
    print(f"manifest -> {OUT.parent / 'manifest.json'}")


if __name__ == "__main__":
    main()
