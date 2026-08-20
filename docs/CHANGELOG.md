## [Unreleased]
### Added
- **银行名权威校正** — `llm_daily_gen.py` 新增 `load_tid_category()` + `fix_bank_from_category()`，按 tid 从 `threads_enriched.json` / `threads_filtered.json` 读出权威论坛版块（`category`），在两个环节消除"经典白金卡属招行却误写交通银行"一类误判：
  - **喂给 LLM**：`build_prompt()` 每条链接后追加 `[板块：招商银行]`，`SYSTEM_PROMPT` 要求 `### 行首` 与热门榜 `[银行]` 必须与 `[板块：]` 一致
  - **后处理强校正**：`fix_bank_from_category()` 按 tid 用权威 category 覆盖 `### 银行名 摘要` 行首和热门榜 `[银行]`，保留 LLM 点评/摘要/分类；非银行版块（求助问答、见闻闲聊等）不参与覆盖
  - **交集检测**：`links` 的 tid 与权威板块 tid 匹配率 < 50% 时打印 `[!]` 警告，避免残留旧 `threads_filtered/enriched.json` 时静默回退到 LLM 从标题推断
- **微信发布四步流程** — 新增 `微信发布.bat` 一键完成「日报 HTML 反向提取 → 公众号发布」
  - `extract_links.py`：解析 `_site/公众号文章_YYYY-MM-DD.html` **底部「原帖链接」区块**，只提取标题+URL+tid → `output/links_MMDD.json`
  - `fetch_threads_detail.py`：按链接列表逐条抓取帖子详情（首楼内容），WAF 限频（1.4~2.2s 随机间隔、403 检测即停）→ `output/threads_detail_MMDD.json`
  - `llm_daily_gen.py`：链接+帖子原文 → LLM 按 flyert-card-forum 技能格式点评/归类/排版 → `output/精选日报_MMDD-副标题.md`
  - **三段式点评**：每条点评按「现象 / 判断 / 依据」组织，引用帖子原文细节作支撑，避免空话套话
  - **多组 LLM 配置**：`apikey.txt` 支持多组 api_key/api_base 备用，自动探测 `/models` 并按**低成本优先**排序（flash/mini 等轻量模型在前，pro/max 昂贵模型在后），失败自动切换下一组
  - **批量回填**：按 tid 从预览版 HTML 回填回复/阅读数（含热门榜单行）
  - `docx_to_wechat.py` 复用：md → 回写 `_site` 当天 `公众号文章/粘贴版/元数据`

### Changed
- **文档归档** — 将项目规划、设计、公众号运营/发布、质量评估和 BAT 审查文档统一归档到 `docs/`，并补充文档导航。

### Fixed
- **四级帖子头兼容** — `docx_to_wechat.py` 的 `parse_daily` 帖子头正则从 `^###\s+` 放宽到 `^#{3,4}\s+`，兼容嵌套分组下的 `#### 帖子`（如 `### 疑问求助` 下的 `#### 帖子`）三级结构，修复此前 `####` 标题行被整体跳过、其 🔗/📊/💬 卡体数据反复覆盖导致丢帖的问题
- **Word 底稿元信息兼容** — `docx_to_wechat.py` 识别 `共20条讨论` / `共 20 条讨论` 等无空格统计行，避免今日概览、HTML description 和元数据 description 回退为 `精选日报`
- **Word 底稿列表兼容** — `docx_to_wechat.py` 兼容 Word 原生列表经 Pandoc 转换后的 `-`/`*`/`•` 卡体前缀、`1.`/`1\.` 榜单格式、`标题（N回/N阅）[银行]` 纯文本热门榜和引用块元信息，避免链接、统计、点评及热门榜单标题被解析丢失
- **日报标签兼容** — 增加 `⚪套路` 标签识别

## [0.6.1] - 2026-07-10

