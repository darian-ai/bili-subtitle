param([Parameter(Mandatory = $true)][string]$Wheel)

$ErrorActionPreference = "Stop"
$wheelPath = (Resolve-Path -LiteralPath $Wheel).Path
$originalToolDir = [Environment]::GetEnvironmentVariable("UV_TOOL_DIR", "Process")
$originalBinDir = [Environment]::GetEnvironmentVariable("UV_TOOL_BIN_DIR", "Process")
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("bili-study-install-" + [guid]::NewGuid().ToString("N"))
$resolvedTempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$resolvedRoot = [System.IO.Path]::GetFullPath($temporaryRoot)
if (-not $resolvedRoot.StartsWith($resolvedTempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe temporary root"
}

try {
    $toolDir = Join-Path $resolvedRoot "tools"
    $binDir = Join-Path $resolvedRoot "bin"
    $workDir = Join-Path $resolvedRoot "work"
    $fixtureDir = Join-Path $resolvedRoot "legacy-fixture"
    $fixturePackage = Join-Path $fixtureDir "src\bili_subtitle"
    $fixtureDist = Join-Path $fixtureDir "dist"
    New-Item -ItemType Directory -Path $workDir -Force | Out-Null
    New-Item -ItemType Directory -Path $fixturePackage -Force | Out-Null
    New-Item -ItemType Directory -Path $fixtureDist -Force | Out-Null
    $env:UV_TOOL_DIR = $toolDir
    $env:UV_TOOL_BIN_DIR = $binDir

    @'
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bili-subtitle"
version = "0.1.0"
requires-python = ">=3.12"

[project.scripts]
bili-subtitle = "bili_subtitle.cli:main"
'@ | Set-Content -LiteralPath (Join-Path $fixtureDir "pyproject.toml") -Encoding UTF8
    '"""Legacy migration fixture."""' | Set-Content -LiteralPath (Join-Path $fixturePackage "__init__.py") -Encoding UTF8
    @'
def main() -> int:
    print("legacy fixture")
    return 0
'@ | Set-Content -LiteralPath (Join-Path $fixturePackage "cli.py") -Encoding UTF8

    uv build --wheel $fixtureDir --out-dir $fixtureDist
    if ($LASTEXITCODE -ne 0) { throw "legacy fixture build failed" }
    $legacyWheel = (Resolve-Path -LiteralPath (Join-Path $fixtureDist "bili_subtitle-0.1.0-py3-none-any.whl")).Path
    uv tool install $legacyWheel
    if ($LASTEXITCODE -ne 0) { throw "legacy fixture install failed" }
    & (Join-Path $binDir "bili-subtitle.exe") | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "legacy fixture command failed" }
    uv tool uninstall bili-subtitle
    if ($LASTEXITCODE -ne 0) { throw "legacy fixture uninstall failed" }
    if (Test-Path -LiteralPath (Join-Path $binDir "bili-subtitle.exe")) {
        throw "legacy command remained after uninstall"
    }

    uv tool install $wheelPath
    if ($LASTEXITCODE -ne 0) { throw "isolated uv tool install failed" }
    $toolList = uv tool list
    if ($LASTEXITCODE -ne 0 -or ($toolList -join "`n") -notmatch "bili-study v0\.2\.0\.dev1") {
        throw "new distribution is not the only installed tool identity"
    }
    if (($toolList -join "`n") -match "bili-subtitle v0\.1\.0") {
        throw "legacy tool identity remained after migration"
    }
    $command = "Set-Location -LiteralPath '$($workDir.Replace("'", "''"))'; `$env:PATH='$($binDir.Replace("'", "''"));' + [IO.Path]::PathSeparator + `$env:PATH; bili-study --help; if (`$LASTEXITCODE -ne 0) { exit `$LASTEXITCODE }; bili-subtitle --help; if (`$LASTEXITCODE -ne 0) { exit `$LASTEXITCODE }; bili-study serve 2>`$null; if (`$LASTEXITCODE -ne 2) { exit 9 }; bili-subtitle not-a-video 2>`$null; if (`$LASTEXITCODE -ne 2) { exit 9 }; exit 0"
    & powershell -NoProfile -NonInteractive -Command $command
    if ($LASTEXITCODE -ne 0) { throw "fresh PowerShell invocation failed" }
}
finally {
    [Environment]::SetEnvironmentVariable("UV_TOOL_DIR", $originalToolDir, "Process")
    [Environment]::SetEnvironmentVariable("UV_TOOL_BIN_DIR", $originalBinDir, "Process")
    if (Test-Path -LiteralPath $resolvedRoot) {
        Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
    }
}
