# _diag_rot.ps1 - 診斷「Excel 為什麼綁不上」：列 ROT 所有 moniker、EXCEL 程序、權限身分
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot '_excel.ps1')

Write-Output "===== 1. 目前身分/權限 ====="
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
Write-Output ("user=" + $id.Name + "  IsElevated=" + [Security.Principal.WindowsPrincipal]::new($id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))

Write-Output "===== 2. ROT 原始 moniker 清單 ====="
$names = [RotHelper]::Names()
Write-Output "ROT moniker 數量: $($names.Count)"
$i = 0
foreach ($n in $names) { $i++; Write-Output ("  [$i] " + $n) }

Write-Output "===== 3. 所有 EXCEL 程序 ====="
$procs = Get-Process EXCEL -ErrorAction SilentlyContinue
Write-Output "EXCEL 程序數量: $($procs.Count)"
foreach ($p in $procs) {
    Write-Output ("  PID=" + $p.Id + "  Session=" + $p.SessionId + "  Title=[" + $p.MainWindowTitle + "]  Path=[" + $p.Path + "]")
}

Write-Output "===== 4. GetActiveObject 試驗 ====="
try {
    $a = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application")
    Write-Output "GetActiveObject OK"
    $wbCount = 0
    try { $wbCount = $a.Workbooks.Count } catch { Write-Output "  Workbooks.Count 讀取失敗: $($_.Exception.Message)" }
    Write-Output ("  Workbooks.Count = " + $wbCount)
    try { Write-Output ("  Excel 版本 = " + $a.Version) } catch {}
} catch {
    Write-Output "GetActiveObject 失敗: $($_.Exception.Message)"
}
Write-Output "===== 5. 直接逐一綁 ROT moniker 並列出其 Application 的 Workbooks ====="
$seen = @{}
foreach ($n in $names) {
    if ($n -match '^!\{\(') { continue }
    try {
        $o = [Runtime.InteropServices.Marshal]::BindToMoniker($n)
        $app = $o.Application
        if (-not $app -or $seen.ContainsKey($app)) { continue }
        $seen[$app] = $true
        Write-Output ("  moniker: " + $n)
        foreach ($wb in $app.Workbooks) {
            Write-Output ("    Workbook: " + $wb.Name)
            foreach ($ws in $wb.Worksheets) {
                $s = "<ERR>"
                try {
                    $u = $ws.UsedRange
                    $s = "rows=" + $u.Rows.Count + " A1=[" + $u.Cells.Item(1,1).Value2 + "]"
                } catch { $s = "read ERR: " + $_.Exception.Message }
                Write-Output ("      sheet=" + $ws.Name + "  " + $s)
            }
        }
    } catch { Write-Output ("  綁定失敗 [$n]: " + $_.Exception.Message) }
}