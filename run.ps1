# Little KB launcher (Windows / PowerShell)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-Python([string]$exe, [string[]]$pre = @()) {
    try {
        & $exe @pre -c "import sys" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$python = $null
$pre = @()

$venv = Join-Path $here ".venv\Scripts\python.exe"
if ((Test-Path $venv) -and (Test-Python $venv)) {
    $python = $venv
} elseif ($env:LITTLE_KB_PYTHON -and (Test-Python $env:LITTLE_KB_PYTHON)) {
    $python = $env:LITTLE_KB_PYTHON
} elseif ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Python "py" @("-3"))) {
    $python = "py"
    $pre = @("-3")
} elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Python "python")) {
    $python = "python"
} elseif ((Get-Command python3 -ErrorAction SilentlyContinue) -and (Test-Python "python3")) {
    $python = "python3"
} else {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        (Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python")
    )
    foreach ($dir in $candidates) {
        if (-not (Test-Path $dir)) { continue }
        $found = Get-ChildItem $dir -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
                 Sort-Object FullName -Descending | Select-Object -First 1
        if ($found -and (Test-Python $found.FullName)) { $python = $found.FullName; break }
    }
}

if (-not $python) {
    throw "Python 3.8+ not found. Install Python, or set LITTLE_KB_PYTHON to python.exe path."
}

& $python @pre (Join-Path $here "server.py") @args
