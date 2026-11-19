@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
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

rem 4) python / python3 on PATH, but never execute the 0-byte Microsoft Store alias
if not defined PY (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PY (
      if not "%%~zP"=="0" (
        "%%~fP" -c "import sys" >nul 2>nul && set "PY=%%~fP"
      )
    )
  )
)
if not defined PY (
  for /f "delims=" %%P in ('where python3 2^>nul') do (
    if not defined PY (
      if not "%%~zP"=="0" (
        "%%~fP" -c "import sys" >nul 2>nul && set "PY=%%~fP"
      )
    )
  )
)

rem 5) per-user Python installs
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if not defined PY if exist "%%D\python.exe" (
      "%%D\python.exe" -c "import sys" >nul 2>nul && set "PY=%%D\python.exe"
    )
  )
)

rem 6) all-users Python installs
if not defined PY (
  for /d %%D in ("%ProgramFiles%\Python*") do (
    if not defined PY if exist "%%D\python.exe" (
      "%%D\python.exe" -c "import sys" >nul 2>nul && set "PY=%%D\python.exe"
    )
  )
)

rem 7) WorkBuddy bundled runtime (this machine)
if not defined PY (
  for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if not defined PY if exist "%%D\python.exe" (
      "%%D\python.exe" -c "import sys" >nul 2>nul && set "PY=%%D\python.exe"
    )
  )
)

rem 8) last resort: DSH bundled runtime (dev machine only)
set "DSHPY=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not defined PY if exist "%DSHPY%" (
  "%DSHPY%" -c "import sys" >nul 2>nul && set "PY=%DSHPY%"
)

if not defined PY (
  echo.
  echo   Python 3.8+ not found.
  echo.
  echo   Fix A: install Python 3.8+  https://www.python.org/downloads/
  echo   Fix B: set LITTLE_KB_PYTHON to your python.exe path, e.g.
  echo          setx LITTLE_KB_PYTHON "C:\Python312\python.exe"
  echo.
  pause
  exit /b 1
)

rem --- already running? just open the browser ---
set "PORT="
if exist "%HERE%data\kb.port" (
  set /p PORT=<"%HERE%data\kb.port"
  if defined PORT (
    netstat -ano | findstr ":!PORT!" | findstr "LISTENING" >nul 2>nul && (
      echo   Already running: http://127.0.0.1:!PORT!
      start "" "http://127.0.0.1:!PORT!"
      timeout /t 2 >nul
      exit /b 0
    )
  )
)

rem --- start server in its own window ---
if exist "%HERE%data\kb.port" del "%HERE%data\kb.port" >nul 2>nul
start "Little KB" "%PY%" %PYARG% "%HERE%server.py" %*

rem --- wait for the port file, then open the browser ---
set "PORT="
for /l %%i in (1,1,40) do (
  if not defined PORT (
    if exist "%HERE%data\kb.port" (
      set /p PORT=<"%HERE%data\kb.port"
    )
    if not defined PORT timeout /t 1 /nobreak >nul
  )
)

if defined PORT (
  echo   Started: http://127.0.0.1:!PORT!
  start "" "http://127.0.0.1:!PORT!"
) else (
  echo   Server is still starting. Open http://127.0.0.1:8777 manually if needed.
)
timeout /t 3 >nul
