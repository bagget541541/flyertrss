# FlyerTRSS — 飞客信用卡日报

自动抓取飞客茶馆信用卡版块，经 LLM 分类 + 噪声过滤后，生成日报 HTML、Markdown、社交分享卡片和微信封面图，自动组装公众号文章，一键部署到静态托管。

## 功能概览

| 能力 | 说明 |
|------|------|
| 论坛抓取 | Playwright 无头浏览器抓取飞客信用卡版块，自动应对 WAF |
| 噪声过滤 | 已读去重（`seen_tids.json`）+ 低质帖过滤 |
| LLM 摘要 | 调用 OpenAI 兼容 API 生成 10 字摘要 + 价值标签（限时/避坑/攻略/公告/讨论/实测） |
| 公众号标题 | LLM 生成 ≤22 字公众号风格标题（含数字/行动导向），内置 `_make_wechat_fallback` 兜底 |
| 文章元数据 | 自动生成整体文章标题 + 摘要 + edition（供公众号信息流展示） |
| 正文文字化 | 每条帖子在图片前展示文字摘要块（摘要+标签+编辑点评），大幅降低读图成本 |
| 编辑推荐 | 文章顶部自动生成"今日编辑精选"板块，指引读者关注当日最有价值帖子 |
| 编辑点评全覆盖 | 所有帖子自动生成价值标签驱动的编辑点评+行动建议，同步到正文和卡片 |
| 公众号粘贴版 | 额外输出内联样式版本，全选复制即可贴入微信编辑器；图片标为上传占位符 |
| 早报/晚报 | `run.py --edition 早报|晚报`，默认按时间自动判断，标题/元数据跟随切换 |
| 分类渲染 | 关键词规则兜底，LLM 优先；生成分类分组的 HTML/Markdown 日报 |
| 卡片生成 | 750x1000 竖屏 3:4 卡片（热门→分类精选→top3→信息图 + 微信封面），3-5 张精简输出 |
| 编辑点评 | 抓取帖子原文+热评，LLM 生成引用热评观点+具体时间节点的行动建议 |
| 历史知识库RAG | BM25检索390条历史公众号文章，注入编辑点评prompt增强历史纵深，rag/目录可选加载 |
| 智能截断 | 热评/标题按句子边界截断（`。！？…`），不再断在句中 |
| 引文清洗 | Discuz! 引用块前缀自动清理（`作者发表于 日期 时间`），热评纯净 |
| 钩子文案 | 每张分类卡顶部增加板块定制引导语，提升阅读引导 |
| 公众号文章 | 自动组装卡片图 + 标题/摘要为完整文章 HTML，含元数据 JSON |
| 浏览器复用 | 所有截图/抓取共用一个 Chromium 实例（7→1 次启动） |
| 多平台部署 | GitHub Pages / 腾讯 COS / Vercel / 腾讯云函数 |

## 项目结构

```
flyertrss/
├── run.py              # 一键编排（抓取 → 摘要 → 卡片 → 文章）
├── fetcher.py          # 论坛抓取（Playwright/httpx）
├── enrich.py           # LLM 摘要 + 价值标签 + 公众号标题/元数据
├── summary.py          # 分类 + 日报渲染（HTML/Markdown/PNG）
├── card_gen.py         # 卡片图生成（Playwright 截图，浏览器复用）
├── settings.py         # 统一配置（路径/密钥/参数）
├── wechat_article_gen.py  # 公众号文章组装
├── deploy_cos.py       # 腾讯 COS 部署
│
├── report_tpl.html     # 日报 HTML 模板（Jinja2）
├── report_tpl.md       # 日报 Markdown 模板
├── rag/                # RAG 历史知识库（BM25检索，可选）
│   ├── rag_query.py    #   BM25 检索引擎
│   └── articles_kb.json#   390 条历史公众号文章
├── template.html       # 竖屏卡片模板（带热度条 + 统计栏 + 钩子文案）
├── template-info.html  # 信息图卡片模板（热评 + 编辑点评）
├── template-top3.html  # Top3 详情卡模板（金牌主题）
├── template-cover.html # 微信封面模板（16:9 横版）
│
├── _site/              # 部署目录（日报 HTML + index.html）
├── _cards/             # 生成的卡片 PNG
│
├── test/               # 单元测试 + 集成测试（pytest）
│   ├── conftest.py     #   共享 fixtures
│   ├── test_unit.py    #   纯逻辑函数测试（44 cases）
│   └── test_render.py  #   Playwright 渲染测试（10 cases）
│
├── cos_config.json     # 腾讯 COS 凭据
├── seen_tids.json      # 已处理帖子 ID（去重用）
├── vercel.json         # Vercel 部署配置
└── .github/workflows/
    └── deploy.yml      # GitHub Pages 部署
```

## 快速开始

### 1. 安装依赖

