@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOGDIR=%ROOT%\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
set "LOGFILE=%LOGDIR%\engine_%TODAY%.log"

echo ============================================================ >> "%LOGFILE%"
echo [%date% %time%] run start (args: %*) >> "%LOGFILE%"

py -m paper.engine --all %* >> "%LOGFILE%" 2>&1
set "RC=%ERRORLEVEL%"

echo [%date% %time%] run end rc=%RC% >> "%LOGFILE%"

if not "%RC%"=="0" (
    echo ------------------------------------------------------------ >> "%LOGDIR%\errors.log"
    echo [%date% %time%] ENGINE FAILED rc=%RC% >> "%LOGDIR%\errors.log"
    type "%LOGFILE%" >> "%LOGDIR%\errors.log"
)

exit /b %RC%
