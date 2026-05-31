# ============================================================
# scheduled_cleanup.ps1
# Spider Diary — 每周定时清理任务
# 建议执行时间: 每周日 02:00 (通过 Windows 任务计划程序)
# ============================================================

param(
    [string]$BasePath = "",
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$LogDir = Join-Path $PSScriptRoot "logs"
$ReportDir = Join-Path $PSScriptRoot "reports"

# 创建目录
New-Item -ItemType Directory -Force -Path $LogDir, $ReportDir, "$ReportDir\docker_reports" | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "scheduled_cleanup_$Timestamp.log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Message"
    Add-Content -Path $LogFile -Value $line
    if ($Verbose -or $Level -eq "ERROR") { Write-Host $line }
}

Write-Log "=== Spider Diary Scheduled Cleanup Started ==="

# ── 1. Python 环境检查 ───────────────────────────────────────
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $PythonCmd) {
    Write-Log "Python not found in PATH" "ERROR"
    exit 1
}
Write-Log "Python: $($PythonCmd.Source)"

# ── 2. 运行 cleanup ───────────────────────────────────────────
Write-Log "Running spider-diary cleanup..."
try {
    $cleanupArgs = @("cleanup", "--base-path", $(if ($BasePath) { $BasePath } else { $PSScriptRoot }))
    $result = & $PythonCmd.Source -m spider_diary $cleanupArgs 2>&1
    Write-Log "Cleanup completed: $result"
} catch {
    Write-Log "Cleanup failed: $_" "ERROR"
}

# ── 3. 运行 Docker 健康检查 ──────────────────────────────────
Write-Log "Running spider-diary docker-health..."
try {
    $dhArgs = @("docker-health", "--base-path", $(if ($BasePath) { $BasePath } else { $PSScriptRoot }))
    $result = & $PythonCmd.Source -m spider_diary $dhArgs 2>&1
    Write-Log "Docker health report: $result"
} catch {
    Write-Log "Docker health check failed: $_" "ERROR"
}

# ── 4. 归档旧报告 (30天以上) ─────────────────────────────────
$ArchiveDir = Join-Path $ReportDir "archive"
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
$Cutoff = (Get-Date).AddDays(-30)

$OldReports = Get-ChildItem $ReportDir -File | Where-Object {
    $_.Extension -eq '.json' -and $_.LastWriteTime -lt $Cutoff
}

if ($OldReports.Count -gt 0) {
    $ArchiveFile = Join-Path $ArchiveDir "reports_$Timestamp.zip"
    $OldReports | Compress-Archive -DestinationPath $ArchiveFile -Force
    $OldReports | Remove-Item -Force
    Write-Log "Archived $($OldReports.Count) old reports to $ArchiveFile"
} else {
    Write-Log "No old reports to archive"
}

# ── 5. 归档旧日志 (7天以上) ──────────────────────────────────
$OldLogs = Get-ChildItem $LogFile -File -ErrorAction SilentlyContinue | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-7)
}
if ($OldLogs.Count -gt 0) {
    $OldLogs | Remove-Item -Force
    Write-Log "Cleaned up $($OldLogs.Count) old log files"
}

# ── 6. 生成摘要 ──────────────────────────────────────────────
$Summary = @{
    timestamp      = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
    cleanup_run    = $true
    docker_health  = $true
    reports_archived = if ($OldReports) { $OldReports.Count } else { 0 }
    logs_cleaned   = if ($OldLogs) { $OldLogs.Count } else { 0 }
    status         = "ok"
}

$SummaryFile = Join-Path $LogDir "summary_$Timestamp.json"
$Summary | ConvertTo-Json -Depth 3 | Set-Content -Path $SummaryFile -Encoding UTF8

Write-Log "=== Spider Diary Scheduled Cleanup Complete ==="
Write-Log "Log: $LogFile"
Write-Log "Summary: $SummaryFile"
