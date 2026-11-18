@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
set "PY="
set "PYARG="

rem 1) project virtualenv
if exist "%HERE%.venv\Scripts\python.exe" (
  "%HERE%.venv\Scripts\python.exe" -c "import sys" >nul 2>nul && set "PY=%HERE%.venv\Scripts\python.exe"
)

rem 2) explicit override
if not defined PY if defined LITTLE_KB_PYTHON (
  "%LITTLE_KB_PYTHON%" -c "import sys" >nul 2>nul && set "PY=%LITTLE_KB_PYTHON%"
)

rem 3) Windows py launcher
if not defined PY (
  py -3 -c "import sys" >nul 2>nul && (set "PY=py" & set "PYARG=-3")
)

rem 4) python / python3 on PATH (skip broken Microsoft Store stubs)
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  python3 -c "import sys" >nul 2>nul && set "PY=python3"
)

rem 5) per-user Python installs
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if not defined PY if exist "%%D\python.exe" (
      "%%D\python.exe" -c "import sys" >nul 2>nul && set "PY=%%D\python.exe"
    )
  )
)

rem 6) last resort: DSH bundled runtime (dev machine only)
set "DSHPY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not defined PY if exist "%DSHPY%" (
  "%DSHPY%" -c "import sys" >nul 2>nul && set "PY=%DSHPY%"
)

if not defined PY (
  echo Python 3.8+ not found. Install Python, or set LITTLE_KB_PYTHON to python.exe path.
  pause
  exit /b 1
)

"%PY%" %PYARG% "%HERE%server.py" %*
if errorlevel 1 pause
