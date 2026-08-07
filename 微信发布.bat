@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "PROJECT_DIR=%~dp0"
set "PYTHON=python"
set "LOG_DIR=%PROJECT_DIR%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM 用 PowerShell 取得可靠的日期格式 (YYYYMMDD)
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd'"`) do set "TODAY_DATE=%%i"
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-Date -Format 'HHmm'"`) do set "TODAY_TIME=%%i"

set "STATE_FILE=%LOG_DIR%\wechat_pub_state_%TODAY_DATE%.txt"
set "LOG_FILE=%LOG_DIR%\wechat_pub_%TODAY_DATE%_%TODAY_TIME%.log"
set "START_STEP=1"

if /I "%~1"=="--resume" (
    if not exist "%STATE_FILE%" (
        echo [FAIL] No saved publish state for today.
        endlocal & pause & exit /b 1
    )
    for /f "usebackq tokens=1,* delims==" %%A in ("%STATE_FILE%") do set "%%A=%%B"
    if not defined STEP (
        echo [FAIL] Invalid publish state: %STATE_FILE%
        endlocal & pause & exit /b 1
    )
    set "START_STEP=!STEP!"
    echo [RESUME] Starting from step !START_STEP!
) else (
    > "%STATE_FILE%" echo STEP=1
)

echo %date% %time% ^| wechat_publish ^| START step=!START_STEP! >> "%LOG_FILE%"
echo ========================================
echo   WeChat Publish - resumable mode
echo   %date% %time%
echo ========================================
echo.

if !START_STEP! LEQ 1 (
    echo [1/4] Extracting bottom link list...
    "%PYTHON%" extract_links.py --print-path > "%TEMP%\flyert_links_path.txt" 2>&1
    set "RC=!ERRORLEVEL!"
    type "%TEMP%\flyert_links_path.txt"
    type "%TEMP%\flyert_links_path.txt" >> "%LOG_FILE%"
    if !RC! NEQ 0 (
        echo [FAIL] Step 1 failed, RC=!RC!
        goto :failed
    )
    set "LINKS_FILE="
    for /f "usebackq delims=" %%i in ("%TEMP%\flyert_links_path.txt") do set "LINKS_FILE=%%i"
    if not defined LINKS_FILE (
        echo [FAIL] No links json captured
        set "RC=1"
        goto :failed
    )
    echo [OK] links: !LINKS_FILE!
    > "%STATE_FILE%" echo STEP=2
    >> "%STATE_FILE%" echo LINKS_FILE=!LINKS_FILE!
)

if !START_STEP! LEQ 2 (
    echo [2/4] Fetching thread details...
    "%PYTHON%" fetch_threads_detail.py "!LINKS_FILE!" --print-path > "%TEMP%\flyert_detail_path.txt" 2>&1
    set "RC=!ERRORLEVEL!"
    type "%TEMP%\flyert_detail_path.txt"
    type "%TEMP%\flyert_detail_path.txt" >> "%LOG_FILE%"
    set "DETAIL_FILE="
    for /f "usebackq delims=" %%i in ("%TEMP%\flyert_detail_path.txt") do set "DETAIL_FILE=%%i"
    if defined DETAIL_FILE if exist "!DETAIL_FILE!" (
        echo [OK] details: !DETAIL_FILE!
    ) else (
        set "DETAIL_FILE="
        echo [WARN] No usable details json, continue with links only.
    )
    if !RC! NEQ 0 echo [WARN] Step 2 failed, continue with partial details.
    > "%STATE_FILE%" echo STEP=3
    >> "%STATE_FILE%" echo LINKS_FILE=!LINKS_FILE!
    >> "%STATE_FILE%" echo DETAIL_FILE=!DETAIL_FILE!
)

if !START_STEP! LEQ 3 (
    echo [3/4] LLM classify / review / layout...
    set "TEMP_MD_PATH=%TEMP%\flyert_md_path_%random%.txt"
    if defined DETAIL_FILE (
        "%PYTHON%" llm_daily_gen.py "!LINKS_FILE!" --detail "!DETAIL_FILE!" --print-path > "!TEMP_MD_PATH!" 2>&1
    ) else (
        "%PYTHON%" llm_daily_gen.py "!LINKS_FILE!" --print-path > "!TEMP_MD_PATH!" 2>&1
    )
    set "RC=!ERRORLEVEL!"
    type "!TEMP_MD_PATH!"
    type "!TEMP_MD_PATH!" >> "%LOG_FILE%"
    if !RC! NEQ 0 (
        echo [FAIL] Step 3 failed, state saved. Start proxy and run: 微信发布.bat --resume
        goto :failed
    )
    set "MD_FILE="
    for /f "usebackq delims=" %%i in ("!TEMP_MD_PATH!") do set "MD_FILE=%%i"
    if not defined MD_FILE (
        echo [FAIL] No md path captured
        set "RC=1"
        goto :failed
    )
    echo [OK] md: !MD_FILE!
    > "%STATE_FILE%" echo STEP=4
    >> "%STATE_FILE%" echo LINKS_FILE=!LINKS_FILE!
    >> "%STATE_FILE%" echo DETAIL_FILE=!DETAIL_FILE!
    >> "%STATE_FILE%" echo MD_FILE=!MD_FILE!
    if exist "!TEMP_MD_PATH!" del /q "!TEMP_MD_PATH!"
)

if !START_STEP! LEQ 4 (
    echo [4/4] Rendering HTML...
    "%PYTHON%" docx_to_wechat.py "!MD_FILE!" --out-dir _site > "%TEMP%\flyert_html_output.txt" 2>&1
    set "RC=!ERRORLEVEL!"
    type "%TEMP%\flyert_html_output.txt"
    type "%TEMP%\flyert_html_output.txt" >> "%LOG_FILE%"
    if !RC! NEQ 0 (
        echo [FAIL] Step 4 failed, state saved. Run: 微信发布.bat --resume
        goto :failed
    )
)

if exist "%STATE_FILE%" del /q "%STATE_FILE%"
echo %date% %time% ^| wechat_publish ^| md=!MD_FILE! ^| RC=0 >> "%LOG_DIR%\history.log"
echo [OK] WeChat publish done.
endlocal & pause & exit /b 0

:failed
if not defined RC set "RC=1"
echo %date% %time% ^| wechat_publish ^| failed_step=!START_STEP! ^| RC=!RC! >> "%LOG_DIR%\history.log"
echo [PAUSED] State kept at: %STATE_FILE%
endlocal & pause & exit /b %RC%