# ─────────────────────────────────────────────────────────────────
# deploy-openshift.ps1 — Interactive OpenShift Deployment Script
# ─────────────────────────────────────────────────────────────────
# Prompts for all environment-specific parameters and deploys the
# OpenRouter Emulator to an OpenShift cluster.
#
# Usage: .\deploy-openshift.ps1
# ─────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  OpenRouter Emulator — OpenShift Deployment" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── Prompt for parameters ────────────────────────────────────────

$namespace = Read-Host "OpenShift Namespace/Project [default: llm-chatbot]"
if ([string]::IsNullOrWhiteSpace($namespace)) { $namespace = "llm-chatbot" }

$registry = Read-Host "Container Registry URL (e.g. registry.internal.org/myproject)"
while ([string]::IsNullOrWhiteSpace($registry)) {
    Write-Host "  ⚠ Registry URL is required!" -ForegroundColor Yellow
    $registry = Read-Host "Container Registry URL"
}

$gpuCount = Read-Host "Number of GPUs [default: 3]"
if ([string]::IsNullOrWhiteSpace($gpuCount)) { $gpuCount = "3" }

$quantization = Read-Host "Quantization method (awq/gptq/none) [default: awq]"
if ([string]::IsNullOrWhiteSpace($quantization)) { $quantization = "awq" }

$gpuMemUtil = Read-Host "GPU Memory Utilization (0.0-1.0) [default: 0.90]"
if ([string]::IsNullOrWhiteSpace($gpuMemUtil)) { $gpuMemUtil = "0.90" }

$maxModelLen = Read-Host "Max Model Length (tokens) [default: 32768]"
if ([string]::IsNullOrWhiteSpace($maxModelLen)) { $maxModelLen = "32768" }

$pvcName = Read-Host "PVC Name for model weights [default: model-weights-pvc]"
if ([string]::IsNullOrWhiteSpace($pvcName)) { $pvcName = "model-weights-pvc" }

$modelHostPath = Read-Host "Model weights host path (if using hostPath instead of PVC, leave empty to skip)"

Write-Host ""
Write-Host "─── Deployment Summary ───" -ForegroundColor Green
Write-Host "  Namespace:       $namespace"
Write-Host "  Registry:        $registry"
Write-Host "  GPUs:            $gpuCount"
Write-Host "  Quantization:    $quantization"
Write-Host "  GPU Memory Util: $gpuMemUtil"
Write-Host "  Max Model Len:   $maxModelLen"
Write-Host "  PVC Name:        $pvcName"
if (-not [string]::IsNullOrWhiteSpace($modelHostPath)) {
    Write-Host "  Host Path:       $modelHostPath"
}
Write-Host ""

$confirm = Read-Host "Proceed with deployment? (y/N)"
if ($confirm -ne "y" -and $confirm -ne "Y") {
    Write-Host "Deployment cancelled." -ForegroundColor Yellow
    exit 0
}

# ── Build and push image ─────────────────────────────────────────

Write-Host ""
Write-Host "Step 1: Building Docker image..." -ForegroundColor Cyan
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dockerDir = $scriptDir

docker build -t "${registry}/openrouter-emulator:latest" -f "$dockerDir/Dockerfile" "$dockerDir"
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Docker build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Step 2: Pushing image to registry..." -ForegroundColor Cyan
docker push "${registry}/openrouter-emulator:latest"
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Docker push failed! Make sure you are logged into the registry." -ForegroundColor Red
    Write-Host "  Try: docker login $registry" -ForegroundColor Yellow
    exit 1
}

# ── Apply OpenShift deployment ───────────────────────────────────

Write-Host "Step 3: Applying OpenShift deployment..." -ForegroundColor Cyan

$templatePath = "$dockerDir/openshift-deployment.yaml"
$deployContent = Get-Content $templatePath -Raw

# Replace all placeholders
$deployContent = $deployContent -replace "__NAMESPACE__", $namespace
$deployContent = $deployContent -replace "__REGISTRY__", $registry
$deployContent = $deployContent -replace "__GPU_COUNT__", $gpuCount
$deployContent = $deployContent -replace "__QUANTIZATION__", $quantization
$deployContent = $deployContent -replace "__GPU_MEMORY_UTIL__", $gpuMemUtil
$deployContent = $deployContent -replace "__MAX_MODEL_LEN__", $maxModelLen
$deployContent = $deployContent -replace "__PVC_NAME__", $pvcName

if (-not [string]::IsNullOrWhiteSpace($modelHostPath)) {
    $deployContent = $deployContent -replace "__MODEL_HOST_PATH__", $modelHostPath
}

# Write resolved manifest
$resolvedPath = "$dockerDir/openshift-deployment.resolved.yaml"
$deployContent | Out-File -FilePath $resolvedPath -Encoding utf8

Write-Host "  Resolved manifest written to: $resolvedPath" -ForegroundColor Gray

# Ensure we're in the right project
oc project $namespace 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Creating namespace $namespace..." -ForegroundColor Yellow
    oc new-project $namespace
}

oc apply -f $resolvedPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ oc apply failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✓ Deployment submitted successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "  Monitor with:" -ForegroundColor Gray
Write-Host "    oc get pods -n $namespace -w" -ForegroundColor Gray
Write-Host ""
Write-Host "  The emulator API will be available at:" -ForegroundColor Gray
Write-Host "    http://openrouter-emulator-service.$namespace.svc:8000" -ForegroundColor Gray
Write-Host ""
Write-Host "  Set this in the backend:" -ForegroundColor Gray
Write-Host "    LLM_BASE_URL=http://openrouter-emulator-service.$namespace.svc:8000/api/v1" -ForegroundColor Gray
Write-Host "═══════════════════════════════════════════════════════════" -ForegroundColor Green
