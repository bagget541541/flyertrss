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
