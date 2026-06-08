# 卡片模板 QA 修复计划

> 基于 `image_qa_0607.md` 审查报告，2026-06-07

## 设计决策

- **封面模板风格**：以浅蓝渐变（#E6F2FF → #F0F8FF）为标准，其他卡片向其靠拢
- **字体标准**：统一无衬线体（思源黑体 / Inter Tight），禁止回退到宋体

---

## F1: template.html（热门列表卡片，图1-4）✅ 已完成

| # | 改动 | 状态 |
|---|------|------|
| F1.1 | `.post .title` font-size: 18px → 20px | ✅ |
| F1.2 | `.hot-title::before` margin-right: 6px → 10px | ✅ |
| F1.3 | `.compact .post` padding: 16px 0 → 20px 0 | ✅ |
| F1.4 | `.footer` padding: 16px → 20px | ✅ |
| F1.5 | `.stat-label` color: 0.7 → 0.85 | ✅ |

---

## F2: template-info.html（社区热评卡片，图5）✅ Phase 1 完成

| # | 改动 | 优先级 | 状态 |
|---|------|--------|------|
| F2.1 | `.hr-item` font-size: 13px → 14px, line-height: 1.5 → 1.6 | P0 | ✅ |
| F2.2 | `.s-footnote` font-size: 12px → 14px | P0 | ✅ |
| F2.3 | body font-family 确保 sans-serif 优先 | P1 | ✅ 已是 |
| F2.4 | `.stat-label` color: 0.7 → 0.85 | P1 | ✅ |
| F2.5 | `.hr-item` margin-bottom: 6px → 10px | P2 | ✅ |

---

## F3: template-top3.html（TOP3 榜单，图6）✅ Phase 1 完成

| # | 改动 | 优先级 | 状态 |
|---|------|--------|------|
| F3.1 | `.stat-label` color: 0.7 → 0.85 | P1 | ✅ |
| F3.2 | `.post` margin-bottom: 6px → 10px | P2 | ✅ |
| F3.3 | `.vt-badge` margin-right: 0 → 6px | P2 | ✅ |

---

## F4: template-cover-43.html（4:3 封面，图7）✅ Phase 1 完成

| # | 改动 | 优先级 | 状态 |
|---|------|--------|------|
| F4.1 | `.brand` / `.content` padding-left: 32px → 36px | P1 | ✅ |
| F4.2 | `.title` margin-bottom: 8px → 16px | P2 | ✅ |
| F4.3 | `.footer-strip` padding-bottom: 20px → 26px | P2 | ✅ |
| F4.4 | 统一浅蓝渐变背景为标准（已是） | — | 已是标准 |

---

## F5: template-cover.html（微信封面，图8）

| # | 改动 | 优先级 | 状态 |
|---|------|--------|------|
| F5.1 | `.title` margin-bottom: 6px → 14px | P2 | ✅ |
| F5.2 | `.footer-strip` padding-bottom: 22px → 28px | P2 | ✅ |

---

## F6: card_gen.py（Python 内联样式）

| # | 改动 | 优先级 | 状态 |
|---|------|--------|------|
| F6.1 | `title_fs` 18 → 20 | P1 | ✅ |
| F6.2 | 确认 info-card 回复字号由模板控制 | P1 | ✅ 已是 |

---

## F7: info-card 银行 logo（方案 C）✅ 已完成

| # | 改动 | 优先级 | 状态 |
|---|------|--------|------|
| F7.1 | 创建 `_assets/banks/` 目录，19 个银行 SVG 占位 logo + default | P1 | ✅ |
| F7.2 | card_gen.py 添加 `BANK_LOGO_MAP` + `_get_bank_logo()` | P1 | ✅ |
| F7.3 | template-info.html `.title-area` 添加 `.bank-badge`（logo + bank name） | P1 | ✅ |
| F7.4 | `_render_info_card` 传递 `{bank_logo}` 路径 | P1 | ✅ |

