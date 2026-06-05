$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

function Invoke-DockerBuild {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    docker build @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker build failed: docker build $($Arguments -join ' ')"
    }
}

Invoke-DockerBuild @("-t", "bioinformatics/backend:local", "-f", "docker/backend/Dockerfile", ".")
docker tag bioinformatics/backend:local bioinformatics/backend:metrics-local
if ($LASTEXITCODE -ne 0) {
    throw "docker tag failed: bioinformatics/backend:metrics-local"
}
Invoke-DockerBuild @("-t", "bioinformatics/frontend:local", "-f", "docker/frontend/Dockerfile", ".")
Invoke-DockerBuild @("-t", "bioinformatics/spark-streaming:local", "-f", "jobs/spark_streaming/Dockerfile", ".")

Write-Host "Built local Kubernetes images:" -ForegroundColor Green
Write-Host "  bioinformatics/backend:local"
Write-Host "  bioinformatics/backend:metrics-local"
Write-Host "  bioinformatics/frontend:local"
Write-Host "  bioinformatics/spark-streaming:local"
