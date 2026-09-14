"""
自動更新 GitHub Pages
跑完 run_stock_analysis.py 後執行此腳本，自動推送看板到 GitHub
"""
import os
import subprocess
import shutil
from datetime import datetime

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_DIR = os.path.join(REPO_DIR, "stock-monitor", "output", "dashboard")
DOCS_DIR = os.path.join(REPO_DIR, "docs")


def run(cmd):
    """執行命令並回傳結果"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=REPO_DIR)
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr.strip()}")
    return result.returncode == 0


def main():
    print("=" * 50)
    print("  更新 GitHub Pages")
    print(f"  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. 複製 dashboard 到 docs
    print("\n[1] 複製看板到 docs/...")
    os.makedirs(DOCS_DIR, exist_ok=True)
    for f in os.listdir(DASHBOARD_DIR):
        if f.endswith(".html"):
            src = os.path.join(DASHBOARD_DIR, f)
            dst = os.path.join(DOCS_DIR, f)
            shutil.copy2(src, dst)
            print(f"  {f}")

    # 2. git add
    print("\n[2] git add docs/...")
    if run("git add docs/"):
        print("  OK")

    # 3. 檢查是否有變更
    print("\n[3] 檢查變更...")
    result = subprocess.run("git status --porcelain docs/", shell=True, capture_output=True, text=True, cwd=REPO_DIR)
    if not result.stdout.strip():
        print("  無變更，跳過")
        return

    # 4. git commit
    print("\n[4] git commit...")
    date_str = datetime.now().strftime("%Y-%m-%d")
    if run(f'git commit -m "update dashboard {date_str}"'):
        print("  OK")

    # 5. git push
    print("\n[5] git push...")
    if run("git push origin master"):
        print("  OK")

    print("\n" + "=" * 50)
    print("  完成！")
    print(f"  看板網址: https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault/")
    print("=" * 50)


if __name__ == "__main__":
    main()