**设计说明：**
- 银行 logo 为 SVG 圆形色块 + 首字缩写，后续可替换为真实 logo 图片
- 显示位置：标题上方，32x32px logo + 13px 银行名
- 匹配逻辑：复用现有 `_detect_bank` → `BANK_PATTERNS` → `_fmt_bank_name` 链路
- 文件映射：`BANK_LOGO_MAP` 字典，bank_name → SVG 文件名

---

## 执行阶段

### Phase 1（P0-P1）— ✅ 已完成
- F2.1-F2.4: template-info.html 回复字号 + 字体 + 对比度 ✅
- F3.1: template-top3.html 对比度 ✅
- F4.1: template-cover-43.html 左侧 padding ✅
- F6.2: card_gen.py 确认 ✅
- F7.1-F7.4: info-card 银行 logo ✅

### Phase 2（P2）— ✅ 已完成
- F2.5, F3.2: 卡片间距 ✅
- F4.2, F4.3, F5.1, F5.2: 封面标题间距 + 底部 padding ✅
- F3.3: HOT 标签间距 ✅

### Phase 3（P3）— ✅ 已完成
- F3.1: card_gen.py `.heat-fill` opacity: 0.5 ✅
- A03: 方案 C，两种设计语言并存，不做统一
- A04: QA 误判，侧边栏结构已一致，无需改动
- A05: 封面与列表卡片类型不同，布局差异合理
- F01: info-card 银行 logo（方案 C）✅

### Phase 4（2026-06-07）— ✅ 已完成

基于 `image_qa_0607.md` 深度审查报告。

| # | 问题 | 改动 | 文件 |
|---|------|------|------|
| B01 | info-card 热评字号 | 已是 14px，无需改 | — |
| B02 | 编辑点评对比度 | 已是 #0f172a，无需改 | — |
| B03 | cover 主副标题层级 | 副标题缩小：4:3 17→15px, 16:9 16→14px | template-cover-43/cover.html |
| B04 | 列表回复数对比度 | replies weight 600→700, 新增 font-size:14px | template.html |
| D01 | 列表间距过密 | .post padding 24→28px | template.html |
| D02 | 行内文字黏连 | 已是 line-height:1.5，无需改 | — |
| D03 | QA 深度检查已否决 | — | — |
| D04 | sidebar 留白不均 | 统一 padding 32px 16px 32px（4个模板） | template*.html |
| D05 | 评论气泡内边距 | .hr-item padding 8px 12px→10px 14px, margin-bottom 10→12px | template-info.html |
| D06 | cover 标题数据间距 | 已合理，无需改 | — |
| E01 | stats bar 层次 | .num 18px/700→20px/800, .lab 12px/#666→11px/#999 | template.html |
| A04 | 银行标签统一 | 当前实现已一致，无需改 | — |

### 性能优化（2026-06-07）

| # | 改动 | 文件 |
|---|------|------|
| P-1 | top3 帖子详情抓取×3 + LLM点评×3 改 ThreadPoolExecutor 并发 | card_gen.py |
| P-2 | info-card 热评 fetch_hot_replies + fetch_hot_replies_list 并发 | card_gen.py |
| P-3 | enrich.py LLM 调用失败自动重试 1 次 | enrich.py |
| P-4 | run.py step_timeout enrich/card_gen 300→900s | run.py |
| P-5 | template-top3.html 修复 `` `n `` 语法错误 | template-top3.html |

**后续修正（2026-06-08）：**
- Playwright sync API 在线程池抓取详情/热评时触发 `greenlet.error: cannot switch to a different thread`。
- 因此 `fetch_post_detail`、`fetch_hot_replies`、`fetch_hot_replies_list` 已回退为串行调用；LLM 点评并发保留。
- 同步补充了 page/context `finally` 清理，修复 Step 4 尾部 callback exception 与卡顿。
