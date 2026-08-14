# ==============================================================================
# Phase 12 - AWS ECR Image Tag & Push
# infra/aws/push_to_ecr.ps1
#
# PURPOSE  : Tag the local telco-churn-api:latest image and push it to ECR
#            with two tags: `latest` and the current git commit SHA.
# VERIFIES : local image exists, Docker login succeeds, digest matches post-push.
# GENERATES: reports/ecr_push_report.json on successful push.
#
# USAGE:
#   .\infra\aws\push_to_ecr.ps1
#
# PREREQUISITES:
#   1. AWS CLI configured  : aws configure  (region must be ap-south-1)
#   2. Docker running      : docker info
#   3. Local image present : py -3.12 tasks.py docker-build
#   4. ECR repo created    : .\infra\aws\create_ecr_repo.ps1
# ==============================================================================

# "Continue" is correct here: every native command is already guarded by an
# explicit $LASTEXITCODE check, so Stop adds no safety — but it does cause
# PS5.1 to abort on stderr from native commands before those checks run.
$ErrorActionPreference = "Continue"

$REQUIRED_REGION   = "ap-south-1"
$REPOSITORY_NAME   = "telco-churn-api"
$LOCAL_IMAGE       = "telco-churn-api:latest"

# Report output path (relative to repo root - script is called from repo root)
$REPORT_PATH       = "reports\ecr_push_report.json"

# ------------------------------------------------------------------------------
# Helper: abort with a red error message and non-zero exit
# ------------------------------------------------------------------------------
function Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# ------------------------------------------------------------------------------
# Step 1: Verify the configured AWS region
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [1/8] Verifying configured AWS region..." -ForegroundColor Cyan

$configuredRegion = aws configure get region 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($configuredRegion)) {
    Fail "Could not determine the configured AWS region. Run 'aws configure' and set the region to '$REQUIRED_REGION'."
}
$configuredRegion = $configuredRegion.Trim()

if ($configuredRegion -ne $REQUIRED_REGION) {
    Fail "AWS CLI is configured for region '$configuredRegion', but this project requires '$REQUIRED_REGION'. Run 'aws configure'."
}
Write-Host "       Region OK: $configuredRegion" -ForegroundColor Green

# ------------------------------------------------------------------------------
# Step 2: Derive AWS account ID dynamically - never hardcoded
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [2/8] Fetching AWS account ID via STS..." -ForegroundColor Cyan

$AccountId = aws sts get-caller-identity --query Account --output text 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($AccountId)) {
    Fail "Could not retrieve AWS account ID. Verify your AWS CLI credentials with 'aws sts get-caller-identity'."
}
$AccountId = $AccountId.Trim()
Write-Host "       Account ID: $AccountId" -ForegroundColor Green

# ------------------------------------------------------------------------------
# Step 3: Build the repository URI
# ------------------------------------------------------------------------------
$RepositoryUri = "$AccountId.dkr.ecr.$REQUIRED_REGION.amazonaws.com/$REPOSITORY_NAME"
Write-Host ""
Write-Host "==> [3/8] Repository URI: $RepositoryUri" -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# Step 4: Verify the local Docker image exists
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [4/8] Verifying local Docker image '$LOCAL_IMAGE' exists..." -ForegroundColor Cyan

docker image inspect $LOCAL_IMAGE 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "Local image '$LOCAL_IMAGE' not found.`n       Build it first by running: py -3.12 tasks.py docker-build"
}
Write-Host "       Image found locally." -ForegroundColor Green

# ------------------------------------------------------------------------------
# Step 5: Resolve the git commit SHA for the second image tag
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [5/8] Resolving git commit SHA..." -ForegroundColor Cyan

$GitSha = git rev-parse --short HEAD 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($GitSha)) {
    Fail "Could not read git commit SHA. Ensure this directory is a git repository."
}
$GitSha = $GitSha.Trim()
Write-Host "       Git SHA: $GitSha" -ForegroundColor Green

# ------------------------------------------------------------------------------
# Step 6: Authenticate Docker with ECR
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [6/8] Authenticating Docker with ECR..." -ForegroundColor Cyan

$loginOutput = aws ecr get-login-password --region $REQUIRED_REGION | `
    docker login --username AWS --password-stdin $RepositoryUri 2>&1

if ($LASTEXITCODE -ne 0) {
    Fail "Docker login to ECR failed. Output:`n$loginOutput"
}

# Verify Docker actually reported success - do NOT silently continue
$loginOutputStr = $loginOutput -join "`n"
if ($loginOutputStr -notmatch "Login Succeeded") {
    Fail "Docker login did not report 'Login Succeeded'. Actual output:`n$loginOutputStr`nAborting."
}
Write-Host "       Login Succeeded." -ForegroundColor Green

# ------------------------------------------------------------------------------
# Step 7: Tag the image with both `latest` and git SHA tags, then push
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [7/8] Tagging and pushing image..." -ForegroundColor Cyan

$TagLatest = "${RepositoryUri}:latest"
$TagSha    = "${RepositoryUri}:${GitSha}"