### Added
- **基于周报 Markdown 生成公众号粘贴 HTML** — 新增 `weekly_to_wechat.py`，将 `Weekly_Report_YYYY年M月第N周.md` 结构化周报转成公众号粘贴版
  - **解析**：顶层标题取期次（`# 信用卡周报 - 2026年7月第2周`）→ 一级板块（`## 🔄 权益变更` / `## 🏷️ 活动` 等）→ 三级卡片（`### {标题}`）→ 卡片字段（`**亮点：**` / `银行：xxx | 来源：xxx` / `[原文链接](url)` / `**结构化信息：**` 列表 / `**原文摘要：**`）
  - **视觉模板复用** `docx_to_wechat.py`：左边银行色条 + 银行/来源标签 + 标题 + ✨亮点块 + 结构化信息列表 + 原帖链接；银行色映射补充华夏（青）、兴业（深蓝）
  - **产物**：`公众号粘贴版_{period}.html`（纯内联，可直接粘贴进公众号编辑器）+ `公众号元数据_{period}.json`
  - **CLI**：`python weekly_to_wechat.py <md>` + `--out-dir DIR`

## [0.6.0] - 2026-07-10

### Added
- **基于 Word 底稿生成公众号粘贴 HTML** — 新增 `docx_to_wechat.py`，从精选日报 `.docx`（Coze AI 产出的结构化底稿）直接生成公众号粘贴版，绕过 JSON 数据流
  - **解析**：pandoc 抽 markdown → 按底稿稳定规律结构化（6 个一级板块 / 三级帖子卡片头 / 三行卡体 `🔗 标题+url` `📊 回复+阅读` `💬 定制批注` / 热门讨论榜单有序列表 / 空板块占位 / AI 合规声明）
  - **降级**：pandoc 不可用时回退 `python-docx` 逐段解析；批注缺失时 fallback 到 `publishing_helpers.gen_editor_note`
  - **视觉模板**：左边色条区分银行（工行红 / 比丰橙 / 中信蓝 / 农行绿 / 交行紫 / 邮储金 / 招行粉 / 浦发青 / 光大紫）+ 银行标签 + 分类副标 + 数据行（回复+阅读数）+ 点评气泡 + 按钮式原帖链接
  - **榜单精简渲染**：热门讨论等有序列表项走精简榜单行（排名+标题+银行+回复阅读数一行，无点评/链接）
  - **约束**：粘贴版纯内联样式，无 `<style>`/JS/外部资源/class，兼容微信公众号编辑器过滤
  - **产物**：`公众号文章_{date}.html` + `公众号粘贴版_{date}.html`（纯内联）+ `公众号元数据_{date}.json`
  - **CLI**：`python docx_to_wechat.py <docx>` + `--paste-only` + `--out-dir DIR`

## [0.5.3] - 2026-07-04

### Fixed
- **简易模式日期串档** — `wechat_article_gen.py` 在 `simple` 模式下不再误读旧的 `threads_enriched.json`，改为直接使用当天 `threads_filtered.json`，修复 2026-07-04 运行却生成 `2026-07-03` 发文文件的问题
- **封面数据源一致性** — `cover_gen.py` 默认改为优先使用当天抓取结果，避免简易链路沿用旧富化数据导致封面标题和统计串到前一天
- **Step 4 退出崩溃** — `run.py` 回收子进程输出线程并关闭管道，修复 `Fatal Python error: _enter_buffered_busy` 的解释器退出异常

## [0.5.2] - 2026-07-03

### Changed
- **简洁模式跳过 LLM** — `run.py --mode simple` 现在直接使用 `threads_filtered.json` 生成封面和公众号文章，不再执行 `enrich.py`
- **封面/发文链路增加回退** — `cover_gen.py`、`wechat_article_gen.py` 在 `threads_enriched.json` 缺失时自动回退到 `threads_filtered.json`

### Fixed
- **步骤短路** — `fetcher.py` / `enrich.py` 在无数据或网络失败时返回非 0；`run.py` 在 Step 1 无有效帖子或 Step 2 无有效富化结果时立即停止，不再继续执行后续无意义步骤

## [0.5.1] - 2026-06-20

