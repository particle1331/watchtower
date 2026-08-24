#requires -Version 7.0
<#
.SYNOPSIS
  Full platform deploy — all phases (docs/01–docs/06, Ch 02–Ch 06).

.DESCRIPTION
  Multi-pass deploy that brings up the whole platform incrementally:
    1. terraform apply — foundation only (ACR, Postgres, storage, identities)
    2. Build + push MLflow image; run grants.sql + schema.sql; apply MLflow pass
    3. Build + push train/batch/serving/dashboard images
    4. terraform apply — all images pinned; full platform running
    5. (Optional) run smoke-tests.ps1 to verify acceptance evidence

  Images with empty vars skip the corresponding module (two-pass gating).
  Auth is managed-identity / Entra throughout; no passwords in this script.
  Requires: az CLI (logged in), terraform >= 1.6, psql, Docker (or az acr build).

.EXAMPLE
  ./deploy/deploy.ps1 -TfVars infra/environments/dev.tfvars -PgAdminUpn you@example.com
#>
[CmdletBinding()]
param(
  [string] $InfraDir         = "$PSScriptRoot/../infra",
  [string] $TfVars           = "$PSScriptRoot/../infra/environments/dev.tfvars",
  [Parameter(Mandatory)] [string] $PgAdminUpn,
  [string] $MlflowImageRepo  = "mlflow-app",
  [string] $TrainImageRepo   = "train-job",
  [string] $BatchImageRepo   = "batch-job",
  [string] $ServingImageRepo = "serving-app",
  [string] $DashImageRepo    = "dashboard",
  [string] $ServingModelName    = "wine-quality",
  [string] $ServingModelVersion = "",
  [string] $LlmEvalDataset       = "",
  [string] $LlmModelName         = "llm-app",
  [string] $LlmModelVersion      = "1",
  [switch] $SkipSmokeTests
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Build-And-Push {
  param([string]$AcrName, [string]$AcrLogin, [string]$Repo, [string]$SrcDir)
  $tag = "$Repo:latest"
  Write-Host "    building $tag from $SrcDir"
  az acr build --registry $AcrName --image $tag $SrcDir | Out-Host
  $digest = az acr repository show --name $AcrName --image $tag --query "digest" -o tsv
  return "$AcrLogin/${Repo}@${digest}"
}

Push-Location $InfraDir
try {
  # -----------------------------------------------------------------------
  # Pass 1: foundation only
  # -----------------------------------------------------------------------
  Write-Host "==> [1/4] terraform init + foundation apply" -ForegroundColor Cyan
  terraform init -input=false
  terraform apply -input=false -auto-approve -var-file $TfVars `
    -var 'mlflow_image=' -var 'train_image=' -var 'batch_image=' `
    -var 'serving_image=' -var 'dashboard_image=' -var 'llm_image='

  $acrName  = terraform output -raw acr_name
  $acrLogin = terraform output -raw acr_login_server
  $pgFqdn   = terraform output -raw postgres_fqdn

  # -----------------------------------------------------------------------
  # Pass 2: MLflow image + DB setup
  # -----------------------------------------------------------------------
  Write-Host "==> [2/4] build + push MLflow image; run grants.sql + schema.sql" -ForegroundColor Cyan
  $mlflowImage = Build-And-Push $acrName $acrLogin $MlflowImageRepo "$PSScriptRoot/../src/mlflow_app"
  Write-Host "    MLflow pinned: $mlflowImage"

  $pgToken = az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv
  $env:PGPASSWORD = $pgToken
  $oidMap = terraform output -json identity_principal_ids | ConvertFrom-Json

  # grants.sql — create principals and schema privileges. Re-run after
  # schema.sql so workload table grants include newly-created tables.
  psql "host=$pgFqdn port=5432 dbname=postgres user=$PgAdminUpn sslmode=require" `
    -v oid_jobs_train=$($oidMap.'id-jobs-train') `
    -v oid_jobs_batch=$($oidMap.'id-jobs-batch') `
    -v oid_mlflow=$($oidMap.'id-mlflow') `
    -v oid_dashboard=$($oidMap.'id-dashboard') `
    -f grants.sql

  # schema.sql — results table DDL (idempotent IF NOT EXISTS)
  $schemaPath = "$PSScriptRoot/../src/ml_platform/results/schema.sql"
  if (Test-Path $schemaPath) {
    psql "host=$pgFqdn port=5432 dbname=results user=$PgAdminUpn sslmode=require" -f $schemaPath
    psql "host=$pgFqdn port=5432 dbname=postgres user=$PgAdminUpn sslmode=require" `
      -v oid_jobs_train=$($oidMap.'id-jobs-train') `
      -v oid_jobs_batch=$($oidMap.'id-jobs-batch') `
      -v oid_mlflow=$($oidMap.'id-mlflow') `
      -v oid_dashboard=$($oidMap.'id-dashboard') `
      -f grants.sql
  }
  Remove-Item Env:PGPASSWORD

  # Apply with MLflow image so the App goes live.
  terraform apply -input=false -auto-approve -var-file $TfVars `
    -var "mlflow_image=$mlflowImage" -var 'train_image=' -var 'batch_image=' `
    -var 'serving_image=' -var 'dashboard_image=' -var 'llm_image='

  # -----------------------------------------------------------------------
  # Pass 3: build remaining images in parallel (sequential here for clarity)
  # -----------------------------------------------------------------------
  Write-Host "==> [3/4] build + push train / batch / serving / dashboard images" -ForegroundColor Cyan
  $trainImage   = Build-And-Push $acrName $acrLogin $TrainImageRepo   "$PSScriptRoot/.."
  $batchImage   = Build-And-Push $acrName $acrLogin $BatchImageRepo   "$PSScriptRoot/.."
  $servingImage = Build-And-Push $acrName $acrLogin $ServingImageRepo "$PSScriptRoot/.."
  $dashImage    = Build-And-Push $acrName $acrLogin $DashImageRepo    "$PSScriptRoot/.."
  Write-Host "    train:   $trainImage"
  Write-Host "    batch:   $batchImage"
  Write-Host "    serving: $servingImage"
  Write-Host "    dash:    $dashImage"

  # -----------------------------------------------------------------------
  # Pass 4: apply with all images pinned
  # -----------------------------------------------------------------------
  Write-Host "==> [4/4] terraform apply — full platform" -ForegroundColor Cyan
  $servVars = if ($ServingModelVersion -ne "") {
    "-var `"serving_model_version=$ServingModelVersion`" -var `"serving_model_name=$ServingModelName`""
  } else { "" }

  $cmd = "terraform apply -input=false -auto-approve -var-file $TfVars " +
    "-var `"mlflow_image=$mlflowImage`" -var `"train_image=$trainImage`" " +
    "-var `"batch_image=$batchImage`" -var `"serving_image=$servingImage`" " +
    "-var `"dashboard_image=$dashImage`" -var `"llm_image=$trainImage`" " +
    "-var `"llm_eval_dataset=$LlmEvalDataset`" -var `"llm_model_name=$LlmModelName`" " +
    "-var `"llm_model_version=$LlmModelVersion`" $servVars"
  Invoke-Expression $cmd

  Write-Host "`nDone. Endpoints:" -ForegroundColor Green
  terraform output

  # -----------------------------------------------------------------------
  # Optional smoke tests
  # -----------------------------------------------------------------------
  if (-not $SkipSmokeTests) {
    Write-Host "`n==> Running smoke tests..." -ForegroundColor Cyan
    & "$PSScriptRoot/smoke-tests.ps1" -TfVarsFile $TfVars
  }
}
finally {
  Pop-Location
}
