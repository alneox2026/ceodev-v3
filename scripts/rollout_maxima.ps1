param(
    [Parameter(Mandatory = $true)]
    [string]$AuthToken,

    [string[]]$AllowedOrigins = @("https://ceoappdev.flutterflow.app"),

    [string]$ProjectId = "ceo-dev123",
    [string]$Region = "us-central1",
    [string]$Repository = "ceosystem",
    [string]$Tag = "latest",
    [string]$SmokeMessage = "Hello from the new Maxima gateway",
    [string[]]$AlertNotificationChannels = @(),
    [switch]$SkipBuild,
    [switch]$SkipApply,
    [switch]$IncludeStreamingSmoke
)

$ErrorActionPreference = "Stop"

$buildScript = Join-Path $PSScriptRoot "build_images.ps1"
$deployScript = Join-Path $PSScriptRoot "deploy_infra.ps1"
$smokeScript = Join-Path $PSScriptRoot "smoke_gateway.ps1"
$terraformDir = Join-Path $PSScriptRoot "..\\infra\\terraform"

if ($SkipBuild) {
    $gatewayImage = "$Region-docker.pkg.dev/$ProjectId/$Repository/ceoagent-gateway-v3`:$Tag"
    $workerImage = "$Region-docker.pkg.dev/$ProjectId/$Repository/ceoagent-persistence-worker-v3`:$Tag"
    $billingApiImage = "$Region-docker.pkg.dev/$ProjectId/$Repository/ceoagent-billing-api-v3`:$Tag"
}

else {
    $buildResult = & $buildScript `
        -ProjectId $ProjectId `
        -Region $Region `
        -Repository $Repository `
        -Tag $Tag
    $gatewayImage = $buildResult.gateway_image
    $workerImage = $buildResult.worker_image
    $billingApiImage = $buildResult.billing_api_image
}

& $deployScript `
    -GatewayImage $gatewayImage `
    -WorkerImage $workerImage `
    -BillingApiImage $billingApiImage `
    -ProjectId $ProjectId `
    -Region $Region `
    -AllowedOrigins $AllowedOrigins `
    -BillingApiAllowedOrigins $AllowedOrigins `
    -AlertNotificationChannels $AlertNotificationChannels `
    -PlanOnly:$SkipApply

if ($SkipApply) {
    Write-Host "Plan-only mode finished. Skipping smoke tests."
    exit 0
}

Push-Location $terraformDir
try {
    $gatewayUrl = terraform output -raw gateway_url
}
finally {
    Pop-Location
}

Write-Host "Running buffered smoke test against $gatewayUrl"
& $smokeScript `
    -ServiceUrl $gatewayUrl `
    -AuthToken $AuthToken `
    -Message $SmokeMessage

if ($IncludeStreamingSmoke) {
    Write-Host "Running streaming smoke test against $gatewayUrl"
    & $smokeScript `
        -ServiceUrl $gatewayUrl `
        -AuthToken $AuthToken `
        -Message $SmokeMessage `
        -Stream
}
