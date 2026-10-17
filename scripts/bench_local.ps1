<#
.SYNOPSIS
    Build the LocdexBench CPU image and run an audited local coding task.
.DESCRIPTION
    Docker Desktop must run Linux containers. Locdex and the model must already
    be installed in the repository .venv and its managed cache.
.EXAMPLE
    .\scripts\bench_local.ps1 -Model qwen25-3b -MemoryGb 10
.EXAMPLE
    .\scripts\bench_local.ps1 -Model qwen25-7b -MemoryGb 14 -SkipBuild
#>
[CmdletBinding()]
param(
    [ValidateSet("qwen25-3b", "qwen25-7b", "qwen25-14b", "kimi", "qwen")]
    [string] $Model = "qwen25-3b",
    [ValidateRange(4, 32)]
    [int] $MemoryGb = 8,
    [string] $ModelVolume = "",
    [switch] $SkipBuild
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repo
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI not found. Start Docker Desktop in Linux-container mode."
    }
    docker info --format '{{.ServerVersion}}' | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker engine unavailable. Start Docker Desktop."
    }

    $locdexExe = Join-Path $repo ".venv\Scripts\locdex.exe"
    $pythonExe = Join-Path $repo ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $locdexExe) -or -not (Test-Path -LiteralPath $pythonExe)) {
        throw "Repo .venv missing. Create/activate .venv and install: python -m pip install -e '.[dev]'"
    }

    $statusText = & $locdexExe model status $Model
    if ($LASTEXITCODE -ne 0) { throw "Cannot query model status for $Model." }
    $status = $statusText | ConvertFrom-Json
    if (-not $status.installed -or -not $status.path) {
        throw "Model $Model is not installed. Run: locdex model install $Model"
    }
    $gguf = (Resolve-Path -LiteralPath $status.path).Path
    if ([IO.Path]::GetExtension($gguf).ToLowerInvariant() -ne ".gguf") {
        throw "Installed model file is not a GGUF."
    }

    Write-Host "Verifying the pinned benchmark fixture..."
    & $pythonExe scripts/validate_benchmark_fixtures.py
    if ($LASTEXITCODE -ne 0) { throw "Fixture validation failed." }

    $tag = "locdex-bench:local"
    if (-not $SkipBuild) {
        Write-Host "Building CPU-only image. The first build downloads Python packages..."
        # The default Docker Desktop Buildx builder can use the docker-container
    # driver. Without --load, it leaves the result only in BuildKit cache.
    & docker buildx build --load --platform linux/amd64 -f benchmarks/Dockerfile -t $tag .
        if ($LASTEXITCODE -ne 0) { throw "Benchmark Docker image build failed." }
    }

    $imageId = (& docker image inspect --format '{{.Id}}' $tag)
    if ($LASTEXITCODE -ne 0 -or -not $imageId) {
        throw "Benchmark image is missing from the local Docker image store. Re-run the build with docker buildx build --load (or run the helper without -SkipBuild)."
    }
    $imageId = $imageId.Trim()
    if ($imageId -notmatch '^sha256:[0-9a-f]{64}$') { throw "Cannot determine pinned Docker image ID." }

    Write-Host "Checking the image runtime with networking disabled..."
    $verifyArgs = @("run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--user", "65534:65534", $imageId, "locdex", "runtime", "verify")
    & docker @verifyArgs
    if ($LASTEXITCODE -ne 0) { throw "The benchmark image's llama.cpp runtime is not ready." }

    $resultsDir = Join-Path $repo "benchmarks\results\local"
    New-Item -Path $resultsDir -ItemType Directory -Force | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $output = Join-Path $resultsDir "$Model-$stamp.json"

    Write-Host "Running local-only LocdexBench: $Model, memory cap $MemoryGb GiB..."
    $args = @(
        "benchmark", "run-local",
        "--repo", $repo,
        "--manifest", (Join-Path $repo "benchmarks\tasks\py-arithmetic-edge-001.yaml"),
        "--image", $imageId,
        "--model", $Model,
        "--model-path", $gguf,
        "--memory-gb", "$MemoryGb",
        "--output", $output
    )
    if ($ModelVolume) {
        $args += @("--model-volume", $ModelVolume)
    }
    & $locdexExe @args
    if ($LASTEXITCODE -ne 0) { throw "Local benchmark runner failed; inspect the error above." }

    Write-Host "Saved trial metadata to $output"
    Write-Host "A single trial is not a comparative benchmark score."
}
finally {
    Pop-Location
}
