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

REM Start every run from fresh klines. The cache TTL (4h) can span 00:00 UTC, so a
REM catch-up run just before midnight would otherwise leave an unfinished daily
REM candle that the next run treats as closed (happened 2026-09-28).
del /q "%ROOT%\paper\cache\*_1d_*.csv" >nul 2>&1

py -m paper.engine --all %* >> "%LOGFILE%" 2>&1
set "RC=%ERRORLEVEL%"

echo [%date% %time%] run end rc=%RC% >> "%LOGFILE%"

if not "%RC%"=="0" (
    echo ------------------------------------------------------------ >> "%LOGDIR%\errors.log"
    echo [%date% %time%] ENGINE FAILED rc=%RC% >> "%LOGDIR%\errors.log"
    type "%LOGFILE%" >> "%LOGDIR%\errors.log"
)

REM Health check incl. ledger reconciliation and the pre-registered kill rules.
REM Exit codes: 0 OK, 1 WARN, 2 KILL (retire with: py -m paper.engine --profile X --retire "...").
py -m paper.healthcheck >> "%LOGFILE%" 2>&1
set "HC=%ERRORLEVEL%"
if "%HC%"=="2" (
    echo ------------------------------------------------------------ >> "%LOGDIR%\errors.log"
    echo [%date% %time%] KILL RULE TRIGGERED - see %LOGFILE% >> "%LOGDIR%\errors.log"
)

REM Commit the day's ledger locally so the forward record has a dated, tamper-evident
REM history. Touches paper/state only; never pushes.
git add -A paper/state >nul 2>&1
git commit -q -m "Paper state %TODAY% (scheduled run rc=%RC%, health=%HC%)" -- paper/state >nul 2>&1

exit /b %RC%
