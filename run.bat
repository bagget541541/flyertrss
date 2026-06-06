@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: ── 配置 ──
set "PROJECT_DIR=D:\ckl\个人\bat\flyertrss"
set "PYTHON=python"
set "LOG_DIR=%PROJECT_DIR%\logs"

:: ── 日志 ──
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\run_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.log"
set "LOG_FILE=%LOG_FILE: =0%"

:: ── 版次参数 ──
set "EDITION=%~1"
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

:: ── 执行 ──
"%PYTHON%" run.py --edition "%EDITION%" 2>&1
set "RC=%ERRORLEVEL%"

echo.
if %RC% EQU 0 (
    echo [OK] 执行成功
) else (
    echo [FAIL] 执行失败，返回码: %RC%
)

:: ── 写日志 ──
echo %date% %time% ^| %EDITION% ^| RC=%RC% >> "%LOG_DIR%\history.log"

endlocal
exit /b %RC%