### Changed
- **精简模式重构为发文模式** — `run.py --mode simple` 仅保留抓取、富化、封面生成、公众号文章组装，不再执行 `summary.py`
- **公众号文章支持发布模式** — `wechat_article_gen.py` 新增 `--publish-mode simple|full`，`simple` 输出更适合直接发文的结构，`full` 保持卡片位能力
- **封面生成解耦卡片链路** — `cover_gen.py` 改为依赖轻量发布辅助逻辑，不再从 `card_gen.py` 导入业务函数

### Added
- **`publishing_helpers.py`** — 抽出评分、银行识别、编辑点评模板等发布链路公共函数，供封面和公众号文章复用

### Fixed
- **`run.py` 终端输出兼容性** — 流式输出改为容错写入，修复当前环境下 `stdout.flush()` 抛出 `OSError: [Errno 22] Invalid argument`

# Changelog

All notable changes to this project will be documented in this file.

## [0.23.0] - 2026-06-20

### Added
- **fetcher.py 智能扩容** — 第1页帖子数 ≥ 18 时自动抓取第2页兜底，日常保持1页高效，高峰日不漏帖；可通过 `--pages N` 或 `--all` 手动覆盖

## [0.22.0] - 2026-06-21

### Changed
- **封面蓝白配色** — `cover_gen.py` `_render_cover_pil()` 颜色方案从深色渐变（`#0f172a → #1e293b`）改为浅蓝渐变（`#e0f2fe → #f0f9ff`），与 `template-cover.html` 统一蓝白风格；品牌文字、标题、统计数字、底部条颜色同步适配浅色背景

## [0.9.4] - 2026-06-16

### Fixed
- **`run.bat` 闪退修复** — 末尾新增 `pause`，避免双击执行后窗口立即关闭；安装全部缺失依赖（`beautifulsoup4`, `httpx`, `Pillow`, `jinja2`, `playwright`），消除所有 ImportError
- **Playwright Chromium 安装** — `python -m playwright install chromium --force` 完成 headless Chromium 下载，WAF 绕过恢复可用

### Cleanup
- 删除临时调试脚本：`_batch_fix.py`, `_fix_settings.py`, `_patch_fix2.py`, `_patch_sidebar.py`, `_render_test.py`, `_test_card_gen.py`, `__sidebar_test.html`
- 删除无关文件：`Qwen-VL-Max使用.txt`, `qr_code_8cm.jpg`

## [0.9.3] - 2026-06-08

### Changed
- **Playwright 抓取回退串行** — `card_gen.py` 的 top3 帖子详情抓取、info-card 热评抓取不再通过 `ThreadPoolExecutor` 并发调用 Playwright sync API；LLM 点评并发保留，避免 `greenlet` 跨线程错误
- **自测文档路径对齐** — `_test_card_gen.py` README 检查改为优先读取 `docs/README.md`，与当前仓库文档结构保持一致

### Fixed
- **Playwright 页面清理一致化** — `_render_card`、`_render_info_card`、`_render_top3_card`、封面渲染及帖子抓取路径统一使用 `finally` 清理 page/context，减少异常路径资源泄漏
- **Step 4 callback exception** — 修复 `SyncBase._sync.<locals>.<lambda>()` / `greenlet.error: cannot switch to a different thread` 导致的卡片生成尾部异常与卡顿
- **info-card 热评兜底未生效** — 无热评时的“数据亮点” fallback HTML 现在会正确渲染

## [0.9.2] - 2026-06-06

### Added
- **综合评分排序** — `card_gen.py` 新增 `_post_score()` 评分函数，头条/信息图/分组排序从纯回复数改为综合评分：value_tag 权重（限时30>攻略25>避坑20>公告15>实测10>讨论0）+ 回复数(log) + 浏览量(log) + 标题关键词加分（新卡/活动/放水/大毛等），避免高回复低价值帖子被选为头条
- **卡片文章自动联动** — `wechat_article_gen.py` 生成文章前自动检测 `_cards/` 是否有封面和卡片图，缺失则自动触发 `card_gen.main()`，保证数据一致
- **`run.bat`** — 新增 Windows 一键执行脚本，支持命令行指定版次（`run.bat 早报`），自动根据时间判断版次，日志输出到 `logs/` 目录

