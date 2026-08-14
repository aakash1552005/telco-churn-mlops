# ==============================================================================
# Phase 12 - AWS ECR Repository Provisioning
# infra/aws/create_ecr_repo.ps1
#
# PURPOSE : Idempotently create the telco-churn-api ECR repository.
# IDEMPOTENT: Checks for existence first - no exception-based control flow.
# REGION CHECK: Aborts with a clear message if the region is wrong.
#
# USAGE:
#   .\infra\aws\create_ecr_repo.ps1
# ==============================================================================

# "Continue" is correct here: every native command is already guarded by an
# explicit $LASTEXITCODE check, so Stop adds no safety — but it does cause
# PS5.1 to abort on stderr from aws.exe before the $LASTEXITCODE check runs.
$ErrorActionPreference = "Continue"

$REQUIRED_REGION   = "ap-south-1"
$REPOSITORY_NAME   = "telco-churn-api"

# ------------------------------------------------------------------------------
# Step 1: Verify the configured AWS region
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [1/3] Verifying configured AWS region..." -ForegroundColor Cyan

$configuredRegion = aws configure get region 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($configuredRegion)) {
    Write-Host ""
    Write-Host "ERROR: Could not determine the configured AWS region." -ForegroundColor Red
    Write-Host "       Run 'aws configure' and set the region to '$REQUIRED_REGION'." -ForegroundColor Red
    exit 1
}

$configuredRegion = $configuredRegion.Trim()

if ($configuredRegion -ne $REQUIRED_REGION) {
    Write-Host ""
    Write-Host "ERROR: AWS CLI is configured for region '$configuredRegion'," -ForegroundColor Red
    Write-Host "       but this project requires region '$REQUIRED_REGION'." -ForegroundColor Red
    Write-Host "       Run 'aws configure' and set Default region name to '$REQUIRED_REGION'." -ForegroundColor Red
    exit 1
}

Write-Host "       Region OK: $configuredRegion" -ForegroundColor Green

# ------------------------------------------------------------------------------
# Step 2: Check whether the repository already exists (idempotent guard)
# No exception-based control flow - we inspect $LASTEXITCODE only.
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [2/3] Checking if repository '$REPOSITORY_NAME' already exists..." -ForegroundColor Cyan

# 2>$null: a non-zero exit here is the *expected* signal that the repo
# doesn't exist yet.  We only use $describeOutput when exit code is 0,
# so swallowing the stderr "RepositoryNotFoundException" is intentional.
$describeOutput = aws ecr describe-repositories `
    --repository-names $REPOSITORY_NAME `
    --region $REQUIRED_REGION 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Repository already exists - nothing to do." -ForegroundColor Green
    Write-Host ""
    $repoJson = $describeOutput | ConvertFrom-Json
    $repoUri  = $repoJson.repositories[0].repositoryUri
    Write-Host "  Repository URI : $repoUri" -ForegroundColor White
    Write-Host "  Region         : $REQUIRED_REGION" -ForegroundColor White
    Write-Host ""
    exit 0
}

# ------------------------------------------------------------------------------
# Step 3: Repository does not exist - create it
# ------------------------------------------------------------------------------
Write-Host "       Repository not found. Creating it now..." -ForegroundColor Yellow
Write-Host ""
Write-Host "==> [3/3] Creating ECR repository '$REPOSITORY_NAME'..." -ForegroundColor Cyan

$createOutput = aws ecr create-repository `
    --repository-name $REPOSITORY_NAME `
    --region $REQUIRED_REGION `
    --image-scanning-configuration scanOnPush=true `
    --encryption-configuration encryptionType=AES256 `
    --output json 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Failed to create ECR repository '$REPOSITORY_NAME'." -ForegroundColor Red
    Write-Host "       AWS CLI output:" -ForegroundColor Red
    Write-Host $createOutput -ForegroundColor Red
    exit 1
}

$repoJson = $createOutput | ConvertFrom-Json
$repoUri  = $repoJson.repository.repositoryUri
$repoArn  = $repoJson.repository.repositoryArn

Write-Host ""
Write-Host "Repository created successfully." -ForegroundColor Green
Write-Host ""
Write-Host "  Repository Name : $REPOSITORY_NAME"  -ForegroundColor White
Write-Host "  Repository URI  : $repoUri"           -ForegroundColor White
Write-Host "  Repository ARN  : $repoArn"           -ForegroundColor White
Write-Host "  Region          : $REQUIRED_REGION"   -ForegroundColor White
Write-Host "  Scan on Push    : ENABLED"            -ForegroundColor White
Write-Host "  Encryption      : AES256"             -ForegroundColor White
Write-Host ""
Write-Host "Done. Run .\infra\aws\push_to_ecr.ps1 to tag and push the Docker image." -ForegroundColor Cyan
Write-Host ""
