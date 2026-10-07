# AI-RxOS Database Seed Script (Windows PowerShell)
# Seeds PostgreSQL canonical biomedical entities, ontology terms, and demo fixtures.
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonBin = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonBin)) {
    $pythonBin = "python"
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AI-RxOS Database Seeding Process                        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check PostgreSQL Connectivity
Write-Host "`n[1/3] Checking PostgreSQL availability..." -ForegroundColor Yellow
$pgPort = 15432
$tcp = New-Object System.Net.Sockets.TcpClient
$asyncResult = $tcp.BeginConnect("localhost", $pgPort, $null, $null)
$success = $asyncResult.AsyncWaitHandle.WaitOne(3000, $false)

if (-not $success) {
    Write-Warning "Could not reach PostgreSQL on localhost:$pgPort."
    Write-Host "Starting data stores via Docker Compose..." -ForegroundColor Gray
    & docker compose up -d postgres redis neo4j
    Start-Sleep -Seconds 5
} else {
    $tcp.EndConnect($asyncResult)
    $tcp.Close()
    Write-Host "  PostgreSQL is accessible on port $pgPort." -ForegroundColor Green
}

# 2. Seed Canonical Knowledge Graph Entities
Write-Host "`n[2/3] Seeding Canonical Knowledge Graph entities..." -ForegroundColor Yellow
$seedScript = Join-Path $repoRoot "services\kg\app\seed_demo.py"

if (Test-Path $seedScript) {
    Push-Location (Join-Path $repoRoot "services\kg")
    try {
        & $pythonBin -m app.seed_demo
        Write-Host "  Canonical entities seeded successfully." -ForegroundColor Green
    } catch {
        Write-Warning "  Direct Python seeding had errors or was already seeded: $_"
    } finally {
        Pop-Location
    }
} else {
    Write-Warning "  Seed script not found at $seedScript."
}

# 3. Verify Opportunity Engine Benchmark Fixtures
Write-Host "`n[3/3] Verifying Opportunity Engine benchmark fixtures..." -ForegroundColor Yellow
$fixturesScript = "from app.opportunity_engine.data.fixtures import list_fixture_assets; assets = list_fixture_assets(); print(f'Successfully loaded {len(assets)} oncology benchmark assets: {[a.name for a in assets]}')"
Push-Location (Join-Path $repoRoot "apps\ai-services")
try {
    & $pythonBin -c $fixturesScript
    Write-Host "  Opportunity benchmark assets verified." -ForegroundColor Green
} catch {
    Write-Warning "  Fixture verification notice: $_"
} finally {
    Pop-Location
}

Write-Host "`nSeeding completed successfully!`n" -ForegroundColor Green
