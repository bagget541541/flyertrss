# Changelog

All notable changes to this project will be documented in this file.

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
