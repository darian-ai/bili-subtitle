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
    New-Item -ItemType Directory -Path $workDir -Force | Out-Null
    $env:UV_TOOL_DIR = $toolDir
    $env:UV_TOOL_BIN_DIR = $binDir
    uv tool install $wheelPath
    if ($LASTEXITCODE -ne 0) { throw "isolated uv tool install failed" }
    $command = "Set-Location -LiteralPath '$($workDir.Replace("'", "''"))'; `$env:PATH='$($binDir.Replace("'", "''"));' + [IO.Path]::PathSeparator + `$env:PATH; bili-study --help; if (`$LASTEXITCODE -ne 0) { exit `$LASTEXITCODE }; bili-subtitle --help"
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
