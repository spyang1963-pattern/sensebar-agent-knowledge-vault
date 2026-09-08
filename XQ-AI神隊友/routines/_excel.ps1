# ============================================================
#  _excel.ps1 ─ 共用模組：掛上正在執行的 Excel，找出 XQ 報價工作表
#
#  由 snapshot.ps1 / check_env.ps1 以 dot-source 方式載入，不要直接執行。
#
#  為什麼不用 GetActiveObject：
#    XQ 的 DDE/RTD 持續推播讓 Excel 長時間忙碌，GetActiveObject 常回傳
#    「空殼」Application（Workbooks.Count = 0、讀到空表）。
#  解法：
#    1. 列舉 ROT（Running Object Table），直接綁活頁簿本身的 moniker
#    2. 註冊 OLE Message Filter，處理 Excel 忙碌時丟出的 RPC_E_CALL_REJECTED
#  必須用 STA 執行緒（powershell.exe -STA）。
# ============================================================

$helperSrc = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class RotHelper {
    [DllImport("ole32.dll")] private static extern int GetRunningObjectTable(int reserved, out IRunningObjectTable prot);
    [DllImport("ole32.dll")] private static extern int CreateBindCtx(int reserved, out IBindCtx ppbc);
    public static List<string> Names() {
        List<string> res = new List<string>();
        IRunningObjectTable rot; IBindCtx ctx;
        GetRunningObjectTable(0, out rot);
        CreateBindCtx(0, out ctx);
        IEnumMoniker en; rot.EnumRunning(out en); en.Reset();
        IMoniker[] mon = new IMoniker[1];
        while (en.Next(1, mon, IntPtr.Zero) == 0) {
            string name = null;
            try { mon[0].GetDisplayName(ctx, null, out name); } catch {}
            if (name != null) res.Add(name);
        }
        return res;
    }
}

[ComImport(), Guid("00000016-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IOleMessageFilter {
    [PreserveSig] int HandleInComingCall(int dwCallType, IntPtr hTaskCaller, int dwTickCount, IntPtr lpInterfaceInfo);
    [PreserveSig] int RetryRejectedCall(IntPtr hTaskCallee, int dwTickCount, int dwRejectType);
    [PreserveSig] int MessagePending(IntPtr hTaskCallee, int dwTickCount, int dwPendingType);
}

public class XqMessageFilter : IOleMessageFilter {
    [DllImport("Ole32.dll")] private static extern int CoRegisterMessageFilter(IOleMessageFilter newFilter, out IOleMessageFilter oldFilter);
    public static void Register() { IOleMessageFilter old = null; CoRegisterMessageFilter(new XqMessageFilter(), out old); }
    public static void Revoke()   { IOleMessageFilter old = null; CoRegisterMessageFilter(null, out old); }
    int IOleMessageFilter.HandleInComingCall(int dwCallType, IntPtr hTaskCaller, int dwTickCount, IntPtr lpInterfaceInfo) { return 0; }
    int IOleMessageFilter.RetryRejectedCall(IntPtr hTaskCallee, int dwTickCount, int dwRejectType) {
        if (dwRejectType == 2) { return 250; }
        return -1;
    }
    int IOleMessageFilter.MessagePending(IntPtr hTaskCallee, int dwTickCount, int dwPendingType) { return 2; }
}
'@
if (-not ('RotHelper' -as [type])) { Add-Type -TypeDefinition $helperSrc -Language CSharp }

# ---------- 這張工作表是不是 XQ 報價表？（標題列要有 代碼／成交／漲幅%） ----------
function Test-QuoteSheet($ws) {
    $u = $ws.UsedRange
    $rows = $u.Rows.Count; $cols = $u.Columns.Count
    if ($rows -lt 2 -or $cols -lt 3) { return $null }
    # 只抓「標題列」判定即可（避免對超大 UsedRange 一次 Value2，DDE 推播中易撞 COM 錯誤）
    $head = $u.Rows(1).Value2
    $m = @{}
    for ($c = 1; $c -le $cols; $c++) {
        $h = ([string]$head[1, $c]).Trim(); if ($h) { $m[$h] = $c }
    }
    if ($m.ContainsKey('代碼') -and $m.ContainsKey('成交') -and $m.ContainsKey('漲幅%')) {
        return [pscustomobject]@{ WS = $ws; Map = $m; Rows = $rows; Cols = $cols }
    }
    return $null
}

# ---------- 走一遍 ROT 與 GetActiveObject，找第一張報價表 ----------
function Get-QuoteHit {
    $apps = New-Object System.Collections.Generic.List[object]
    foreach ($n in [RotHelper]::Names()) {
        if ($n -match '^!\{') { continue }          # 跳過類別 moniker，只綁活頁簿
        try {
            $o = [Runtime.InteropServices.Marshal]::BindToMoniker($n)
            $app = $o.Application
            if ($app) { $apps.Add($app) }
        } catch {}
    }
    try {
        $a = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
        if ($a -and $a.Workbooks.Count -gt 0) { $apps.Add($a) }
    } catch {}

    foreach ($app in $apps) {
        try { if ($app.Workbooks.Count -lt 1) { continue } } catch { continue }
        $hit = $null
        try { $hit = Test-QuoteSheet $app.ActiveSheet } catch {}
        if ($hit) { $wn = 'unknown'; try { $wn = $app.ActiveWorkbook.Name } catch {}; return @($hit, $wn) }
        foreach ($wb in $app.Workbooks) {
            foreach ($ws in $wb.Worksheets) {
                try { $hit = Test-QuoteSheet $ws } catch {}
                if ($hit) { return @($hit, $wb.Name) }
            }
        }
    }
    return $null
}

# ---------- 對外：連上報價表（含重試），回傳 Hit / Workbook ----------
function Connect-XQSheet {
    param([int]$Retries = 8, [int]$DelayMs = 1500)
    [XqMessageFilter]::Register()
    $res = $null; $lastErr = ''
    for ($try = 1; $try -le $Retries; $try++) {
        try { $res = Get-QuoteHit } catch { $lastErr = $_.Exception.Message }
        if ($res) { break }
        Start-Sleep -Milliseconds $DelayMs
    }
    if (-not $res) {
        if ($lastErr -match '8001010A' -or $lastErr -match 'RPC_E_SERVERCALL' -or $lastErr -match '80010001') {
            throw "Excel 忙碌（可能有儲存格還在編輯狀態）。請切到 Excel 按 Esc 後重跑。原始訊息：$lastErr"
        }
        throw "找不到含『代碼/成交/漲幅%』標題列的報價工作表。$lastErr"
    }
    return [pscustomobject]@{ Hit = $res[0]; Workbook = $res[1] }
}

function Disconnect-XQSheet {
    try { [XqMessageFilter]::Revoke() } catch {}
}