### Changed
- **Step 2 超时调整** — `run.py` 中 enrich.py 进程超时从 120s → 300s，避免 LLM 富化因网络波动被误杀
- **所有排序统一** — 卡片分组（农行/股份行/其他/全量）排序全部从 `-t["replies"]` 改为 `_post_score`，提升卡片内容质量

### Fixed
- **LLM 点评被模板覆盖** — `card_gen.py` 回写阶段 info_post 的 `_gen_editor_note` 模板会覆盖 top3 已写入的 LLM 点评（同一帖子时）；修复为仅在无 LLM 点评时才用模板补充
- **LLM 点评空内容静默失败** — `_gen_llm_opinion` 新增 reasoning_content fallback（部分模型将内容放在该字段）；空内容时自动重试一次；失败时打印 warning 便于排查

## [0.9.1] - 2026-06-05

### Fixed
- **编辑点评重复** — `card_gen.py` 回写阶段为所有缺失 `editor_note` 的帖子调用 `_gen_llm_opinion()` 补生成 LLM 点评，消除粘贴版文章中 7/10 条帖子编辑点评完全相同的问题

### Added
- **编辑点评回写单元测试** — `test_unit.py` 新增 `TestEditorNoteBackfill`（5 个用例），覆盖缺失补全、已有保留、→ 格式拼接、混合场景

## [0.9.0] - 2026-06-04

### Added
- **RAG 历史知识库集成** — 新增 rag/ 目录，BM25 检索 390 条历史公众号文章
- **编辑点评RAG增强** — card_gen.py _gen_llm_opinion 根据帖子 value_tag 映射搜索分类，注入历史参考到 LLM prompt

### Changed
- **项目结构** — 新增 rag/ 子目录（rag_query.py + articles_kb.json）

## Contract
RAG(rag/) integrates BM25-based historical knowledge base (390 entries) into card_gen.py's _gen_llm_opinion for richer editor notes

## [0.8.0] - 2026-06-04

### Added
- **正文文字化** — `wechat_article_gen.py` v2：每条帖子在图片前展示文字摘要块（wechat_title + summary + value_tag 色块图标 + editor_note），读者无需点开图片即可获取核心信息
- **编辑精选板块** — 文章顶部概览之后新增"✨ 今日编辑精选"卡片，紫色渐变背景，显示当日最热帖的标题+摘要+编辑点评第一句
- **编辑点评全覆盖** — `_post_card()` 对无 editor_note 的帖子自动调用 `_gen_editor_note()` 模板生成，确保每帖都有编辑点评；已有 LLM 点评的帖子优先使用
- **编辑点评回写 enriched** — `card_gen.py` 将 TOP3 和信息图帖子的 LLM 编辑点评写回 `threads_enriched.json`，供文章生成读取
- **公众号粘贴版** — 额外输出 `公众号粘贴版_{ds}.html`，全部使用内联样式，图片标记为"请上传"占位符，全选复制即可贴入微信编辑器

### Changed
- **`wechat_article_gen.py`** — 从 class 式 CSS 全面改为 inline styles（微信编辑器兼容）；文章结构重排：封面→概览→编辑精选→今日提醒→前三甲→全部帖子→CTA
- **`_post_card()`** — 参数不变，输出改为纯内联样式；editor_note 为空时自动用 `_gen_editor_note` 补齐
- **`top3_data`** — 新增 `tid` 字段，用于编辑点评回写匹配

### Removed
- **预览图板块** — 文章正文不再输出 `preview.jpg`（原为精华一瞥），减少无用大图加载

