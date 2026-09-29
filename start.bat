@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"

echo === ModelIQ setup ===

if not exist "%PY%" (
  echo Creating virtual environment in %VENV_DIR% ...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo Failed to create virtual environment. Is Python installed and on PATH?
    pause
    exit /b 1
  )
)

echo Installing backend prerequisites...
"%PY%" -m pip install --disable-pip-version-check -q -r backend\requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)

if not exist "backend\.env" (
  echo No backend\.env found - copying backend\.env.example.
  echo Fill in real credentials in backend\.env before generating.
  copy /y "backend\.env.example" "backend\.env" >nul
)

set "PORT=5000"
echo Checking for an existing process on port %PORT% ...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
  echo Stopping existing process %%P on port %PORT% ...
  taskkill /F /PID %%P >nul 2>&1
)

echo Starting backend on http://localhost:%PORT% ...
start "ModelIQ backend" cmd /k ""%PY%" -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port %PORT%"

echo Waiting for the server to come up...
timeout /t 3 /nobreak >nul

echo Opening the app in your browser...
start "" "http://localhost:%PORT%/"

endlocal
