$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. "D:\AI-Agent-Workspace\XQ-AI神隊友\routines\_excel.ps1"
$apps = New-Object System.Collections.Generic.List[object]
foreach ($n in [RotHelper]::Names()) {
    if ($n -match '^!\{') { continue }
    try { $o = [Runtime.InteropServices.Marshal]::BindToMoniker($n); $app = $o.Application; if ($app) { $apps.Add($app) } } catch {}
}
try { $a = [Runtime.InteropServices.Marshal]::GetActiveObject("Excel.Application"); if ($a -and $a.Workbooks.Count -gt 0) { $apps.Add($a) } } catch {}
$seen = @{}
foreach ($app in $apps) {
    if ($seen.ContainsKey($app)) { continue }; $seen[$app] = $true
    foreach ($wb in $app.Workbooks) {
        Write-Output ("=== Workbook: " + $wb.Name)
        foreach ($ws in $wb.Worksheets) {
            try {
                $u = $ws.UsedRange; $rows = $u.Rows.Count
                $v2 = $u.Cells.Item(1,1).Value2
                $v5 = $u.Cells.Item(2,1).Value2
                $v6 = $u.Cells.Item(2,5).Value2
                Write-Output ("  sheet=" + $ws.Name + " rows=" + $rows + " A1=" + $v2 + " A2=" + $v5 + " E2=" + $v6)
            } catch { Write-Output ("  sheet=" + $ws.Name + " ERR") }
        }
    }
}
