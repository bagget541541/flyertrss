@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ── 配置 ──
set "PROJECT_DIR=%~dp0"
set "PYTHON=python"
set "LOG_DIR=%PROJECT_DIR%\logs"

:: ── 日志 ──
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\run_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.log"
set "LOG_FILE=%LOG_FILE: =0%"

:: ── 版次参数 ──
set "EDITION=%~1"
set "RESUME_ARG="
if /I "%EDITION%"=="--resume" (
    set "EDITION="
    set "RESUME_ARG=--resume"
)
if /I "%~2"=="--resume" set "RESUME_ARG=--resume"
if "%EDITION%"=="" (
    set /a "HOUR=%time:~0,2%"
    if !HOUR! LSS 12 (set "EDITION=早报") else (set "EDITION=晚报")
)

echo ========================================
echo   飞客信用卡日报 - %EDITION%
echo   %date% %time%
echo ========================================
echo.

cd /d "%PROJECT_DIR%"

:: ── Chrome 会话前置检查 ──
powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:9333/json/version' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo [FAIL] 未检测到 Edge 调试会话（127.0.0.1:9333）。
    echo 请先双击“启动飞客浏览器.bat”，等待论坛页面正常显示后再运行本脚本。
    echo %date% %time% ^| %EDITION% ^| RC=2 ^| Edge CDP unavailable >> "%LOG_DIR%\history.log"
    endlocal & pause & exit /b 2
)

:: ── 执行 ──
set "RUN_OUTPUT=%TEMP%\flyert_run_output_%random%_%random%.txt"
"%PYTHON%" run.py --edition "%EDITION%" --mode simple %RESUME_ARG% > "%RUN_OUTPUT%" 2>&1
set "RC=%ERRORLEVEL%"
type "%RUN_OUTPUT%"
type "%RUN_OUTPUT%" >> "%LOG_FILE%"

echo.
if %RC% EQU 0 (
    echo [OK] 执行成功
) else (
    echo [FAIL] 执行失败，返回码: %RC%
)

:: ── 写日志 ──
echo %date% %time% ^| %EDITION% ^| RC=%RC% >> "%LOG_DIR%\history.log"

endlocal & pause & exit /b %RC%
