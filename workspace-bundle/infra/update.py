"""
環境更新工具
用法：python update.py [--bundle NAME] [--check-only] [--dry-run]

  --bundle NAME   只更新指定的 bundle（infra/knowledge-management/stock-monitor）
  --check-only    只檢查，不執行更新
  --dry-run       顯示會做什麼，但不實際執行
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# ── 路徑設定 ──
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", r"D:\AI-Agent-Workspace"))
BUNDLE_DIR = WORKSPACE / "workspace-bundle"
INFRA_DIR = BUNDLE_DIR / "infra"


def run(cmd, timeout=60, cwd=None):
    """執行命令並回傳輸出"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=timeout, cwd=cwd,
        )
        for enc in ["utf-8", "cp950", "big5", "latin-1"]:
            try:
                stdout = r.stdout.decode(enc)
                stderr = r.stderr.decode(enc)
                return stdout.strip(), r.returncode
            except (UnicodeDecodeError, AttributeError):
                continue
        return r.stdout.decode("latin-1", errors="replace").strip(), r.returncode
    except Exception as e:
        return str(e), 1


def read_version(bundle_dir):
    """讀取 VERSION 檔"""
    version_file = bundle_dir / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return None


def git_pull(cwd):
    """執行 git pull"""
    print(f"  執行 git pull...")
    out, code = run(["git", "pull"], cwd=str(cwd))
    if code == 0:
        print(f"  ✅ {out[:100]}")
        return True
    else:
        print(f"  ❌ git pull 失敗: {out[:200]}")
        return False


def install_requirements(bundle_dir, requirements_file):
    """安裝套件"""
    req_path = bundle_dir / requirements_file
    if not req_path.exists():
        print(f"  ℹ️ {requirements_file} 不存在，跳過")
        return True

    print(f"  安裝 {requirements_file}...")
    out, code = run([
        sys.executable, "-m", "pip", "install", "-r", str(req_path), "-q"
    ], timeout=120)

    if code == 0:
        print(f"  ✅ 套件安裝完成")
        return True
    else:
        print(f"  ⚠️ 部分套件可能安裝失敗")
        return False


def merge_config(defaults_path, machine_path):
    """合併設定檔（保留 machine.yaml 已有的 key）"""
    import yaml

    if not defaults_path.exists():
        return

    defaults = yaml.safe_load(defaults_path.read_text(encoding="utf-8")) or {}

    if machine_path.exists():
        machine = yaml.safe_load(machine_path.read_text(encoding="utf-8")) or {}
    else:
        machine = {}

    # 合併：machine 有的不覆蓋，沒有的從 defaults 補
    def merge(base, overlay):
        for key, value in base.items():
            if key not in overlay:
                overlay[key] = value
            elif isinstance(value, dict) and isinstance(overlay[key], dict):
                merge(value, overlay[key])

    merge(defaults, machine)

    # 寫回
    machine_path.parent.mkdir(parents=True, exist_ok=True)
    machine_path.write_text(
        yaml.dump(machine, allow_unicode=True, default_flow_style=False),
        encoding="utf-8"
    )
    print(f"  ✅ 設定已合併: {machine_path.name}")


def update_bundle(bundle_name, check_only=False, dry_run=False):
    """更新單個 bundle"""
    bundle_map = {
        "infra": {
            "name": "基礎層",
            "dir": INFRA_DIR,
            "requirements": "requirements-base.txt",
            "is_git": True,
        },
        "knowledge-management": {
            "name": "知識管理",
            "dir": BUNDLE_DIR / "knowledge-management",
            "requirements": "requirements.txt",
            "is_git": False,
        },
        "stock-monitor": {
            "name": "台股看板",
            "dir": WORKSPACE / "stock-monitor",
            "requirements": "requirements.txt",
            "is_git": False,
        },
    }

    if bundle_name not in bundle_map:
        print(f"❌ 未知的 bundle: {bundle_name}")
        return False

    info = bundle_map[bundle_name]
    print(f"\n{'='*50}")
    print(f"  更新 {info['name']} ({bundle_name})")
    print(f"{'='*50}")

    old_version = read_version(info["dir"])
    print(f"  目前版本: {old_version or '未安裝'}")

    if check_only:
        print(f"  ℹ️ 只檢查模式，不執行更新")
        return True

    if dry_run:
        print(f"  ℹ️ 模擬模式，以下是會執行的操作：")
        if info["is_git"]:
            print(f"    - git pull")
        print(f"    - pip install -r {info['requirements']}")
        return True

    # 執行更新
    if info["is_git"]:
        if not git_pull(WORKSPACE):
            return False

    # 安裝套件
    install_requirements(info["dir"], info["requirements"])

    # 合併設定
    if bundle_name == "infra":
        defaults = info["dir"] / "config" / "defaults.yaml"
        machine = info["dir"] / "config" / "machine.yaml"
        merge_config(defaults, machine)

    new_version = read_version(info["dir"])
    print(f"\n  更新後版本: {new_version or '未安裝'}")

    if old_version and new_version and old_version != new_version:
        print(f"  🎉 已從 {old_version} 更新到 {new_version}")

    return True


def main():
    parser = argparse.ArgumentParser(description="workspace-bundle 更新工具")
    parser.add_argument("--bundle", choices=["infra", "knowledge-management", "stock-monitor"],
                        help="只更新指定的 bundle")
    parser.add_argument("--check-only", action="store_true", help="只檢查，不執行更新")
    parser.add_argument("--dry-run", action="store_true", help="顯示會做什麼但不執行")
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  workspace-bundle 更新工具")
    print(f"  {datetime.now().isoformat()}")
    print(f"{'='*50}")

    bundles = [args.bundle] if args.bundle else ["infra", "knowledge-management", "stock-monitor"]

    success = 0
    for b in bundles:
        if update_bundle(b, check_only=args.check_only, dry_run=args.dry_run):
            success += 1

    print(f"\n{'='*50}")
    print(f"  完成: {success}/{len(bundles)} 個 bundle 更新成功")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
