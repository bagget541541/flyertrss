# 飞客信用卡日报 — 自动生成工具

从飞客信用卡论坛自动抓取热帖，经 LLM 富化/分类后生成日报 HTML、公众号文章和卡片图片。

## 项目结构

| 文件 | 作用 |
|------|------|
| `run.py` | 一键全流程（简易/完整两种模式，默认简易） |
| `run.bat` | Windows 一键执行脚本（支持定时任务） |
| `fetcher.py` | 论坛抓取（Playwright/httpx/curl 三级降级，智能扩容） |
| `enrich.py` | LLM 富化（摘要 + 公众号标题 + 价值标签） |
| `summary.py` | LLM 分类 + 日报 Markdown/HTML 渲染 |
| `card_gen.py` | 卡片图片生成（Playwright 截图，5 张 + 封面，综合评分排序选头条，右侧蓝条含二维码+数据摘要；Playwright 页面统一 finally 清理，帖子详情/热评抓取避免在线程池中直接调用 sync API） |
| `cover_gen.py` | PIL 轻量封面生成（发文精简模式使用，无需 Playwright） |
| `wechat_image_qa.py` | 卡片 QA 质检（VLM 视觉审查，两阶段扫描，自动生成报告） |
| `wechat_article_gen.py` | 公众号文章组装（支持 `simple/full` 两种发布模式） |
| `settings.py` | 统一配置（LLM、代理、论坛参数、代理自动清除） |
| `template*.html` | 卡片/封面/信息图 HTML 模板 |
| `report_tpl.html` / `.md` | 日报 Jinja2 模板 |

## 快速开始

### 1. 配置 LLM

在 `~/.llm_config.json` 中设置：

```
{
  "api_key": "sk-xxx",
  "api_base": "http://127.0.0.1:10808/v1",
  "model": "mimo-v2.5"
}
```

### 2. 一键运行（简易模式，默认）

只产出面向发文的封面图 + 公众号内容，跳过日报渲染、卡片截图、QA 和部署：

```
python run.py                  # 简易模式（默认）
python run.py --mode simple    # 同上
```

### 3. 完整模式（含卡片 + QA + 部署）

产出日报、卡片图、QA 报告、历史归档 index.html：

```
python run.py --mode full
python run.py --mode full --edition 晚报
```

### 4. Windows 快捷执行

```
run.bat                        # 简易模式（默认）
run.bat 晚报                   # 指定版次
```

**Windows 定时任务：** 用任务计划程序设置 `run.bat`，可设每天两次（如 9:00 早报、18:00 晚报）。详见任务计划程序配置。

### 5. QA 质检配置（可选）

卡片生成后自动运行 QA 质检。在项目根目录创建 `qa_config_qwen.json`：

```json
{
  "provider": "qwen",
  "qwen_api_key": "sk-xxx",
  "model": "qwen-vl-max",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "output_dir": "_cards"
}
```

- 配置文件不存在或 API key 未填写时，QA 步骤自动跳过
- QA 报告输出到 `_cards/image_qa_MMDD.md`
- 也可单独运行：`python wechat_image_qa.py`

### 4. 单步运行

```
python fetcher.py                     # 仅抓取（默认第1页，智能扩容）
python fetcher.py --pages 3           # 抓取前3页
python fetcher.py --all               # 抓取所有页
python enrich.py --edition 晚报       # 仅 LLM 富化
python summary.py                     # 仅分类+日报
python cover_gen.py                   # 仅封面图（轻量，简易模式下使用）
python card_gen.py                    # 完整卡片生成（需 Playwright，耗时较长）
python wechat_image_qa.py             # 仅 QA 质检
python wechat_article_gen.py --publish-mode simple             # 发文模式：封面 + 精简粘贴版
python wechat_article_gen.py --publish-mode full               # 完整模式文章（含卡片位）
python wechat_article_gen.py --no-cards --publish-mode simple  # 仅文章，不触发卡片生成
```

## 环境要求

- Python 3.10+
- 依赖：`httpx`, `beautifulsoup4`, `Pillow`, `jinja2`, `playwright`（可选）
- 一键安装：`pip install httpx beautifulsoup4 Pillow jinja2 playwright`
- Playwright 浏览器：`python -m playwright install chromium`

### Windows Store Python 注意事项

Windows Store 版 Python 受沙箱限制，Playwright 无法启动子进程（WinError 5 拒绝访问）。

解决方案：
1. 使用非 Store 版 Python（推荐 python.org 安装包）
2. 或使用 `run_outside_sandbox.py` 在沙箱外运行卡片生成：

```
python run_outside_sandbox.py
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `日报_YYYY-MM-DD.html` | 当日日报（浏览器打开） |
| `日报_YYYY-MM-DD.md` | Markdown 版日报 |
| `_cards/` | 卡片图片（card_01~05.png, cover, top3；`preview` 已禁用，不再作为常规输出） |
| `_cards/image_qa_MMDD.md` | QA 质检报告（自动生成） |
| `qr_code.jpg` | 公众号二维码（卡片侧边栏用，建议 344px+） |
| `_site/公众号文章_*.html` | 公众号预览版 |
| `_site/公众号粘贴版_*.html` | 公众号粘贴版（全选复制粘贴到编辑器） |
| `_site/公众号元数据_*.json` | 文章元数据 |
| `threads_raw.json` | 原始抓取数据 |
| `threads_filtered.json` | 过滤后数据 |
| `threads_enriched.json` | LLM 富化后数据 |
| `seen_tids.json` | 已见帖子 ID（去重用） |

## 配置项（settings.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `PROXY` | `http://127.0.0.1:10808` | curl 抓取用代理 |
| `BASE_URL` | `https://www.flyert.com.cn` | 论坛地址 |
| `MIN_REP` | 3 | 最低回复数过滤 |
| `MIN_VIEW` | 3000 | 最低浏览数过滤 |
| `CARD_W` / `CARD_H` | 750 / 1000 | 卡片尺寸（3:4） |
| `BRANDING` | `@moat成长` | 卡片水印 |