### Added
- **`--edition` 参数** — `run.py` + `enrich.py` 支持 `{早报,晚报}`，默认 12:00 前=早报/后=晚报；文章标题自动切换（`飞客早报 | ...` / `飞客晚报 | ...`）
- **`_clean_quote()`** — 新增 Discuz! 引文块前缀清洗函数，去除 `作者发表于 日期 时间` 前缀
- **引文清洗覆盖** — `_parse_replies` / `fetch_hot_replies_list` / `fetch_post_detail` 三个抓取入口均应用 `_clean_quote`，热评不再显示作者名和时间

### Changed
- **信息图卡片去元信息** — `template-info.html` 删除日期行、银行名、浏览量；仅保留摘要+回复数+热评+编辑点评
- **Top3 卡片去元信息** — `template-top3.html` 删除 `{cn_date}` 日期；meta 行移除 `category_str`（银行名）；`_render_top3_card` 清理未使用的 `cn_date`/`daily_tagline` 变量
- **已更新所有文档** — README / CHANGELOG / 系统规划 / 卡片设计蓝图 同步最新状态

### Changed
- **卡片序列重排** — 输出顺序改为：今日热门→分类精选→前三甲详情→信息图→[全量速览]→封面；高价值内容（top3/info）提前到读者注意力最强的位置
- **分类卡合并** — 农行/股份行/其他合并为单张"分类精选"卡（≤5条），减少卡片总数从 7-9 张降至 4-6 张
- **全量速览按需出卡** — 仅 threads > 10 时生成，帖子少时跳过避免与热门卡重复
- **热门卡精简** — top 6 → top 5，与 top3 详情卡形成差异化
- **封面主标题优化** — 主标题优先使用 LLM 重写的公众号标题（`wechat_title`），fallback 到摘要；副标题改为关键数据（"X 条讨论 · Y 家银行"）
- **编辑点评调优** — LLM prompt 增强：要求引用至少 1 条热评观点、action_tip 包含具体时间节点、禁止"建议关注"等空话；fallback 模板数据化（引用回复数+当前日期）
- **编辑点评函数签名** — `_gen_editor_note(post)` 移除冗余 `replies` 参数，从 post 中自动提取

### Added
- **`wechat_title` 字段** — `enrich.py` 新增公众号风格标题生成（≤22 字，含数字，行动导向），用于封面主标题
- **信息图数据亮点兜底** — 热评为空时显示回复数/浏览量/互动率数据卡，替代"暂无高赞评论"空白
- **`all_posts_meta` 扩展** — 新增 `avg_replies`/`avg_views`/`avg_engagement` 平均值数据，供信息图亮点对比使用

### Fixed
- **prompt 字符串编码** — 修复 `_gen_llm_opinion` 中 ASCII 引号嵌套导致的 SyntaxError（中文引号改为 Unicode 转义）
- **`_gen_editor_note` 冗余替换** — 移除 info_card 中重复的 `{value_tag}` 替换

## [0.5.0] - 2026-06-04

### Added
- **第一卡钩子文案** — 每张分类卡顶部增加板块定制引导语（"今日社区最热的 N 条讨论"等），提升阅读引导
- **热评智能截断** — `_smart_truncate()` 按句号/问号/感叹号截断，不再断在句中
- **单元测试框架** — `test/` 目录，54 个测试用例覆盖核心纯逻辑函数 + Playwright 渲染集成测试
  - `test_unit.py`：`_smart_truncate`、`_int`、`_fmt_bank_name`、`_ds_meta`、`_gen_editor_note`、`_is_waf`、`detect_total_pages`、`build_page_url`、`is_noise`、`filter_threads`、`load_seen`/`save_seen`
  - `test_render.py`：`_render_card`（单条/多条/compact/hook）、`_render_info_card`、`_render_top3_card`、`render_cover`、`gen_preview`、`TAG_COLORS` 一致性

### Changed
- **价值标签视觉强化** — 标签字号 10px→13px，padding 加宽，手机端更易识别
- **TAG_COLORS 提取为模块级常量** — 消除 `_render_card` 和 `_render_top3_card` 中的重复定义
- **预览图精选 3 张** — `gen_preview()` 改为选封面+信息图+top3，不再拼全部卡片

