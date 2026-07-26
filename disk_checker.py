#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
磁碟空間檢查模組
在派任務前 / 執行任務前盤點空間，推算能否完成任務

用法:
  from disk_checker import DiskCheck, NEED_MIN
  check = DiskCheck()
  result = check.can_run_task("D:\\", video_size_mb=150)
  if not result.ok:
      print(result.msg)
"""
import ctypes, os, socket
from dataclasses import dataclass
from typing import Optional

# === 閾值定義 ===
# 系統碟 C: 保留 2GB 避免系統異常
C_DRIVE_SAFE_GB = 2.0
# 工作碟 D: 保留 5GB（scheduler/worker 會寫入暫存）
D_DRIVE_SAFE_GB = 5.0
# Pipeline 過程需要約原始檔 2.5 倍的暫存空間
PIPELINE_SPACE_MULTIPLIER = 2.5


def get_free_space_gb(path: str) -> float:
    """取得指定路徑所在磁碟的剩餘空間（GB）"""
    try:
        free = ctypes.c_ulonglong()
        drive = os.path.splitdrive(path)[0] + "\\"
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            drive, None, None, ctypes.byref(free)
        )
        return free.value / 1024**3
    except Exception:
        return 0.0


def _is_local_drive(path: str) -> bool:
    """判斷是否為本機磁碟（非網路 UNC）"""
    return not path.startswith("\\\\")


@dataclass
class DiskCheckResult:
    ok: bool
    level: str        # "ok" | "warn" | "critical"
    c_free_gb: float
    d_free_gb: float
    c_required_raw: float  # 實際需要（不含保留）
    d_required_raw: float
    msg: str
    suggestion: str = ""


class DiskCheck:
    """
    磁碟盤點。使用方式：

    check = DiskCheck()
    result = check.can_run_task(work_drive="D:\\", video_size_mb=150)
    """
    def __init__(self):
        self.hostname = socket.gethostname()
        self.c_free = get_free_space_gb("C:\\")
        self.d_free = get_free_space_gb("D:\\")

    @staticmethod
    def resolve_drive(path: str) -> str:
        """從路徑反推磁碟代號（eg. D:）"""
        return os.path.splitdrive(path)[0] + "\\"

    def estimate_task_need(self, video_size_mb: float) -> dict:
        """估算一個任務所需的磁碟空間"""
        video_gb = video_size_mb / 1024.0
        # C: 用來放 auto-editor/ffmpeg 暫存（約等於原始檔大小）
        c_need = video_gb * 1.0
        # D: 原始檔 + pipeline 產出 + 暫存（預留 2.5 倍）
        d_need = video_gb * PIPELINE_SPACE_MULTIPLIER
        return {"c_gb": c_need, "d_gb": d_need, "video_gb": video_gb}

    def check_drive_health(self, drive: str, safe_gb: float) -> tuple:
        """檢查單一磁碟，回傳 (free_gb, is_local)"""
        free = get_free_space_gb(drive)
        is_local = _is_local_drive(drive)
        return free, is_local

    def can_run_task(
        self,
        work_drive: Optional[str] = None,
        video_size_mb: float = 0,
        video_path: Optional[str] = None,
    ) -> DiskCheckResult:
        """
        全面磁碟檢查

        參數:
          work_drive: 工作磁碟代號（eg. "D:\\"）。None 時自動從 video_path 推斷。
          video_size_mb: 原始影片大小（MB）
          video_path: 原始影片路徑（用於推斷 work_drive）

        回傳:
          DiskCheckResult
        """
        # ---- 找出工作磁碟 ----
        if work_drive is None and video_path:
            work_drive = self.resolve_drive(video_path)
        if work_drive is None:
            work_drive = "D:\\"

        # ---- 取得真實剩餘空間 ----
        c_free, _ = self.check_drive_health("C:\\", C_DRIVE_SAFE_GB)
        d_free = get_free_space_gb(work_drive)
        # 如果 work_drive 是 C:，d_free 沿用 c_free
        if work_drive.upper().startswith("C"):
            d_free = c_free

        # ---- 估算需求 ----
        need = self.estimate_task_need(video_size_mb)
        c_req = need["c_gb"]
        d_req = need["d_gb"]

        # ---- 門檻檢查 ----
        # C: 在 pipeline 過程中需要暫存
        c_after_task = c_free - c_req
        c_ok = c_after_task > C_DRIVE_SAFE_GB

        # D: 要放影片 + pipeline 產出
        d_after_task = d_free - d_req
        d_ok = d_after_task > D_DRIVE_SAFE_GB

        # ---- 判斷等級 ----
        msgs = []
        suggestions = []
        level = "ok"

        if not c_ok:
            level = "critical"
            msgs.append(
                f"C: 剩 {c_free:.1f}GB，需 {c_req:.1f}GB（安全線 {C_DRIVE_SAFE_GB}GB）"
            )
            suggestions.append("清理 C: 暫存檔或系統垃圾")

        if not d_ok:
            if d_after_task > 0:
                level = "warn"
                msgs.append(
                    f"{work_drive} 剩 {d_free:.1f}GB，需 {d_req:.1f}GB，執行後僅剩 {d_after_task:.1f}GB（低於安全線 {D_DRIVE_SAFE_GB}GB）"
                )
                suggestions.append("注意空間，建議預留更多再跑下一個任務")
            else:
                level = "critical"
                msgs.append(
                    f"{work_drive} 剩 {d_free:.1f}GB，需 {d_req:.1f}GB，容量不足！"
                )
                suggestions.append("清理工作磁碟或暫不接新任務")

        if level == "ok":
            msg = (
                f"C: {c_free:.1f}GB ✓ | {work_drive} {d_free:.1f}GB ✓"
            )
        else:
            msg = " | ".join(msgs)

        suggestion_text = "；".join(suggestions) if suggestions else ""

        return DiskCheckResult(
            ok=(c_ok and d_ok),
            level=level,
            c_free_gb=c_free,
            d_free_gb=d_free,
            c_required_raw=c_req,
            d_required_raw=d_req,
            msg=msg,
            suggestion=suggestion_text,
        )

    def can_accept_batch(self, tasks: list) -> tuple:
        """
        批次檢查：對於多個任務，計算總需求與空間是否足夠

        回傳:
          (ok, msg, max_tasks)
          ok=True 表示所有任務可消化
          max_tasks = 此批最大可安全執行數
        """
        total_mb = sum(t.get("size_mb", 0) for t in tasks)
        # 批次暫存可共享（ffmpeg/Whisper 不會疊加），但仍要保守估計
        # 保守：2 部同時執行
        concurrent = min(len(tasks), 2)
        active_mb = sum(
            sorted((t.get("size_mb", 0) for t in tasks), reverse=True)[:concurrent]
        )
        result = self.can_run_task(video_size_mb=active_mb)

        if not result.ok:
            return (False, result.msg, 0)

        # 簡單計算可處理數量
        max_count = 0
        running_total = 0.0
        for t in sorted(tasks, key=lambda x: x.get("size_mb", 0)):
            need = (t.get("size_mb", 0) / 1024) * PIPELINE_SPACE_MULTIPLIER
            if running_total + need < result.d_free_gb - D_DRIVE_SAFE_GB:
                running_total += need
                max_count += 1
            else:
                break

        return (True, result.msg, max_count)


# === 命令列使用 ===
if __name__ == "__main__":
    import sys
    # force utf-8 for console
    sys.stdout.reconfigure(encoding="utf-8")
    check = DiskCheck()
    print(f"主機: {check.hostname}")
    print(f"C: 剩餘: {check.c_free:.1f} GB")
    print(f"D: 剩餘: {check.d_free:.1f} GB")
    print()

    # 可以接受影片大小參數
    size = float(sys.argv[1]) if len(sys.argv) > 1 else 150
    result = check.can_run_task(video_size_mb=size)
    ok_mark = "[OK]" if result.ok else "[NG]"
    print(f"{ok_mark} 任務檢查 (影片 {size:.0f} MB):")
    print(f"  C: 有 {result.c_free_gb:.1f} GB / 需 {result.c_required_raw:.1f} GB",
          end="")
    if result.c_free_gb - result.c_required_raw > C_DRIVE_SAFE_GB:
        print(" (ok)")
    else:
        print(" (crit)")
    print(f"  D: 有 {result.d_free_gb:.1f} GB / 需 {result.d_required_raw:.1f} GB",
          end="")
    if result.d_free_gb - result.d_required_raw > D_DRIVE_SAFE_GB:
        print(" (ok)")
    else:
        print(" (crit)")
    print(f"  結論: {result.msg}")
    if result.suggestion:
        print(f"  建議: {result.suggestion}")
