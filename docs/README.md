# 飞客信用卡日报 — 自动生成工具

从飞客信用卡论坛自动抓取热帖，经 LLM 富化/分类后生成日报 HTML、公众号文章和卡片图片。

## 项目结构

| 文件 | 作用 |
|------|------|
| `run.py` | 一键全流程（抓取→富化→分类→卡片→QA质检→部署→公众号文章） |
| `run.bat` | Windows 一键执行脚本（支持定时任务） |
| `fetcher.py` | 论坛抓取（Playwright/httpx/curl 三级降级） |
| `enrich.py` | LLM 富化（摘要 + 公众号标题 + 价值标签） |
| `summary.py` | LLM 分类 + 日报 Markdown/HTML 渲染 |
| `card_gen.py` | 卡片图片生成（Playwright 截图，5 张 + 封面，综合评分排序选头条，右侧蓝条含二维码+数据摘要；Playwright 页面统一 finally 清理，帖子详情/热评抓取避免在线程池中直接调用 sync API） |
| `wechat_image_qa.py` | 卡片 QA 质检（VLM 视觉审查，两阶段扫描，自动生成报告） |
| `wechat_article_gen.py` | 公众号文章组装（预览版 + 粘贴版） |
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

### 2. 一键运行

```
python run.py                  # 自动判断早报/晚报（12:00 为界）
python run.py --edition 晚报   # 指定晚报
python run.py --edition 早报   # 指定早报
run.bat                        # Windows 双击运行（自动判断版次）
run.bat 晚报                   # Windows 指定版次
```

**Windows 定时任务：** 用任务计划程序设置 `run.bat`，可设每天两次（如 9:00 早报、18:00 晚报）。详见任务计划程序配置。

### 3. QA 质检配置（可选）

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
python fetcher.py                     # 仅抓取
python enrich.py --edition 晚报       # 仅 LLM 富化
python summary.py                     # 仅分类+日报
python card_gen.py                    # 仅卡片（需 Playwright）
python wechat_image_qa.py             # 仅 QA 质检
python wechat_article_gen.py          # 仅公众号文章
```

## 环境要求

- Python 3.10+
- 依赖：httpx, beautifulsoup4, jinja2, playwright (可选)
- Playwright 浏览器：`playwright install chromium`

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

### 2026-06-07

- **card_05 信息图**：修复布局，热评和编辑点评改为纵向排列，不再挤到右侧
- **card_top3**：每帖热评 3 条（100 字截断），优化间距确保编辑点评可见；修复顶部 VOL 重复；顶部改为白底
- **封面**：cover_43 比例改为 3:4（750×1000），与主卡片一致；封面配色改为蓝白科技风
- **银行名检测**：新增 _detect_bank 函数，优先从标题检测银行名，避免「中国银行」被截断为「银行」
- **编辑点评**：top3 和 info 卡片的 LLM 点评正确传入银行名，避免误判