### Fixed
- **`_render_info_card` 临时文件泄漏** — 清理逻辑从 `except` 块移至 `finally` 块，确保每次执行都删除临时 HTML
- **GBK 编码问题** — `summary.py` 删除冗余 `o()` 函数（绕过 reconfigure 的 buffer.write），统一用 `print()`；加 stderr reconfigure；`run.py` 删除 GBK fallback 解码，统一 UTF-8

## [0.4.0] - 2026-06-04

### Changed
- **画布尺寸 1080x1440 → 750x1000** — 适配公众号图片标准宽度（375pt @2x），加载更快
- **编辑点评全面升级** — LLM prompt 注入帖子原文内容，要求引用具体银行名/卡种名/权益细节，不再泛泛而谈
- **`max_tokens` 512 → 4096** — 适配推理模型（reasoning tokens 占用大量预算）
- **模板 fallback 去泛化** — `_gen_editor_note` 每个价值标签都有独立的判断+行动建议模板

### Added
- **`fetch_post_detail()`** — 新增帖子详情页抓取，一次请求同时获取原文正文+热评，避免重复抓取
- **`_ds_meta()`** — 日期元信息生成（vol、中文日期、tagline）
- **公众号图文优化清单** — P0/P1/P2 分级的 12 项图文优化规划

### Fixed
- **info 卡片 `{cn_date}` 未替换** — 模板变量显示为原始文本
- **top3 卡片路径错误** — 相对路径导致 Playwright 截图失败
- **top3 编辑注变量顺序** — `editor_note` 在定义前使用导致 UnboundLocalError

### Removed
- **帖子作者** — 从卡片 meta 行、日报 HTML/Markdown 模板中移除
- **热评作者** — top3 热评数据不再传递 author 字段
- **临时文件清理** — 删除 18 个 `__*.py` 开发文件、12 个调试脚本、`_cards/resources/`、`template-dark.html`

## [0.3.0] - 2026-06-03

### Added
- **卡片字体自动动态调整** — 根据内容长度自动缩放字号，避免溢出
- **信息图卡片重构** — `template-info.html` 新增热评展示 + LLM 编辑点评（RAG 增强）
- **Top3 详情卡** — `template-top3.html` 金牌主题，展示最热帖子的详细内容与热评
- **微信封面图** — `template-cover.html` 16:9 横版封面（1260x540），暗色杂志风
- **预览合集图** — `_cards/preview.jpg` 自动生成卡片缩略图网格
- **分类卡片字体放大** — 竖屏卡片可读性提升
- **LLM 摘要 + 价值标签** — `enrich.py` 调用 LLM API 生成 10 字中文摘要和 6 类价值标签
- **热评抓取** — 抓取 top3 帖子的热门社区评论
- **腾讯 COS 部署脚本** — `deploy_cos.py` + `scf_bootstrap` + `index.py`
- **落地实施方案 v3** — 含 WAF 应对策略、代理配置、GBK 编码处理

## [0.2.0] - 2026-06-02

### Added
- 卡片图生成系统 — `card_gen.py` + HTML 模板 + Playwright 截图
- 模板重设计 — 竖屏 3:4 卡片（带热度条、统计栏、分类色标）
- 日报 HTML 模板 — 移动端适配的响应式布局
- GitHub Pages 部署 — GitHub Actions 自动部署 `日报_*.html`
- Vercel 部署支持

### Changed
- 飞客信用卡日报 2026-06-02 首版上线

## [0.1.0] - 2026-06-01

### Added
- 项目初始化
- `fetcher.py` — 论坛抓取（Playwright + BeautifulSoup）
- `summary.py` — 关键词规则分类 + Markdown/HTML 日报渲染
- `run.py` — 一键编排流水线
- 帖子去重（`seen_tids.json`）
- 低质帖过滤规则

- **Hot ranking category semantics** - Hot posts render as full cross-category detail cards, are removed from category sections, and are counted once to prevent duplicate content and links.