# Tag: latest
Write-Host "       Tagging as: $TagLatest" -ForegroundColor White
docker tag $LOCAL_IMAGE $TagLatest
if ($LASTEXITCODE -ne 0) { Fail "Failed to tag image as '$TagLatest'." }

# Tag: git SHA
Write-Host "       Tagging as: $TagSha" -ForegroundColor White
docker tag $LOCAL_IMAGE $TagSha
if ($LASTEXITCODE -ne 0) { Fail "Failed to tag image as '$TagSha'." }

# Push: latest
Write-Host ""
Write-Host "       Pushing '$TagLatest'..." -ForegroundColor White
docker push $TagLatest
if ($LASTEXITCODE -ne 0) { Fail "Push of '$TagLatest' failed." }

# Push: git SHA
Write-Host ""
Write-Host "       Pushing '$TagSha'..." -ForegroundColor White
docker push $TagSha
if ($LASTEXITCODE -ne 0) { Fail "Push of '$TagSha' failed." }

Write-Host ""
Write-Host "       Both tags pushed successfully." -ForegroundColor Green

# ------------------------------------------------------------------------------
# Step 8: Verify digest - compare post-push RepoDigests against ECR imageDigest
#
# IMPORTANT: Do NOT compare docker image inspect .Id (image config digest) with
# ECR imageDigest (manifest digest). These are different digest types and will
# always differ even on a correct push.
#
# Correct approach: read RepoDigests AFTER push - Docker populates this field
# only after a successful push, and it contains the manifest digest (sha256:...)
# that ECR also reports.
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "==> [8/8] Verifying push digest (RepoDigests vs ECR imageDigest)..." -ForegroundColor Cyan

# 8a. Fetch the manifest digest from the local RepoDigests (post-push only)
$localDigestRaw = docker image inspect $TagLatest --format="{{index .RepoDigests 0}}" 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($localDigestRaw)) {
    Fail "Could not read RepoDigests from local image '$TagLatest'. Ensure the push completed successfully."
}
$localDigestRaw = $localDigestRaw.Trim()

# 8b. Extract the SHA portion after the '@' (format: registry/repo@sha256:...)
if ($localDigestRaw -notmatch "@") {
    Fail "Unexpected RepoDigests format - expected 'registry/repo@sha256:...', got: $localDigestRaw"
}
$localDigest = ($localDigestRaw -split "@")[1].Trim()
Write-Host "       Local  RepoDigest : $localDigest" -ForegroundColor White

# 8c. Query ECR for the imageDigest of the `latest` tag
$ecrDigest = aws ecr describe-images `
    --repository-name $REPOSITORY_NAME `
    --image-ids imageTag=latest `
    --query "imageDetails[0].imageDigest" `
    --output text 2>&1

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ecrDigest)) {
    Fail "Could not query ECR for imageDigest of '$REPOSITORY_NAME:latest'. AWS output:`n$ecrDigest"
}
$ecrDigest = $ecrDigest.Trim()
Write-Host "       ECR    imageDigest: $ecrDigest" -ForegroundColor White

# 8d. Compare
if ($localDigest -ne $ecrDigest) {
    Write-Host ""
    Write-Host "DIGEST MISMATCH:" -ForegroundColor Red
    Write-Host "  Local RepoDigest : $localDigest" -ForegroundColor Red
    Write-Host "  ECR imageDigest  : $ecrDigest"   -ForegroundColor Red
    Fail "Digest verification failed. The pushed image may be corrupt or a different image was pushed."
}

Write-Host "       Digest MATCH confirmed." -ForegroundColor Green

# ------------------------------------------------------------------------------
# Generate reports/ecr_push_report.json
# ------------------------------------------------------------------------------
$pushTimestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")

$report = [ordered]@{
    repository_name = $REPOSITORY_NAME
    region          = $REQUIRED_REGION
    image_tag       = $GitSha
    image_digest    = $ecrDigest
    repository_uri  = $RepositoryUri
    push_timestamp  = $pushTimestamp
}

$reportJson = $report | ConvertTo-Json -Depth 5
Set-Content -Path $REPORT_PATH -Value $reportJson -Encoding UTF8

Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "  Phase 12 - ECR Push COMPLETE" -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Repository      : $REPOSITORY_NAME"     -ForegroundColor White
Write-Host "  Repository URI  : $RepositoryUri"        -ForegroundColor White
Write-Host "  Tags pushed     : latest, $GitSha"       -ForegroundColor White
Write-Host "  Manifest Digest : $ecrDigest"            -ForegroundColor White
Write-Host "  Push Timestamp  : $pushTimestamp"        -ForegroundColor White
Write-Host "  Report saved to : $REPORT_PATH"          -ForegroundColor White
Write-Host ""
Write-Host "Next: open the AWS Console -> ECR -> $REPOSITORY_NAME" -ForegroundColor Cyan
Write-Host "      and confirm both 'latest' and '$GitSha' tags are visible." -ForegroundColor Cyan
Write-Host ""