## fetcher.py 抓取策略

默认只抓论坛信用卡版块的**第1页**（按最新回复排序），已能覆盖每日活跃热帖。

当第1页帖子数 **≥ 18 帖**（接近论坛每页容量）且论坛有第2页时，自动扩容到第2页，避免高峰日漏帖，可通过 `--pages N` 或 `--all` 手动覆盖。

| 场景 | 行为 |
|------|------|
| 日常（< 18 帖） | 只抓第1页 |
| 高峰日（≥ 18 帖） | 自动扩容到第2页 |
| `--pages 3` 或 `--all` | 按用户指定，不触发扩容 |

## 故障排除

### httpx 连接被拒绝（WinError 10061）

系统设置了不可达的代理（如 127.0.0.1:9）。`settings.py` 已内置自动清除机制：
导入时检测并移除指向 127.0.0.1:* 的代理环境变量，所有下游模块自动生效。

### LLM 分类返回格式错误

`classify_llm` 要求 LLM 返回 `[{"tid":"...","category":"..."}]` 格式。
如果模型返回纯字符串数组，会自动降级到规则分类。

### Playwright 权限错误

参见「Windows Store Python 注意事项」。

### Playwright callback exception / greenlet 跨线程错误

`card_gen.py` 已统一把 Playwright page/context 清理放入 `finally`，并避免在 `ThreadPoolExecutor` 中直接调用 Playwright sync API 抓取帖子详情/热评。
如果日志曾出现 `SyncBase._sync.<locals>.<lambda>()` 或 `greenlet.error: cannot switch to a different thread`，请确认使用的是当前版本代码并重新运行 `python card_gen.py` 验证。

### run.py 中文/emoji 编码错误

`run.py` 顶部已设置 `sys.stdout.reconfigure(encoding="utf-8")`，
Windows GBK 控制台下 emoji 字符不再导致崩溃。

## 更新日志

### 2026-06-20 新增

- **fetcher.py 智能扩容**：第1页帖子数 ≥ 18 时自动抓取第2页兜底，日常保持1页高效，高峰日不漏帖
- **精简模式收口为发文模式**：`run.py --mode simple` 现在只执行 抓取 → 富化 → 封面 → 公众号文章，不再生成日报
- **发布辅助模块**：新增 `publishing_helpers.py`，把评分、银行识别、模板点评从 `card_gen.py` 中拆出，供封面和发文链路复用
- **公众号文章双发布模式**：`wechat_article_gen.py` 新增 `--publish-mode simple|full`，`simple` 仅保留封面、概览、精选、提醒、Top3、少量扩展帖和链接汇总，更适合直接发文
- **`run.py` 控制台兼容性**：修复当前终端环境下流式输出 `flush()` 触发的 `OSError: [Errno 22] Invalid argument`

### 2026-06-12 优化

- **简易模式大幅提速**：summary.py 新增 `--rule-only`（跳过 LLM 分类，改用规则分类，~40s→0s）和 `--skip-png`（跳过 Playwright PNG 截图，~8s→0s）
- **`cover_gen.py` 改用 PIL**：彻底去除 Playwright 依赖，轻量封面 ~0.9s 生成（原 ~8s），零浏览器开销
- **简易模式总耗时**：从 ~60-80s 降至 ~5-10s（不含 enrich），真正轻量
- **`summary.py` CLI**：新增 `--rule-only` / `--skip-png` 参数

### 2026-06-06 新增

- **简易/完整双模式**：`run.py` 新增 `--mode` 参数（默认 `simple`），简易模式跳过卡片截图+QA+部署，仅产出封面图和公众号文章，运行时间大幅缩短
- **`cover_gen.py`**：轻量封面生成器，复用 `card_gen.render_cover` 但跳过所有卡片渲染和 LLM 点评
- **`wechat_article_gen.py`**：`gen_article(check_cards=False)` 支持卡片缺失降级为纯文字版；CLI 新增 `--no-cards` 参数
- **`run.py`** 文档和参数提示信息同步更新

### 2026-06-07

- **card_05 信息图**：修复布局，热评和编辑点评改为纵向排列，不再挤到右侧
- **card_top3**：每帖热评 3 条（100 字截断），优化间距确保编辑点评可见；修复顶部 VOL 重复；顶部改为白底
- **封面**：cover_43 比例改为 3:4（750×1000），与主卡片一致；封面配色改为蓝白科技风
- **银行名检测**：新增 _detect_bank 函数，优先从标题检测银行名，避免「中国银行」被截断为「银行」
- **编辑点评**：top3 和 info 卡片的 LLM 点评正确传入银行名，避免误判