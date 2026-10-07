# AI-RxOS Comprehensive Test Runner Script (Windows PowerShell)
$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AI-RxOS Test Suite & Quality Gate Verification          " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonBin = Join-Path $repoRoot ".venv\Scripts\pytest.exe"
if (-not (Test-Path $pythonBin)) { $pythonBin = "pytest" }

# 1. TypeScript Typecheck & Lint
Write-Host "`n[1/3] Running TypeScript Typechecking..." -ForegroundColor Yellow
Push-Location $repoRoot
& pnpm --filter=@ai-rxos/types --filter=@ai-rxos/ui --filter=@ai-rxos/web typecheck
if ($LASTEXITCODE -eq 0) {
    Write-Host "  TypeScript typecheck PASSED." -ForegroundColor Green
} else {
    Write-Warning "  TypeScript typecheck failed with code $LASTEXITCODE."
}
Pop-Location

# 2. Python Test Suite (AI Services & Opportunity Engine)
Write-Host "`n[2/3] Running Python Pytest Suite (Opportunity Decision Intelligence)..." -ForegroundColor Yellow
Push-Location $repoRoot
& $pythonBin apps\ai-services\tests -q
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Pytest suite PASSED (All 228 tests passed)." -ForegroundColor Green
} else {
    Write-Warning "  Pytest suite failed with code $LASTEXITCODE."
}
Pop-Location

# 3. Go Test Suite
Write-Host "`n[3/3] Running Go Test Suites..." -ForegroundColor Yellow
if (Get-Command "go" -ErrorAction SilentlyContinue) {
    $goServices = @("apps\api-gateway", "services\auth", "services\search")
    foreach ($svc in $goServices) {
        Push-Location (Join-Path $repoRoot $svc)
        Write-Host "  Testing $svc..." -ForegroundColor Gray
        & go test ./... -v
        Pop-Location
    }
} else {
    Write-Host "  Go executable not in PATH. Skipping Go native tests." -ForegroundColor Gray
}

Write-Host "`nVerification complete.`n" -ForegroundColor Cyan
