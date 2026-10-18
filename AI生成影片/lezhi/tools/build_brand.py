"""Build the brand profile and asset index for the LE Interior Design engine."""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(r"D:\AI-Agent-Workspace\AI生成影片\lezhi")
CROPS = ROOT / "assets" / "crops"

PROJECTS = [
    {"id": "h-time", "name": "華友聯 H-TIME", "type": "私宅", "area": "18坪 / 60 sq.m",
     "year": 2022, "city": "高雄",
     "materials": ["美耐板", "系統塑合板", "鍍鈦飾條", "冷烤漆", "超耐磨木地板"],
     "plates": ["02_h-time_a", "03_h-time_b"]},
    {"id": "taipu-mingrihui", "name": "太普 明日匯", "type": "私宅", "area": "33坪 / 109 sq.m",
     "year": 2021, "city": "高雄",
     "materials": ["大理石", "人造石", "美耐板", "系統塑合板", "鍍鈦飾條",
                   "黑灰茶鏡", "烤漆鐵件", "繃布", "超耐磨木地板"],
     "plates": ["04_taipu_mingrihui_a", "05_taipu_mingrihui_b", "06_taipu_mingrihui_c"]},
    {"id": "liuli-yuan", "name": "琉璃園", "type": "私宅", "area": "20坪 / 66 sq.m",
     "year": 2022, "city": "高雄",
     "materials": ["人造石", "美耐板", "系統塑合板", "鍍鈦飾條", "烤漆鐵件", "超耐磨木地板"],
     "plates": ["07_liuli_yuan"]},
    {"id": "rongyao-shiji", "name": "榮耀世紀", "type": "私宅", "area": "40坪 / 132 sq.m",
     "year": 2023, "city": "台北",
     "materials": ["大理石", "原石", "天然實木皮", "鍍鈦板", "特殊塗料", "水磨石", "海島型木地板"],
     "plates": ["08_rongyao_shiji"]},
]

PROFILE = {
    "brand": {
        "name": "樂之", "name_en": "LE Interior Design", "designer": "楊樂之",
        "location": "高雄", "service_area": ["高雄", "屏東"],
        "contact": {"email": "kse49210@gmail.com", "phone": "0988-813-511"},
        "education": "國立臺北教育大學 藝術與造形設計學系 (2012-2016)",
    },
    "services": ["到府丈量", "平面配置", "簡報製作", "施工圖繪製",
                 "預算製作", "工程發包", "現場監工", "Sketchup 3D建模+Enscape渲染"],
    "pricing_note": "平面配置設計費依實際坪數計價 3000 元/坪",
    "positioning": [
        "專注私宅室內設計", "小宅坪效與收納是強項", "南部地區（高雄/屏東）為主",
    ],
    "voice": {
        "tone": "專業、溫和、接地氣；不堆砌行話嚇人",
        "persona": "年輕但扎實、會站在屋主立場想的設計師",
        "avoid": ["過度誇大", "行話堆砌", "貶低同業"],
    },
    "palette": {  # auto-sampled from the portfolio crops
        "bg": "#FCFCFC", "surface": "#E7E9E8", "accent": "#758985", "ink": "#151A1B",
    },
    "typography": {"font": "Microsoft JhengHei", "note": "標題用粗體，內文清晰為先"},
    "format": {
        "master": "1080x1920 (9:16) @30fps", "source_note": "橫式原圖以 Ken Burns 斜移填滿直式",
        "duration_s": "30-60", "subtitles": "逐句字幕、燒進畫面、避開安全邊界",
    },
    "cta": {
        "primary": "高雄/屏東室內設計，免費諮詢",
        "secondary": "私訊詢問平面配置與報價",
        "channels": ["IG 私訊", "email", "電話"],
    },
    "prohibitions": [  # human-locked; AI must not override
        "不承諾保證工期或價格", "不批評同業或特定品牌",
        "不使用未經同意的他人作品或圖片", "不誇大「一定省錢/一定好看」",
        "不對結構安全做絕對斷言",
    ],
}


def size_of(p: Path) -> str:
    im = Image.open(p)
    return f"{im.width}x{im.height}"


def main() -> None:
    for proj in PROJECTS:
        files = []
        for plate in proj["plates"]:
            files += sorted(str(f.name) for f in CROPS.glob(f"{plate}__*.jpg"))
        proj["crops"] = files
        proj["photo_count"] = len(files)

    index = {p["id"]: {"name": p["name"], "year": p["year"], "city": p["city"],
                       "area": p["area"], "crops": p["crops"]} for p in PROJECTS}

    (ROOT / "brand" / "profile.json").parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "brand" / "profile.json").write_text(
        json.dumps(PROFILE, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "assets" / "projects.json").write_text(
        json.dumps(PROJECTS, ensure_ascii=False, indent=2), encoding="utf-8")

    for proj in PROJECTS:
        print(f"{proj['name']:14} {proj['area']:16} {proj['city']}  photos={proj['photo_count']}")
    total = sum(p["photo_count"] for p in PROJECTS)
    print("total project photos:", total)
    # sample sizes
    for proj in PROJECTS[:2]:
        for c in proj["crops"][:1]:
            print("  sample", c, size_of(CROPS / c))


if __name__ == "__main__":
    main()
