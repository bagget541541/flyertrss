@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: =====================================================
::  wechat_publish.bat
::  Step 1: extract_links.py       HTML bottom links -> links json
::  Step 2: fetch_threads_detail.py links json -> post details (WAF rate-limited)
::  Step 3: llm_daily_gen.py       links+details -> LLM review/classify -> md
::  Step 4: docx_to_wechat.py      md -> update today's _site HTML
::  NOTE: keep this file pure ASCII to avoid codepage
::        mojibake on Chinese Windows cmd.
:: =====================================================

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "PYTHON=python"
set "LOG_DIR=%PROJECT_DIR%\logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "LOG_FILE=%LOG_DIR%\wechat_pub_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.log"
set "LOG_FILE=%LOG_FILE: =0%"
echo %date% %time% ^| wechat_publish ^| START >> "%LOG_FILE%"

echo ========================================
echo   WeChat Publish - extract + details + LLM + render
echo   %date% %time%
echo ========================================
echo.

:: ---- Step 1: HTML -> links json ----
echo [1/4] Extracting bottom link list from today's daily report HTML...
"%PYTHON%" extract_links.py --print-path > "%TEMP%\flyert_links_path.txt" 2>&1
set "RC=%ERRORLEVEL%"
type "%TEMP%\flyert_links_path.txt"
type "%TEMP%\flyert_links_path.txt" >> "%LOG_FILE%"
if %RC% NEQ 0 (
    echo [FAIL] Step 1 failed, RC=%RC%
    type "%TEMP%\flyert_links_path.txt"
    echo %date% %time% ^| wechat_publish ^| step1 fail RC=%RC% >> "%LOG_DIR%\history.log"
    endlocal & pause & exit /b %RC%
)

set "LINKS_FILE="
for /f "usebackq delims=" %%i in ("%TEMP%\flyert_links_path.txt") do set "LINKS_FILE=%%i"
if not defined LINKS_FILE (
    echo [FAIL] No links json captured
    type "%TEMP%\flyert_links_path.txt"
    echo %date% %time% ^| wechat_publish ^| no links path ^| RC=1 >> "%LOG_DIR%\history.log"
    endlocal & pause & exit /b 1
)
echo [OK] links: %LINKS_FILE%

:: ---- Step 2: links json -> post details ----
echo [2/4] Fetching thread details (WAF rate-limited)...
"%PYTHON%" fetch_threads_detail.py "%LINKS_FILE%" --print-path > "%TEMP%\flyert_detail_path.txt" 2>&1
set "RC=%ERRORLEVEL%"
type "%TEMP%\flyert_detail_path.txt"
type "%TEMP%\flyert_detail_path.txt" >> "%LOG_FILE%"
set "DETAIL_FILE="
for /f "usebackq delims=" %%i in ("%TEMP%\flyert_detail_path.txt") do set "DETAIL_FILE=%%i"
if defined DETAIL_FILE if exist "%DETAIL_FILE%" (
    echo [OK] details: %DETAIL_FILE%
) else (
    set "DETAIL_FILE="
    echo [WARN] No usable details json captured, continue without details
)
if %RC% NEQ 0 echo [WARN] Step 2 failed, RC=%RC% (continue with partial details when available)

:: ---- Step 3: links + details -> LLM -> md ----
echo [3/4] LLM classify / review / layout -> md...
if defined DETAIL_FILE (
    "%PYTHON%" llm_daily_gen.py "%LINKS_FILE%" --detail "%DETAIL_FILE%" --print-path > "%TEMP%\flyert_md_path.txt" 2>&1
) else (
    "%PYTHON%" llm_daily_gen.py "%LINKS_FILE%" --print-path > "%TEMP%\flyert_md_path.txt" 2>&1
)
set "RC=%ERRORLEVEL%"
type "%TEMP%\flyert_md_path.txt"
type "%TEMP%\flyert_md_path.txt" >> "%LOG_FILE%"
if %RC% NEQ 0 (
    echo [FAIL] Step 3 failed, RC=%RC%
    type "%TEMP%\flyert_md_path.txt"
    echo %date% %time% ^| wechat_publish ^| step3 fail RC=%RC% >> "%LOG_DIR%\history.log"
    endlocal & pause & exit /b %RC%
)

set "MD_FILE="
for /f "usebackq delims=" %%i in ("%TEMP%\flyert_md_path.txt") do set "MD_FILE=%%i"
if not defined MD_FILE (
    echo [FAIL] No md path captured
    type "%TEMP%\flyert_md_path.txt"
    echo %date% %time% ^| wechat_publish ^| no md path ^| RC=1 >> "%LOG_DIR%\history.log"
    endlocal & pause & exit /b 1
)
echo [OK] md: %MD_FILE%

:: ---- Step 4: md -> HTML in _site ----
echo [4/4] Running docx_to_wechat.py...
set "HTML_OUTPUT=%TEMP%\flyert_html_output.txt"
"%PYTHON%" docx_to_wechat.py "%MD_FILE%" --out-dir _site > "%HTML_OUTPUT%" 2>&1
set "RC=%ERRORLEVEL%"
type "%HTML_OUTPUT%"
type "%HTML_OUTPUT%" >> "%LOG_FILE%"

echo.
if %RC% EQU 0 (
    echo [OK] WeChat publish done
) else (
    echo [FAIL] Step 4 failed, RC=%RC%
)

echo %date% %time% ^| wechat_publish ^| md=%MD_FILE% ^| RC=%RC% >> "%LOG_DIR%\history.log"

endlocal & pause & exit /b %RC%
