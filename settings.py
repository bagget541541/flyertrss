# -*- coding: utf-8 -*-
"""统一配置 — 所有模块从此读取路径/密钥/参数"""
import json, os, sys
from pathlib import Path

# -- clear broken system proxy (sandbox 127.0.0.1:9) --
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    if os.environ.get(_k, "").startswith("http://127.0.0.1:"):
        os.environ.pop(_k, None)

# ── 项目路径 ──
CWD = Path(__file__).parent

# ── LLM 配置（从用户级文件读取） ──
LLM_CONFIG_PATH = Path.home() / ".llm_config.json"
LLM_OK = False
LLM_KEY = ""
LLM_BASE = ""
LLM_MODEL = ""
if LLM_CONFIG_PATH.exists():
    try:
        d = json.loads(LLM_CONFIG_PATH.read_text(encoding="utf-8"))
        LLM_KEY = d.get("api_key", "")
        LLM_BASE = d.get("api_base", "")
        LLM_MODEL = d.get("model", "mimo-v2.5")
        LLM_OK = bool(LLM_KEY and LLM_BASE)
    except:
        pass

# ── 腾讯 COS 配置（从项目级文件读取） ──
COS_CONFIG_PATH = CWD / "cos_config.json"
COS_BUCKET = ""
COS_REGION = ""
COS_SECRET_ID = ""
COS_SECRET_KEY = ""
if COS_CONFIG_PATH.exists():
    try:
        d = json.loads(COS_CONFIG_PATH.read_text(encoding="utf-8"))
        COS_BUCKET = d.get("bucket", "")
        COS_REGION = d.get("region", "")
        COS_SECRET_ID = d.get("secret_id", "")
        COS_SECRET_KEY = d.get("secret_key", "")
    except:
        pass

# ── 代理配置 ──
PROXY = "http://127.0.0.1:10808"

# ── 论坛抓取 ──
BASE_URL = "https://www.flyert.com.cn"
AD_KW = ["收", "代"]
MIN_TITLE = 4
MIN_REP = 3
MIN_VIEW = 3000
WAF_RETRY_DELAYS = [30, 120, 600]

# ── 卡片渲染 ──
CARD_W, CARD_H = 750, 1000
BRANDING = "@moat成长"
OUT_DIR = CWD / "_cards"

# ── 数据文件 ──
RAW_PATH = CWD / "threads_raw.json"
FILTERED_PATH = CWD / "threads_filtered.json"
ENRICHED_PATH = CWD / "threads_enriched.json"
SEEN_TIDS_PATH = CWD / "seen_tids.json"

# ── 公众号文章 ──
ARTICLE_DIR = CWD / "_site"
SITE_DIR = CWD / "_site"
