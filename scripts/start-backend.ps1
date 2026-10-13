#Requires -Version 5.1
<#
.SYNOPSIS
    AI Knowledge Agent — Backend Startup Script (no Docker required)

.DESCRIPTION
    1. Checks if PostgreSQL is running locally.
    2. Checks if Qdrant is available at localhost:6333; offers to download the
       standalone Windows binary if not found.
    3. Checks Redis availability; suggests Memurai for Windows.
    4. Loads .env and launches FastAPI via uvicorn.

.EXAMPLE
    .\scripts\start-backend.ps1
    .\scripts\start-backend.ps1 -SkipChecks
#>

param(
    [switch]$SkipChecks,
    [string]$EnvFile = ".\.env",
    [int]    $BackendPort = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─── Color helpers ────────────────────────────────────────────────────────────
function Write-Header  { param($msg) Write-Host "`n━━━  $msg  ━━━" -ForegroundColor Cyan   }
function Write-Ok      { param($msg) Write-Host "  [✓] $msg"       -ForegroundColor Green  }
function Write-Warn    { param($msg) Write-Host "  [!] $msg"       -ForegroundColor Yellow }
function Write-Err     { param($msg) Write-Host "  [✗] $msg"       -ForegroundColor Red    }
function Write-Info    { param($msg) Write-Host "  [i] $msg"       -ForegroundColor Gray   }

# ─── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════╗" -ForegroundColor DarkCyan
Write-Host "║   AI Knowledge Agent — Backend Startup                ║" -ForegroundColor DarkCyan
Write-Host "╚═══════════════════════════════════════════════════════╝" -ForegroundColor DarkCyan

$summaryOk   = [System.Collections.Generic.List[string]]::new()
$summaryWarn = [System.Collections.Generic.List[string]]::new()
$summaryErr  = [System.Collections.Generic.List[string]]::new()

# ─── Resolve project root (script lives in <root>/scripts/) ──────────────────
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
Write-Info "Project root: $projectRoot"

# ─── Load .env for informational display ─────────────────────────────────────
$envPath = Join-Path $projectRoot ".env"
if (Test-Path $envPath) {
    Write-Ok ".env file found at $envPath"
    $summaryOk.Add(".env loaded") | Out-Null
} else {
    Write-Warn ".env not found — copy .env.example and fill in secrets before starting!"
    $summaryWarn.Add(".env missing — backend may fail to start") | Out-Null
}

if ($SkipChecks) {
    Write-Warn "Dependency checks skipped (-SkipChecks flag)."
} else {

    # ── 1. PostgreSQL ─────────────────────────────────────────────────────────
    Write-Header "PostgreSQL"

    $pgRunning = $false

    # Check if the pg service is running
    $pgService = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue |
                 Where-Object { $_.Status -eq "Running" } |
                 Select-Object -First 1

    if ($pgService) {
        Write-Ok "PostgreSQL service running: $($pgService.Name)"
        $pgRunning = $true
        $summaryOk.Add("PostgreSQL service: $($pgService.Name)") | Out-Null
    } else {
        # Try a TCP probe on 5432
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", 5432)
            $tcp.Close()
            Write-Ok "PostgreSQL is accepting connections on port 5432"
            $pgRunning = $true
            $summaryOk.Add("PostgreSQL: port 5432 open") | Out-Null
        } catch {
            $pgRunning = $false
        }
    }

    if (-not $pgRunning) {
        Write-Err "PostgreSQL is NOT running."
        Write-Warn "To start PostgreSQL locally, choose one of:"
        Write-Host ""
        Write-Host "  Option A — Windows Service (if installed via https://www.postgresql.org/download/windows/):"
        Write-Host '    Start-Service postgresql*' -ForegroundColor White
        Write-Host ""
        Write-Host "  Option B — Scoop:"
        Write-Host '    scoop install postgresql' -ForegroundColor White
        Write-Host '    pg_ctl start -D "$env:USERPROFILE\scoop\apps\postgresql\current\data"' -ForegroundColor White
        Write-Host ""
        Write-Host "  Option C — EDB Installer (GUI):"
        Write-Host "    https://www.enterprisedb.com/downloads/postgres-postgresql-downloads" -ForegroundColor White
        Write-Host ""
        Write-Host "  After starting PostgreSQL, create the database:"
        Write-Host '    createdb -U postgres ai_knowledge_agent' -ForegroundColor White
        Write-Host ""
        $summaryErr.Add("PostgreSQL NOT running — backend will fail to start") | Out-Null
    }

    # ── 2. Qdrant ─────────────────────────────────────────────────────────────
    Write-Header "Qdrant Vector Database (localhost:6333)"

    $qdrantOk = $false
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:6333/healthz" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            Write-Ok "Qdrant is healthy at http://localhost:6333"
            $qdrantOk = $true
            $summaryOk.Add("Qdrant: healthy") | Out-Null
        }
    } catch {
        $qdrantOk = $false
    }

    if (-not $qdrantOk) {
        Write-Warn "Qdrant is NOT running at localhost:6333."
        Write-Host ""
        Write-Host "  To download and run Qdrant standalone for Windows:" -ForegroundColor Yellow
        Write-Host ""

        # Fetch latest release tag from GitHub
        $qdrantVersion = "v1.13.6"   # fallback pinned version
        try {
            $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/qdrant/qdrant/releases/latest" -TimeoutSec 5
            $qdrantVersion = $rel.tag_name
        } catch { <# use fallback #> }

        $qdrantExe = "qdrant-$qdrantVersion-x86_64-pc-windows-msvc.zip"
        $qdrantUrl = "https://github.com/qdrant/qdrant/releases/download/$qdrantVersion/$qdrantExe"

        Write-Host "  Step 1 — Download:" -ForegroundColor Cyan
        Write-Host "    curl.exe -L -o qdrant.zip `"$qdrantUrl`"" -ForegroundColor White
        Write-Host ""
        Write-Host "  Step 2 — Extract:" -ForegroundColor Cyan
        Write-Host '    Expand-Archive -Path qdrant.zip -DestinationPath .\qdrant-bin -Force' -ForegroundColor White
        Write-Host ""
        Write-Host "  Step 3 — Run:" -ForegroundColor Cyan
        Write-Host '    .\qdrant-bin\qdrant.exe' -ForegroundColor White
        Write-Host ""

        $choice = Read-Host "  Would you like to download and start Qdrant now? [y/N]"
        if ($choice -match "^[Yy]") {
            $qdrantDir = Join-Path $projectRoot "qdrant-bin"
            $qdrantBin = Join-Path $qdrantDir "qdrant.exe"

            if (-not (Test-Path $qdrantBin)) {
                Write-Info "Downloading Qdrant $qdrantVersion ..."
                $zipPath = Join-Path $env:TEMP "qdrant.zip"
                try {
                    curl.exe -L -o $zipPath $qdrantUrl
                    Write-Info "Extracting ..."
                    Expand-Archive -Path $zipPath -DestinationPath $qdrantDir -Force
                    Remove-Item $zipPath -Force
                    Write-Ok "Qdrant extracted to $qdrantDir"
                } catch {
                    Write-Err "Download failed: $_"
                    Write-Warn "Please download manually from: $qdrantUrl"
                }
            }

            if (Test-Path $qdrantBin) {
                Write-Info "Launching Qdrant in a new PowerShell window ..."
                Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", "& '$qdrantBin'" -WindowStyle Normal
                Start-Sleep -Seconds 3

                # Verify it started
                try {
                    $r2 = Invoke-WebRequest -Uri "http://localhost:6333/healthz" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
                    if ($r2.StatusCode -eq 200) {
                        Write-Ok "Qdrant started successfully!"
                        $qdrantOk = $true
                        $summaryOk.Add("Qdrant: started from $qdrantBin") | Out-Null
                    }
                } catch {
                    Write-Warn "Qdrant may still be initializing — check the Qdrant window."
                }
            }
        }

        if (-not $qdrantOk) {
            $summaryWarn.Add("Qdrant NOT running — vector search will fail") | Out-Null
        }
    }

    # ── 3. Redis ──────────────────────────────────────────────────────────────
    Write-Header "Redis (optional)"

    $redisOk = $false
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", 6379)
        $tcp.Close()
        Write-Ok "Redis is accepting connections on port 6379"
        $redisOk = $true
        $summaryOk.Add("Redis: port 6379 open") | Out-Null
    } catch {
        $redisOk = $false
    }

    if (-not $redisOk) {
        Write-Warn "Redis is NOT running on port 6379."
        Write-Info "Redis is optional — when REDIS_URL is not set in .env, the backend"
        Write-Info "automatically falls back to an in-process async task worker."
        Write-Host ""
        Write-Host "  If you need Redis (for distributed Celery workers), install Memurai:" -ForegroundColor Yellow
        Write-Host "    https://www.memurai.com/get-memurai  (Redis-compatible for Windows)" -ForegroundColor White
        Write-Host ""
        Write-Host "  Or use WSL2 + Redis:"
        Write-Host '    wsl --install' -ForegroundColor White
        Write-Host '    wsl sudo apt install redis-server && wsl sudo service redis start' -ForegroundColor White
        Write-Host ""
        $summaryWarn.Add("Redis NOT running — in-process async worker will be used (REDIS_URL unset)") | Out-Null
    }

} # end -not $SkipChecks

# ─── Activate virtual environment (if present) ─────────────────────────────
Write-Header "Python Environment"

$venvPaths = @(
    Join-Path $projectRoot ".venv\Scripts\Activate.ps1"
    Join-Path $projectRoot "venv\Scripts\Activate.ps1"
    Join-Path $projectRoot "env\Scripts\Activate.ps1"
)

$venvActivated = $false
foreach ($venv in $venvPaths) {
    if (Test-Path $venv) {
        Write-Info "Activating virtual environment: $venv"
        & $venv
        $venvActivated = $true
        break
    }
}

if (-not $venvActivated) {
    Write-Warn "No .venv / venv / env directory found — using system Python."
    Write-Info "Tip: python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r requirements.txt"
}

# Verify uvicorn is available
$uvicorn = Get-Command uvicorn -ErrorAction SilentlyContinue
if ($uvicorn) {
    Write-Ok "uvicorn found: $($uvicorn.Source)"
    $summaryOk.Add("uvicorn: $($uvicorn.Source)") | Out-Null
} else {
    Write-Err "uvicorn not found in PATH — install with: pip install uvicorn[standard]"
    $summaryErr.Add("uvicorn not found — install requirements first") | Out-Null
}

# ─── Summary ─────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════╗" -ForegroundColor DarkCyan
Write-Host "║   Startup Summary                                     ║" -ForegroundColor DarkCyan
Write-Host "╚═══════════════════════════════════════════════════════╝" -ForegroundColor DarkCyan

foreach ($s in $summaryOk)   { Write-Ok   $s }
foreach ($s in $summaryWarn) { Write-Warn $s }
foreach ($s in $summaryErr)  { Write-Err  $s }

if ($summaryErr.Count -gt 0) {
    Write-Host ""
    Write-Err "One or more critical dependencies are missing. Resolve them before launching."
    $choice = Read-Host "  Launch FastAPI anyway? [y/N]"
    if ($choice -notmatch "^[Yy]") {
        Write-Host "  Aborted." -ForegroundColor Red
        exit 1
    }
}

# ─── Launch FastAPI ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════════╗" -ForegroundColor DarkGreen
Write-Host "║   Launching FastAPI on http://0.0.0.0:$BackendPort           ║" -ForegroundColor DarkGreen
Write-Host "╚═══════════════════════════════════════════════════════╝" -ForegroundColor DarkGreen
Write-Host ""
Write-Info "Docs:   http://localhost:$BackendPort/docs"
Write-Info "Health: http://localhost:$BackendPort/health"
Write-Info "Status: http://localhost:$BackendPort/api/v1/status"
Write-Host ""

# Pass .env to uvicorn via the process environment (pydantic-settings auto-discovers it)
$env:ENV_FILE = $envPath

uvicorn backend.main:app `
    --host 0.0.0.0 `
    --port $BackendPort `
    --reload `
    --reload-dir backend