```bash
pip install playwright beautifulsoup4 httpx jinja2 cos-python-sdk-v5 Pillow pytest
playwright install chromium
```

### 2. 配置 LLM（可选，不配置则使用规则分类）

创建 `~/.llm_config.json`（`C:/Users/<用户名>/.llm_config.json`）：

```json
{
  "api_key": "your-api-key",
  "api_base": "https://your-api-endpoint.com/v1",
  "model": "your-model-name"
}
```

### 3. 配置 COS 部署（可选）

编辑 `cos_config.json`，填入腾讯云 API 密钥和存储桶信息。

### 4. 运行

```bash
# 一键全流程（抓取 → LLM 富化 → 渲染卡片 → 公众号文章）
python run.py
# 自动判断版次：12:00 前=早报，12:00 后=晚报

# 指定版次
python run.py --edition 早报
python run.py --edition 晚报

# 或分步执行
python fetcher.py              # 抓取论坛
python enrich.py --edition 晚报 # LLM 摘要 + 文章元数据
python summary.py               # 分类 + 渲染日报
python card_gen.py              # 生成卡片图
python wechat_article_gen.py    # 组装公众号文章
python deploy_cos.py            # 部署到 COS
```

### 5. 运行测试

```bash
pytest test/ -v          # 54 个用例，~25s（浏览器复用后更快）
```

测试基于缓存数据（`threads_filtered.json`、`_cards/*.png`），无需网络。覆盖：
- 纯逻辑函数：`_smart_truncate`、`_int`、`_fmt_bank_name`、`_ds_meta`、`_gen_editor_note`、`_is_waf`、`is_noise` 等
- Playwright 渲染：分类卡、信息图、top3、封面、预览图
- 集成逻辑：`filter_threads`、`load_seen`/`save_seen`

## 输出产物

| 文件 | 说明 |
|------|------|
| `日报_YYYY-MM-DD.md` | Markdown 日报 |
| `日报_YYYY-MM-DD.html` | HTML 日报（移动端适配） |
| `日报_YYYY-MM-DD.png` | 日报截图（微信公众号用） |
| `公众号文章_YYYY-MM-DD.html` | 公众号文章预览版（浏览器打开看效果） |
| `公众号粘贴版_YYYY-MM-DD.html` | 公众号文章粘贴版（内联样式，全选复制→贴入微信编辑器） |
| `公众号元数据_YYYY-MM-DD.json` | 结构化文章元数据（含 edition） |
| `_cards/card_01.png ~ card_03.png` | 分类卡片（竖屏 3:4，3-5 张） |
| `_cards/card_top3.png` | Top3 详情卡（含编辑点评 + 热评） |
| `_cards/card_03~05.png` | 信息图卡（热评 + 编辑点评 + 数据亮点） |
| `_cards/cover_wechat.png` | 微信封面（16:9 横版） |
| `_cards/preview.jpg` | 精选 3 张卡片缩略图 |

## 部署方式

| 平台 | 说明 |
|------|------|
| GitHub Pages | 推送到 `main` 分支自动触发，通过 Actions 部署 `_site/` |
| 腾讯 COS | `python deploy_cos.py` 上传到 COS 静态网站 |
| Vercel | 直接关联仓库，输出目录设为 `_site/` |
| 腾讯云函数 | 通过 `scf_bootstrap` + `index.py` 部署为 Serverless HTTP 代理 |

## 技术栈

- **Python 3** + Playwright（无头浏览器抓取 & 截图，浏览器实例复用）
- **BeautifulSoup4**（Discuz! 论坛 HTML 解析）
- **httpx**（HTTP 请求 + LLM API 调用）
- **BM25**（纯Python实现，零外部依赖的RAG检索，历史知识库注入编辑点评）
- **Jinja2**（模板渲染）
- **Pillow**（图片合成）
- **腾讯 COS SDK**（云存储部署）

## 已解决技术债务

| 问题 | 修复方式 |
|------|----------|
| Playwright 每次启动新浏览器 | 创建 `_ensure_browser()` 共享实例，7→1 次启动 |
| 无统一配置文件 | 新增 `settings.py`，6 个文件统一引用 |
| `enrich.py` 线性脚本 | 重构为 8 个可测试函数 |
| `summary.py` GBK 输出乱码 | 使用 `reconfigure()` 统一 UTF-8 |
| `cos_config.json` 明文密钥 | 已加入 `.gitignore` |

## 相关文档

- [公众号图文优化清单](公众号图文优化清单.md) — P0/P1/P2 分级的图文优化规划
- [系统规划](系统规划.md) — 架构总览 + 开发路线图
- [卡片设计蓝图](卡片设计蓝图.md) — 卡片视觉规范
- [落地实施方案](落地实施方案.md) — 部署策略 + WAF 应对
- [LLM RAG 评估](LLM_RAG评估.md) — LLM+RAG 方案评估

## License

Private project.
