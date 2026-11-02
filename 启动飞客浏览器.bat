@echo off
setlocal

set "EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" set "EDGE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
if not exist "%EDGE%" (
    echo [ERROR] Microsoft Edge was not found in the standard install locations.
    echo Install Microsoft Edge or edit EDGE in this batch file.
    pause
    exit /b 1
)

set "PROFILE=%LOCALAPPDATA%\FlyertEdgeProfile"
start "Flyert Edge" "%EDGE%" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9333 --user-data-dir="%PROFILE%" "https://www.flyert.com.cn/forum.php?mod=forumdisplay&fid=59"
endlocal
