@echo off
setlocal
title MediNote Launcher
cd /d "%~dp0"

echo ========================================
echo          MediNote Launcher
echo ========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env file not found.
    pause
    exit /b 1
)

echo [1/4] Cleaning old MediNote ports...

powershell -NoProfile -Command ^
"$ports = @(8001,8501,8502,8503,8504,8505); ^
foreach ($port in $ports) { ^
  $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; ^
  foreach ($connection in $connections) { ^
    if ($connection.OwningProcess -gt 0) { ^
      Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue ^
    } ^
  } ^
}"

timeout /t 2 /nobreak >nul

echo [2/4] Starting FastAPI backend...

start "MediNote Backend" cmd /k ""%CD%\venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8001"

echo Waiting for backend...

powershell -NoProfile -Command ^
"$ok=$false; ^
for($i=0;$i -lt 15;$i++){ ^
  try { ^
    $r=Invoke-RestMethod 'http://127.0.0.1:8001/health' -TimeoutSec 2; ^
    if($r.status -eq 'healthy'){ $ok=$true; break } ^
  } catch {} ^
  Start-Sleep -Seconds 1 ^
}; ^
if(-not $ok){ exit 1 }"

if errorlevel 1 (
    echo.
    echo [ERROR] Backend health check failed.
    echo Check the MediNote Backend window.
    pause
    exit /b 1
)

echo [3/4] Backend healthy.
echo [4/4] Starting Streamlit frontend...

start "MediNote Frontend" cmd /k ""%CD%\venv\Scripts\python.exe" -m streamlit run frontend\app.py --server.port 8501"

timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo          MediNote is READY
echo ========================================
echo Backend : http://127.0.0.1:8001
echo Frontend: http://localhost:8501
echo ========================================

start "" "http://localhost:8501"

timeout /t 2 /nobreak >nul
exit /b 0
