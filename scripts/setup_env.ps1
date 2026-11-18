# Install Little KB runtime prerequisites (user scope, no admin needed):
#   - Node.js LTS (includes npm)
#   - MinGit (git command)
#   - pnpm (optional, via npm global install)
# Re-running is safe: existing installs are skipped.
# NOTE: keep this file ASCII-only so Windows PowerShell 5.1 parses it correctly.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Join-Path $env:LOCALAPPDATA "Programs"
$tmp = Join-Path $root "_downloads"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$nodeVersion = "v26.13.0"
$gitTag = "v2.56.0.windows.4"
$gitFile = "MinGit-2.56.0.4-64-bit.zip"

function Fetch($urls, $out) {
    foreach ($url in $urls) {
        Write-Host "download $url"
        & curl.exe -L -sS --retry 3 --retry-delay 2 -m 900 -o $out $url
        if ((Test-Path $out) -and ((Get-Item $out).Length -gt 1MB)) {
            $size = [math]::Round((Get-Item $out).Length / 1MB, 1)
            Write-Host "  OK $size MB"
            return $true
        }
        Write-Host "  failed, trying next mirror"
    }
    return $false
}

# ---------------------------------------------------------------- Node.js
$nodeDir = Join-Path $root "node"
if (-not (Test-Path (Join-Path $nodeDir "node.exe"))) {
    $zip = Join-Path $tmp "node.zip"
    $nodeFile = "node-$nodeVersion-win-x64.zip"
    $ok = Fetch @(
        "https://npmmirror.com/mirrors/node/$nodeVersion/$nodeFile",
        "https://nodejs.org/dist/$nodeVersion/$nodeFile"
    ) $zip
    if (-not $ok) { throw "Node.js download failed" }
    Write-Host "extract node"
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $inner = Join-Path $tmp ("node-" + $nodeVersion + "-win-x64")
    if (Test-Path $nodeDir) { Remove-Item $nodeDir -Recurse -Force }
    Move-Item -Path $inner -Destination $nodeDir
    Remove-Item $zip -Force
} else {
    Write-Host "node already present"
}

# ---------------------------------------------------------------- MinGit
$gitDir = Join-Path $root "git"
if (-not (Test-Path (Join-Path $gitDir "cmd\git.exe"))) {
    $zip = Join-Path $tmp "mingit.zip"
    $ok = Fetch @(
        "https://mirrors.tuna.tsinghua.edu.cn/github-release/git-for-windows/git/LatestRelease/$gitFile",
        "https://ghfast.top/https://github.com/git-for-windows/git/releases/download/$gitTag/$gitFile",
        "https://github.com/git-for-windows/git/releases/download/$gitTag/$gitFile"
    ) $zip
    if (-not $ok) { throw "MinGit download failed" }
    Write-Host "extract mingit"
    if (Test-Path $gitDir) { Remove-Item $gitDir -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $gitDir -Force
    Remove-Item $zip -Force
} else {
    Write-Host "git already present"
}

# ---------------------------------------------------------------- PATH
# NOTE: build the separator from a char code; a literal ";" inside a quoted
# string can be mangled by some command wrappers.
$sep = [char]59
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$targets = @($nodeDir, (Join-Path $gitDir "cmd"))
foreach ($target in $targets) {
    $parts = @($userPath -split $sep | Where-Object { $_ })
    if ($parts -notcontains $target) {
        $userPath = (($parts + $target) -join $sep)
        Write-Host "PATH += $target"
    }
}
[Environment]::SetEnvironmentVariable("Path", $userPath, "User")

# ---------------------------------------------------------------- pnpm
$env:Path = "$nodeDir;" + (Join-Path $gitDir "cmd") + ";" + $env:Path
$npmCmd = Join-Path $nodeDir "npm.cmd"
if (Test-Path $npmCmd) {
    Write-Host "install pnpm (optional)"
    & $npmCmd install -g pnpm --no-fund --no-audit 2>&1 | Select-Object -Last 6
}

Write-Host ""
Write-Host "=== result ==="
& (Join-Path $nodeDir "node.exe") -v
& $npmCmd -v
& (Join-Path $gitDir "cmd\git.exe") --version
$pnpmCmd = Join-Path $nodeDir "pnpm.cmd"
if (Test-Path $pnpmCmd) { & $pnpmCmd -v } else { Write-Host "pnpm: not installed (optional)" }
