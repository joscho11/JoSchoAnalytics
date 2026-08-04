<#
  Local daily driver for the 2026 point-in-time market archive.

  WHY THIS EXISTS
  ---------------
  The GitHub Actions run captures the same snapshot, but this repository is PUBLIC, so its
  artifacts are capped at 90 days and nothing lands on disk automatically (proven: adp_logs/
  holds one manual file despite the workflow committing daily since 2026-07-27). This task is
  the DURABLE copy: it writes into the local private archive, which never expires.

  WHAT IT WRITES — nothing outside market_snapshots/:
    market_snapshots/_task_logs/<UTC>.log   full stdout+stderr of the run
    market_snapshots/task_runs.jsonl        append-only ledger: one row per invocation

  It never touches the live board overlay, the season dataset, the ADP cache, or any frozen
  artifact — it only invokes capture_market_snapshot.py, whose own write paths are confined to
  the archive.

  INTERPRETER: $env:JOSCHO_CAPTURE_PY if set and present, else the AI_hedge_fund venv (the
  repo's own .venv is broken), else whatever `python` resolves to. The resolved path is logged
  every run so a silent interpreter swap is visible.

  NO CREDENTIALS: the scheduled task registers under the current user with no stored password
  (it runs when Joseph is logged on). Nothing secret appears here or in the task definition.

  HARD STOP: the archive is for the 2026 season study. After END_DATE this script refuses to
  run and logs the refusal, independently of the Task Scheduler EndBoundary — two independent
  stops, so a scheduler misconfiguration cannot keep it capturing forever.
#>
$ErrorActionPreference = 'Continue'

$END_DATE = [datetime]::ParseExact('2027-02-15', 'yyyy-MM-dd', $null)   # last day allowed
$SEASON   = 2026

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Arch = Join-Path $Here 'market_snapshots'
$Logs = Join-Path $Arch '_task_logs'
$Ledger = Join-Path $Arch 'task_runs.jsonl'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

$nowUtc = (Get-Date).ToUniversalTime()
$ts     = $nowUtc.ToString('yyyy-MM-ddTHHmmssZ')
$log    = Join-Path $Logs "$ts.log"

function Write-Log([string]$text) {
    # Tee-Object / Out-File in Windows PowerShell 5.1 emit UTF-16, which makes the run log
    # awkward to grep and parse. Append BOM-less UTF-8 explicitly, and echo to the console so
    # the Task Scheduler transcript still shows it.
    Write-Host $text
    [System.IO.File]::AppendAllText($log, $text + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
}

function Write-Ledger([string]$status, [int]$code, [string]$diag, [string]$py) {
    $row = [ordered]@{
        run_utc     = $nowUtc.ToString('yyyy-MM-ddTHH:mm:ssZ')
        run_local   = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
        season      = $SEASON
        status      = $status
        exit_code   = $code
        interpreter = $py
        log_file    = "_task_logs/$ts.log"
        diagnostic  = $diag
        host        = $env:COMPUTERNAME
    }
    # Windows PowerShell 5.1's -Encoding UTF8 emits a BOM, which makes the ledger fail a
    # plain json.loads per line. Append via .NET with an explicit BOM-less UTF8 encoder.
    $line = ($row | ConvertTo-Json -Compress) + "`r`n"
    [System.IO.File]::AppendAllText($Ledger, $line, (New-Object System.Text.UTF8Encoding($false)))
}

# --- hard stop after the study window -------------------------------------------------
if ((Get-Date).Date -gt $END_DATE.Date) {
    $msg = "refused: past END_DATE $($END_DATE.ToString('yyyy-MM-dd')); 2026 capture window closed"
    Write-Log $msg
    Write-Ledger 'refused' 0 $msg ''
    exit 0
}

# --- resolve a stable interpreter -----------------------------------------------------
$py = $env:JOSCHO_CAPTURE_PY
if (-not $py -or -not (Test-Path $py)) {
    $venv = 'C:\Users\josep\Desktop\random_stuff\cowork_OS\AI_hedge_fund\.venv\Scripts\python.exe'
    $py = if (Test-Path $venv) { $venv } else { 'python' }
}
$script = Join-Path $Here 'capture_market_snapshot.py'
if (-not (Test-Path $script)) {
    $msg = "capture script not found: $script"
    Write-Log $msg
    Write-Ledger 'failed' 1 $msg $py
    exit 1
}

Write-Log "[$ts] interpreter: $py"
Write-Log "[$ts] script     : $script"
Write-Log "[$ts] archive    : $Arch"

# --- run the capture -------------------------------------------------------------------
try {
    & $py $script --season $SEASON *>&1 | ForEach-Object { Write-Log ($_ | Out-String).TrimEnd() }
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
} catch {
    Write-Log ($_ | Out-String)
    Write-Ledger 'failed' 1 "launch error: $($_.Exception.Message)" $py
    exit 1
}

if ($code -eq 0) {
    Write-Ledger 'success' 0 'capture ok' $py
} else {
    Write-Ledger 'failed' $code "capture exited $code (see manifest/failures.jsonl for detail)" $py
}
exit $code
