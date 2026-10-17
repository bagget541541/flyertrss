@echo off
rem WorkBuddy -> OpenAI 兼容网关（workbuddy2api-hub）
rem 账号凭据已导入 accounts\，无需 --info
setlocal
cd /d "%~dp0workbuddy2api-hub-main"
set WB_PROXY_DEFAULT_REALM=cn
python wb_proxy.py --host 127.0.0.1 --port 8788 --api-key sk-workbuddy
