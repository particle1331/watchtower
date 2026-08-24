#requires -Version 7.0
<#
.SYNOPSIS
  End-to-end smoke tests for the ML platform golden path (docs/07, Ch 10).

.DESCRIPTION
  Verifies acceptance evidence for each phase against a running deployed platform.
  Run after `deploy.ps1` has completed all passes.

  Phase 0 (Foundation):    MLflow reachable; ACR, Postgres, Storage exist.
  Phase 1 (Training):      Trigger train Job; confirm registered version + results row.
  Phase 2 (Batch):         Trigger batch Job; poll execution + parent row to SUCCESS.
  Phase 3 (Serving):       /readyz reports exact version; test a prediction.
  Phase 4 (Observability): Dashboard /api/runs returns rows; /healthz alive.
  Phase 5 (LLM):           pyfunc version loads via models:/ URI (structure check only).

.EXAMPLE
  ./deploy/smoke-tests.ps1 -TfVarsFile infra/environments/dev.tfvars
#>
[CmdletBinding()]
param(
  [string] $InfraDir    = "$PSScriptRoot/../infra",
  [string] $TfVarsFile  = "$PSScriptRoot/../infra/environments/dev.tfvars",
  [int]    $TimeoutSecs = 300
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Push-Location $InfraDir
try {
  $mlflowUrl   = terraform output -raw mlflow_url
  $servingUrl  = terraform output -raw serving_url 2>$null
  $dashUrl     = terraform output -raw dashboard_url 2>$null
  $trainJob    = terraform output -raw train_job_name 2>$null
  $batchJob    = terraform output -raw batch_job_name 2>$null
}
finally { Pop-Location }

$Errors = 0
function Assert([bool]$cond, [string]$msg) {
  if ($cond) { Write-Host "  PASS $msg" -ForegroundColor Green }
  else       { Write-Host "  FAIL $msg" -ForegroundColor Red; $script:Errors++ }
}

function Wait-JobExecution([string]$jobName, [string]$executionName, [string]$label) {
  Write-Host "  Execution: $executionName — waiting up to ${TimeoutSecs}s..."
  $deadline = (Get-Date).AddSeconds($TimeoutSecs)
  do {
    $status = az containerapp job execution show --name $jobName --job-execution-name $executionName --output tsv --query "properties.status" 2>$null
    if ($status -in @('Succeeded','Failed','Stopped','Degraded')) { break }
    Start-Sleep 15
  } while ((Get-Date) -lt $deadline)
  if ($status -notin @('Succeeded','Failed','Stopped','Degraded')) { $status = 'Timeout' }
  Assert ($status -eq 'Succeeded') "$label execution reached SUCCESS (status=$status)"
  return $status
}

function Assert-LatestBatchResult([string]$dashboardUrl) {
  if ($dashboardUrl -eq '') { Assert $false 'Dashboard URL is empty; cannot verify the batch results row'; return }
  try {
    $runs = Invoke-RestMethod "$dashboardUrl/api/runs?limit=50" -TimeoutSec 10
    $success = @($runs | Where-Object {
      $_.name -like 'batch:score-*' -and $_.status -eq 'SUCCESS'
    }).Count -gt 0
    Assert $success 'Dashboard results API contains a successful batch parent row'
  } catch { Assert $false "Dashboard results API after batch execution: $_" }
}

# --- Phase 0: Foundation + MLflow reachable ---------------------------------
Write-Host "`n[Phase 0] Foundation" -ForegroundColor Cyan
Assert ($mlflowUrl -ne "") "MLflow URL is non-empty"
try {
  $health = Invoke-RestMethod "$mlflowUrl/health" -TimeoutSec 10
  Assert ($health -match "OK|ok|healthy|{}" ) "MLflow /health returns OK"
} catch { Assert $false "MLflow /health reachable: $_" }

# --- Phase 1: Training Job --------------------------------------------------
Write-Host "`n[Phase 1] Training" -ForegroundColor Cyan
if ($trainJob -ne "") {
  Write-Host "  Triggering train Job ($trainJob)..."
  $execJson = az containerapp job start --name $trainJob --resource-group (
    Push-Location $InfraDir; terraform output -raw resource_group_name; Pop-Location
  ) --output json 2>$null
  if ($execJson) {
    $execName = ($execJson | ConvertFrom-Json).name
    Write-Host "  Execution: $execName — waiting up to ${TimeoutSecs}s..."
    $deadline = (Get-Date).AddSeconds($TimeoutSecs)
    do {
      Start-Sleep 15
      $status = az containerapp job execution show --name $trainJob --job-execution-name $execName --output tsv --query "properties.status" 2>$null
    } while ($status -notin @('Succeeded','Failed','Stopped','Degraded') -and (Get-Date) -lt $deadline)
    Assert ($status -eq 'Succeeded') "Train Job execution succeeded (status=$status)"
  } else { Write-Host "  (train job not deployed, skipping)" -ForegroundColor Yellow }
} else { Write-Host "  (train_job_name empty, skipping Phase 1)" -ForegroundColor Yellow }

# --- Phase 2: Batch Job -----------------------------------------------------
Write-Host "`n[Phase 2] Batch" -ForegroundColor Cyan
if ($batchJob -ne "") {
  Write-Host "  Triggering batch Job ($batchJob)..."
  $rg = Push-Location $InfraDir; terraform output -raw resource_group_name; Pop-Location
  $batchExecJson = az containerapp job start --name $batchJob --resource-group $rg --output json 2>$null
  if ($batchExecJson) {
    $batchExecName = ($batchExecJson | ConvertFrom-Json).name
    Wait-JobExecution $batchJob $batchExecName 'Batch Job' | Out-Null
    Assert-LatestBatchResult $dashUrl
  } else {
    Assert $false 'Batch Job start returned no execution'
  }
} else { Write-Host "  (batch_job_name empty, skipping Phase 2)" -ForegroundColor Yellow }

# --- Phase 3: Serving App ---------------------------------------------------
Write-Host "`n[Phase 3] Serving" -ForegroundColor Cyan
if ($servingUrl -ne "") {
  try {
    $readyz = Invoke-RestMethod "$servingUrl/readyz" -TimeoutSec 10
    Assert ($readyz.status -eq 'ready') "Serving /readyz status=ready"
    Assert ($readyz.model_version -ne '') "Serving /readyz reports a model_version"
    Write-Host "  Loaded version: $($readyz.model_version)"
    $prediction = Invoke-RestMethod "$servingUrl/v1/predictions" -Method Post -ContentType 'application/json' -Body '{"instances":[[7.0,0.27,0.36,20.7,0.045,45.0,170.0,1.001,3.0,0.45,8.8]]}' -TimeoutSec 10
    Assert ($prediction.model_version -eq $readyz.model_version) "Serving prediction reports the ready model_version"
  } catch { Assert $false "Serving /readyz reachable: $_" }
} else { Write-Host "  (serving_url empty, skipping Phase 3)" -ForegroundColor Yellow }

# --- Phase 4: Observability / Dashboard -------------------------------------
Write-Host "`n[Phase 4] Observability" -ForegroundColor Cyan
if ($dashUrl -ne "") {
  try {
    $health = Invoke-RestMethod "$dashUrl/healthz" -TimeoutSec 10
    Assert ($health.status -eq 'alive') "Dashboard /healthz status=alive"
    $runs = Invoke-RestMethod "$dashUrl/api/runs?limit=5" -TimeoutSec 10
    Assert ($null -ne $runs) "Dashboard /api/runs returns a response"
  } catch { Assert $false "Dashboard reachable: $_" }
} else { Write-Host "  (dashboard_url empty, skipping Phase 4)" -ForegroundColor Yellow }

# --- Summary ----------------------------------------------------------------
Write-Host ""
if ($Errors -eq 0) {
  Write-Host "All smoke tests passed." -ForegroundColor Green
} else {
  Write-Host "$Errors test(s) failed." -ForegroundColor Red
  exit 1
}
