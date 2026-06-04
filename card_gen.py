# -*- coding: utf-8 -*-
"""手机竖屏卡片图 v2 (3:4 | P0 优化: 统计栏+银行标签+热力条+底部CTA+紧凑排版)"""
import sys, os, json, httpx
from datetime import date
from pathlib import Path
from collections import Counter

# 统一配置
import settings
cwd = settings.CWD
LLM_OK = settings.LLM_OK
LLM_KEY = settings.LLM_KEY
LLM_BASE = settings.LLM_BASE
LLM_MODEL = settings.LLM_MODEL

CARD_W, CARD_H = settings.CARD_W, settings.CARD_H
BRANDING = settings.BRANDING
OUT_DIR = settings.OUT_DIR

PALETTES = {
    "hot":      {"accent":"#dc2626","bg":"#fef2f2","fg":"#991b1b","bar":"#fca5a5",
                 "header_start":"#0f172a","header_end":"#1e293b"},
    "农行":     {"accent":"#16a34a","bg":"#f0fdf4","fg":"#166534","bar":"#86efac",
                 "header_start":"#14532d","header_end":"#166534"},
    "股份行":   {"accent":"#2563eb","bg":"#eff6ff","fg":"#1e40af","bar":"#93c5fd",
                 "header_start":"#1e3a5f","header_end":"#2563eb"},
    "国有行":   {"accent":"#7c3aed","bg":"#f5f3ff","fg":"#5b21b6","bar":"#c4b5fd",
                 "header_start":"#4c1d95","header_end":"#6d28d9"},
    "速览":     {"accent":"#78716c","bg":"#f5f5f4","fg":"#44403c","bar":"#d6d3d1",
                 "header_start":"#44403c","header_end":"#57534e"},
}

TAG_COLORS = {
    "限时": "#dc2626", "避坑": "#ea580c", "攻略": "#16a34a",
    "公告": "#2563eb", "讨论": "#78716c", "实测": "#7c3aed",
}

# ── Playwright 浏览器复用 ──
_PW = None
_BROWSER = None

def _ensure_browser():
    """获取共享浏览器实例（首次启动，后续复用）"""
    global _PW, _BROWSER
    if _BROWSER:
        return _BROWSER
    from playwright.sync_api import sync_playwright
    _PW = sync_playwright().start()
    _BROWSER = _PW.chromium.launch(headless=True)
    return _BROWSER

def _new_page(viewport=None):
    """从共享浏览器创建新页面（调用方需 _close_page(page)）"""
    b = _ensure_browser()
    ctx = b.new_context()
    pg = ctx.new_page()
    if viewport:
        pg.set_viewport_size(viewport)
    # 把 context 挂到 page 上，close 时一起清理
    pg._ctx = ctx
    return pg

def _close_page(page):
    """关闭页面及其 context"""
    try:
        ctx = getattr(page, '_ctx', None)
        if ctx:
            ctx.close()
    except:
        pass
    try:
        page.close()
    except:
        pass

def _close_browser():
    """关闭共享浏览器"""
    global _PW, _BROWSER
    if _BROWSER:
        try: _BROWSER.close()
        except: pass
        _BROWSER = None
    if _PW:
        try: _PW.stop()
        except: pass
        _PW = None


def _smart_truncate(text, max_len=150):
    """按句子边界智能截断，避免断在句中"""
    if len(text) <= max_len:
        return text
    # 在 max_len 范围内找最后一个完整句子结尾
    for i in range(min(max_len, len(text)) - 1, max(max_len - 40, 0), -1):
        if text[i] in "。！？…":
            return text[:i + 1]
    return text[:max_len] + "…"

def _clean_quote(text):
    """清理 Discuz! 引用块前缀：'作者发表于 日期 时间'"""
    import re
    # 匹配 "XXX 发表于 YYYY-M-D HH:MM" 或 "XXX发表于 YYYY-M-D HH:MM" 前缀
    text = re.sub(r'^[^\s]*?\s*发表于\s+\d{4}[\d-]+\s+\d{1,2}:\d{2}\s*', '', text)
    return text

TPL_SRC = (cwd / "template.html").read_text(encoding="utf-8")


def _render_card(posts, ds, total, palette, idx, section, branding,
                 bank_count, hot_bank, top_replies, global_max_r=None, compact=False):
    """渲染一张卡片 — 字号随帖子数动态调整"""
    max_r = global_max_r or max((t.get("replies", 0) for t in posts), default=1)

    # 动态字号：帖子越少字越大，保证手机阅读（750宽适配）
    n = len(posts)
    if compact:
        title_fs, sub_fs, meta_fs = 22, 18, 18
    elif n <= 2:
        title_fs, sub_fs, meta_fs = 26, 22, 20
    elif n <= 4:
        title_fs, sub_fs, meta_fs = 24, 20, 19
    elif n <= 6:
        title_fs, sub_fs, meta_fs = 23, 19, 18
    else:
        title_fs, sub_fs, meta_fs = 22, 18, 18

    posts_html = []
    for t in posts:
        r = t.get("replies", 0)
        title = t.get("title", "")
        cat = t.get("category", "")
        summary = t.get("summary", "")
        vt = t.get("value_tag", "")
        pct = min(r / max_r * 100, 100) if max_r > 0 else 0
        is_hot = r >= 20
        title_cls = ' class="hot-title"' if is_hot else ""

        has_summary = summary and summary != title[:len(summary)]
        tag_cls = ""
        if vt and vt != "讨论":
            tc = TAG_COLORS.get(vt, "#78716c")
            tag_cls = f' style="background:{tc};color:#fff;position:absolute;top:12px;right:12px;font-size:13px;font-weight:700;padding:2px 10px;border-radius:4px;"'

        posts_html.append('<div class="post">')
        if has_summary:
            # 有摘要：摘要作为主行，原标题作为副行
            posts_html.append(f'<div class="left-bar"></div>')
            if vt and vt != "讨论":
                posts_html.append(f'<span{tag_cls}>{vt}</span>')
            posts_html.append(f'<div class="title" style="font-size:{title_fs}px;font-weight:700;color:#0f172a;line-height:1.45;margin-bottom:2px;padding-right:56px;">{summary}</div>')
            posts_html.append(f'<div class="title" style="font-size:{sub_fs}px;font-weight:400;color:#64748b;line-height:1.4;margin-bottom:5px;padding-right:56px;">&#x2192; {title}</div>')
        else:
            posts_html.append(f'<div class="left-bar"></div>')
            if cat:
                posts_html.append(f'<span class="tag">{cat}</span>')
            posts_html.append(f'<div{title_cls} style="font-size:{title_fs}px;padding-right:60px;">{title}</div>')

        posts_html.append(
            f'<div class="meta" style="display:flex;align-items:center;gap:12px;font-size:{meta_fs}px;color:#94a3b8;">'
            f'<span class="replies" style="color:var(--accent,{palette["accent"]});font-weight:700;">{r} 回复</span>'
            f'<div class="heat-track" style="flex:1;height:4px;background:#e5e7eb;border-radius:2px;max-width:80px;overflow:hidden;">'
            f'<div class="heat-fill" style="height:100%;background:var(--accent,{palette["accent"]});border-radius:2px;width:{pct:.0f}%;"></div></div>'
            f'</div></div>'
        )

    posts_joined = "\n".join(posts_html)

    hot_bank_short = hot_bank[:2] if len(hot_bank) > 4 else hot_bank

    header_grad = f"linear-gradient(135deg,{palette['header_start']} 0%,{palette['header_end']} 60%,{palette['header_start']} 100%)"

    extra_cls = " compact" if compact else ""
    tmp = cwd / f"__card_{idx}.html"
    html = TPL_SRC
    html = html.replace("{w}", str(CARD_W))
    html = html.replace("{h}", str(CARD_H))
    html = html.replace("{accent}", palette["accent"])
    html = html.replace("{bar}", palette["bar"])
    html = html.replace("{header_grad}", header_grad)
    html = html.replace("{ds}", ds)
    html = html.replace("{total}", str(total))
    html = html.replace("{bank_count}", str(bank_count))
    html = html.replace("{top_replies}", str(top_replies))
    html = html.replace("{hot_bank}", hot_bank_short)
    html = html.replace("{posts_html}", posts_joined)
    html = html.replace("{section}", section)
    html = html.replace("{branding}", branding)
    html = html.replace("{extra_cls}", extra_cls)

    # 钩子文案：第一张卡用强引导，其余按板块定制
    HOOKS = {
        "今日热门": f"今日社区最热的 {n} 条讨论，别错过",
        "分类精选": "各银行热门帖子精选",
        "全量速览": "今日全部热帖一览",
    }
    html = html.replace("{hook}", HOOKS.get(section, "今日精选"))
    tmp.write_text(html, encoding="utf-8")
    out = OUT_DIR / f"card_{idx:02d}.png"

    try:
        page = _new_page(viewport={"width": CARD_W, "height": CARD_H})
        page.goto(tmp.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out), full_page=True)
        _close_page(page)
        return True, out
    except Exception as e:
        return False, str(e)
    finally:
        if tmp.exists(): tmp.unlink()


def _int(v):
    try: return int(v)
    except: return 0


def _fmt_bank_name(name):
    """缩短银行名: '中国农业银行' -> '农业银行'"""
    return name.replace("中国", "") if "中国" in name else name


def fetch_hot_replies(tid, max_items=4):
    """抓取帖子详情页，提取有价值回复，返回 HTML 片段或空字符串"""
    import time, re
    url = "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=%s" % tid
    proxy = "http://127.0.0.1:10808"

    def _parse_replies(html):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        NOISE_KW = ["收", "代", "85折", "商务舱", "广告", "推广"]
        replies = []
        for post_div in soup.find_all("div", id=re.compile(r"^(post_|pid_)")):
            pid = post_div.get("id", "")
            if pid == "post_%s" % tid:
                continue  # 跳过主帖
            text_el = post_div.select_one(".t_f, .postmessage, .message, td.t_f")
            if not text_el:
                continue
            content = text_el.get_text(strip=True)
            content = _clean_quote(content)
            if len(content) < 12:
                continue
            if any(kw in content for kw in NOISE_KW):
                continue
            author_el = post_div.select_one("a.poster_t, .authi a.xw1, .authi a")
            author = author_el.get_text(strip=True) if author_el else "卡友"
            replies.append({"author": author, "content": _smart_truncate(content, 180)})
        return replies

    try:
        pg = _new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        import time; time.sleep(1)
        html = pg.content()
        _close_page(pg)
        if not html or "403 Forbidden" in html[:200]:
            return ""
        replies = _parse_replies(html)
    except Exception:
        return ""

    if not replies:
        return ""

    # 去重：相似内容只保留一条
    seen = set()
    deduped = []
    for r in replies:
        key = r["content"][:30]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    # 取前 max_items 条
    items = deduped[:max_items]
    if not items:
        return ""

    parts = []
    for r in items:
        parts.append(
            '<div class="hr-item"><span class="hr-text">%s</span></div>'
            % _smart_truncate(r["content"], 150)
        )
    return "\n".join(parts)


def fetch_hot_replies_list(tid, max_items=2):
    """Return [{author, content}, ...] for top3 cards"""
    import re, time
    url = "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=%s" % tid
    try:
        pg = _new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        html = pg.content()
        _close_page(pg)
        if not html or "403 Forbidden" in html[:200]:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        NOISE_KW = ["收", "代", "85折", "商务舱", "广告", "推广"]
        replies = []
        for post_div in soup.find_all("div", id=re.compile(r"^(post_|pid_)")):
            pid = post_div.get("id", "")
            if pid == "post_%s" % tid:
                continue
            text_el = post_div.select_one(".t_f, .postmessage, .message, td.t_f")
            if not text_el:
                continue
            content = text_el.get_text(strip=True)
            content = _clean_quote(content)
            if len(content) < 12:
                continue
            if any(kw in content for kw in NOISE_KW):
                continue
            author_el = post_div.select_one("a.poster_t, .authi a.xw1, .authi a")
            author = author_el.get_text(strip=True) if author_el else "卡友"
            replies.append({"author": author, "content": _smart_truncate(content, 180)})
        seen = set()
        deduped = []
        for r in replies:
            key = r["content"][:30]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        return deduped[:max_items]
    except Exception:
        return []

def fetch_post_detail(tid):
    """抓取帖子详情页，返回 (main_content, hot_replies_list)
    main_content: 帖子正文（最多800字）
    hot_replies_list: [{content}, ...]
    """
    import time, re
    url = "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=%s" % tid
    try:
        pg = _new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        html = pg.content()
        _close_page(pg)
        if not html or "403 Forbidden" in html[:200]:
            return "", []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        NOISE_KW = ["收", "代", "85折", "商务舱", "广告", "推广"]

        main_content = ""
        replies = []
        first_post = True
        for post_div in soup.find_all("div", id=re.compile(r"^post_\d")):
            text_el = post_div.select_one(".t_f, .postmessage, .message, td.t_f")
            if not text_el:
                continue
            content = text_el.get_text(strip=True)
            if first_post:
                # 第一个 post_* div 就是主帖
                main_content = content[:800]
                first_post = False
                continue
            content = _clean_quote(content)
            # 回复
            if len(content) < 12:
                continue
            if any(kw in content for kw in NOISE_KW):
                continue
            replies.append({"content": _smart_truncate(content, 200)})

        # 去重
        seen = set()
        deduped = []
        for r in replies:
            key = r["content"][:30]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)

        return main_content, deduped[:4]
    except Exception:
        return "", []


def _render_info_card(post, ds, palette, branding, all_posts_meta, hot_replies_html="", hot_replies_raw=None, card_idx=6):
    """渲染信息图卡片（第 6 张），可选 hot_replies（纯 .hr-item HTML，不含外层容器）"""
    replies = int(post.get("replies", 0))
    views = int(post.get("views", 0))
    summary = post.get("summary", post["title"][:12])
    title = post.get("title", "")
    bank = post.get("category", "其他")
    vt = post.get("value_tag", "讨论")

    # 浏览数格式化
    views_display = f"{views:,}" if views >= 1000 else str(views)
    views_label = "%s 次浏览" % views_display

    # 编辑总结 — LLM+RAG 优先，降级到模
    if hot_replies_raw:
        rag_text = "\n".join(r["content"][:200] for r in hot_replies_raw)
        editor_summary, editor_footnote = _gen_llm_opinion(post, rag_text)
    else:
        editor_summary, editor_footnote = _gen_editor_note(post)

    header_grad = f"linear-gradient(135deg,{palette['header_start']} 0%,{palette['header_end']} 60%,{palette['header_start']} 100%)"

    tpl = (cwd / "template-info.html").read_text(encoding="utf-8")

    # 如果 hot_replies 为空，显示数据亮点
    if not hot_replies_html:
        # 计算数据亮点
        avg_replies = all_posts_meta.get("avg_replies", 0)
        avg_views = all_posts_meta.get("avg_views", 0)
        engagement = (views / replies * 100) if replies > 0 else 0
        avg_engagement = all_posts_meta.get("avg_engagement", 0)

        highlights = []
        # 回复数对比
        if avg_replies > 0:
            ratio = replies / avg_replies
            if ratio >= 1.5:
                highlights.append(f'<div class="dh-item"><span class="dh-icon">🔥</span><span class="dh-label">回复数</span><span class="dh-value">{replies} 条</span><span class="dh-label">，高于均值 {ratio:.1f}x</span></div>')
            else:
                highlights.append(f'<div class="dh-item"><span class="dh-icon">💬</span><span class="dh-label">回复数</span><span class="dh-value">{replies} 条</span></div>')
        else:
            highlights.append(f'<div class="dh-item"><span class="dh-icon">💬</span><span class="dh-label">回复数</span><span class="dh-value">{replies} 条</span></div>')

        # 浏览数
        highlights.append(f'<div class="dh-item"><span class="dh-icon">👀</span><span class="dh-label">浏览量</span><span class="dh-value">{views_display}</span></div>')

        # 互动率
        if engagement > 0:
            if avg_engagement > 0 and engagement > avg_engagement * 1.2:
                highlights.append(f'<div class="dh-item"><span class="dh-icon">📈</span><span class="dh-label">互动率</span><span class="dh-value">{engagement:.0f}%</span><span class="dh-label">，高于均值</span></div>')
            else:
                highlights.append(f'<div class="dh-item"><span class="dh-icon">📊</span><span class="dh-label">互动率</span><span class="dh-value">{engagement:.0f}%</span></div>')

        hot_replies = '<div class="data-highlights">' + "\n".join(highlights) + '</div>'

    html = tpl
    html = html.replace("{w}", str(CARD_W))
    html = html.replace("{h}", str(CARD_H))
    html = html.replace("{accent}", palette["accent"])
    html = html.replace("{accent_light}", palette["bar"])
    html = html.replace("{bg_color}", palette["bg"])
    html = html.replace("{footer_bg}", palette["bg"])
    html = html.replace("{header_grad}", header_grad)
    html = html.replace("{ds}", ds)
    _, cn_date, _ = _ds_meta(ds)
    html = html.replace("{cn_date}", cn_date)
    html = html.replace("{replies}", str(replies))
    html = html.replace("{summary}", summary)
    html = html.replace("{title}", title)
    html = html.replace("{views_label}", views_label)
    html = html.replace("{bank}", bank)
    html = html.replace("{value_tag}", vt)
    html = html.replace("{hot_replies_placeholder}", hot_replies_html)
    html = html.replace("{editor_summary}", editor_summary)
    html = html.replace("{editor_footnote}", editor_footnote)
    html = html.replace("{branding}", branding)

    tmp = cwd / f"__card_info.html"
    tmp.write_text(html, encoding="utf-8")
    out = OUT_DIR / f"card_{card_idx:02d}.png"

    try:
        page = _new_page(viewport={"width": CARD_W, "height": CARD_H})
        page.goto(tmp.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out), full_page=True)
        _close_page(page)
        return True, out
    except Exception as e:
        return False, str(e)
    finally:
        if tmp.exists(): tmp.unlink()

WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
MONTHS_CN = ["", "一月", "二月", "三月", "四月", "五月", "六月",
             "七月", "八月", "九月", "十月", "十一月", "十二月"]

def _ds_meta(ds):
    """返回 (vol, cn_date, daily_tagline)"""
    from datetime import date as _date
    d = _date.fromisoformat(ds)
    vol = f"VOL.{d.year}.{d.month:02d}.{d.day:02d}"
    cn_date = f"{d.month}月{d.day}日 {WEEKDAYS_CN[d.weekday()]}"
    daily_tagline = "DAILY · 晚报"
    return vol, cn_date, daily_tagline


def _render_top3_card(top3, ds, total, branding):
    """Render top3 detail card with gold theme"""
    vol, _, _ = _ds_meta(ds)
    RANK_EMOJI = {0: "\U0001F947", 1: "\U0001F948", 2: "\U0001F949"}
    RANK_CLS = {0: "r1", 1: "r2", 2: "r3"}
    posts_html = []
    for i, p in enumerate(top3):
        rank_emoji = RANK_EMOJI[i]; rank_cls = RANK_CLS[i]
        vt = p.get("value_tag", "")
        vt_color = TAG_COLORS.get(vt, "#78716c")
        vt_html = f'<span class="vt-badge" style="background:{vt_color};color:#fff;">{vt}</span>' if vt and vt != "讨论" else ""
        replies_str = f'<span class="replies">{p["replies"]} 回复</span>'
        hot_html = ""
        for r in p.get("hot_replies", []):
            hot_html += f'<div class="hot-reply">\U0001F4AC "{r["content"]}"</div>'
        editor_note = p.get("editor_note", "")
        editor_html = f'<div class="editor-note"><span class="label">编辑</span> {editor_note}</div>' if editor_note else ""
        posts_html.append(
            f'<div class="post">'
            f'<div class="rank-badge {rank_cls}">{rank_emoji}</div>'
            f'<div class="title">{p.get("summary") or p["title"]}</div>'
            f'<div class="meta">{vt_html} {replies_str}</div>'
            f'{hot_html}{editor_html}'
            f'</div>'
        )
    posts_joined = "\n".join(posts_html)
    from pathlib import Path as _P
    tpl = _P("template-top3.html").read_text(encoding="utf-8")
    html = tpl.replace("{w}", str(CARD_W)).replace("{h}", str(CARD_H))
    html = html.replace("{vol}", vol)
    html = html.replace("{posts_html}", posts_joined)
    html = html.replace("{branding}", branding)
    tmp = cwd / "__card_top3.html"; tmp.write_text(html, encoding="utf-8")
    out = cwd / "_cards" / "card_top3.png"
    try:
        page = _new_page(viewport={"width": CARD_W, "height": CARD_H})
        page.goto(tmp.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.screenshot(path=str(out), full_page=True)
        _close_page(page)
        return True, out
    except Exception as e:
        return False, str(e)
    finally:
        if tmp.exists(): tmp.unlink()

def _gen_editor_note(post):
    """根据帖子信息生成编辑总结"""
    title = post.get("title", "")
    vt = post.get("value_tag", "讨论")
    bank = post.get("category", "其他")
    reply_count = post.get("replies", 0)
    from datetime import date as _date
    today = _date.today()
    month = today.month
    day = today.day

    # 不同价值标签的编辑点评模板 — 引用数据 + 具体时间节点
    notes = {
        "限时": (
            f"「{title[:20]}」有时效性，{reply_count} 条回复说明关注度高。窗口一过就没了，符合条件的今天就上车。",
            f"截止日期以官方公告为准，建议{month}月{day}日内完成操作。"
        ),
        "避坑": (
            f"「{title[:20]}」社区 {reply_count} 条讨论，踩坑反馈不少。别急着操作，先确认自身情况。",
            f"建议对照自身卡种和地区再决定，{month}月底前确认是否适用。"
        ),
        "攻略": (
            f"「{title[:20]}」操作路径清晰，{reply_count} 条回复已验证可行性。按步骤来就行。",
            f"实操前截图保存步骤，本周内完成最佳。"
        ),
        "公告": (
            f"「{title[:20]}」银行政策调整，{reply_count} 条讨论说明影响面广。直接影响持卡权益，别等客服通知。",
            f"建议{month}月{day}日起对比调整前后差异，评估是否影响用卡计划。"
        ),
        "实测": (
            f"「{title[:20]}」真人实测数据，{reply_count} 条回复佐证。比官方宣传靠谱，但个体差异存在。",
            "参考其方法论而非具体数字，因地制宜。"
        ),
        "讨论": (
            f"「{title[:20]}」{reply_count} 条回复热度不低，说明这事确实纠结。核心看你的消费场景。",
            "别被极端观点带偏，结合自身需求做判断。"
        ),
    }
    summary, footnote = notes.get(vt, notes["讨论"])

    # 如果是典型"怎么选"类帖子，给出更具体的总结
    how_to_choose = ["怎么选", "如何选", "vs", "还是", "选择"]
    if any(kw in title for kw in how_to_choose):
        # 尝试从标题提取两个选项
        opts = [x.strip() for x in title.replace("？","").replace("?","").replace("和","|").replace("还是","|").replace("vs","|").replace("VS","|").split("|") if len(x.strip()) > 1]
        if len(opts) >= 2:
            summary = f"社区对该话题讨论激烈，双方各有拥趸。结合热评反馈，倾向选 %s 的偏多。" % opts[0]
            footnote = f"短期权益看 %s，长期持有成本看 %s。建议先算年费再决定。" % (opts[0], opts[1])

    return summary, footnote


def _gen_llm_opinion(post, hot_replies_text, post_content=""):
    """用 LLM 生成有观点的编辑点评 + 行动建议。失败时回退到模板"""
    if not LLM_OK:
        return _gen_editor_note(post)
    title = post.get("title", "")
    category = post.get("category", "")
    replies = post.get("replies", 0)
    summary = post.get("summary", "")
    content_block = f"帖子原文：\n{post_content[:600]}\n\n" if post_content else ""
    rag_ctx = hot_replies_text[:800] if hot_replies_text else "暂无热评"
    today = date.today().strftime("%m月%d日")
    prompt = (
        "你是信用卡论坛日报编辑，风格犀利、观点鲜明，不说废话。\n"
        "你必须仔细阅读帖子原文和社区热评，理解帖子核心内容后再给出判断。\n\n"
        f"标题：{title}\n"
        f"分类：{category}\n"
        f"摘要：{summary}\n"
        f"回复数：{replies}\n"
        f"今天：{today}\n\n"
        f"{content_block}"
        f"社区热评：\n{rag_ctx}\n\n"
        "要求：\n"
        "- opinion：先概括帖子核心内容（什么银行、什么卡种、什么权益/活动），再给出你的判断（推荐/谨慎/观望/避开），20-40字\n"
        "- action_tip：读者下一步具体该做什么（时间节点+动作），15-30字\n"
        "- 必须引用原文中的具体信息（银行名、卡种名、权益细节、截止日期等），不要泛泛而谈\n"
        "- 必须引用至少 1 条热评中的具体观点（用引号标注），如「有卡友反馈...」\n"
        "- action_tip 要包含具体时间节点（如\u201c今天内\u201d、\u201c本周五前\u201d、\u201c6月底前\u201d），不要说\u201c建议关注\u201d\n"
        "- 不要重复标题，要输出标题里没有的增量信息\n"
        "- 禁止出现\u201c建议关注\u201d、\u201c值得关注\u201d、\u201c可以了解\u201d等空话\n\n"
        "返回 JSON，不要多余文字：\n"
        '{"opinion": "...", "action_tip": "..."}'
    )
    try:
        with httpx.Client(timeout=30) as x:
            r = x.post(
                f"{LLM_BASE}/chat/completions",
                json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 4096,
                },
                headers={"Authorization": f"Bearer {LLM_KEY}"},
            )
            r.raise_for_status()
            ct = r.json()["choices"][0]["message"]["content"].strip()
            if ct.startswith("```"):
                ct = ct.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            d = json.loads(ct)
            opinion = d.get("opinion", "")
            action_tip = d.get("action_tip", "")
            if opinion and action_tip:
                return opinion, action_tip
    except Exception:
        pass
    return _gen_editor_note(post)

def render_cover(info_post, ds, total, bank_count, hot_bank, top_replies, branding,
                 article_title=None, article_desc=None):
    """生成公众号 16:9 封面卡片"""
    summary = info_post.get("summary", info_post["title"][:12])
    title = info_post.get("title", "")
    wechat_title = info_post.get("wechat_title", "")
    value_tag = info_post.get("value_tag", "讨论")
    replies = info_post.get("replies", 0)
    # 用 hot 色系作为封面 accent
    accent = PALETTES["hot"]["accent"]

    # 主标题：优先用文章级标题，其次 wechat_title，再 fallback 到摘要
    cover_title = article_title or (wechat_title if wechat_title else summary)
    # 副标题：优先用文章摘要，否则用关键数据
    cover_subtitle = article_desc or f"{replies} 条讨论 · {bank_count} 家银行"

    tpl = (cwd / "template-cover.html").read_text(encoding="utf-8")
    html = tpl
    html = html.replace("{ds}", ds)
    html = html.replace("{total}", str(total))
    html = html.replace("{bank_count}", str(bank_count))
    html = html.replace("{hot_bank}", hot_bank[:4])
    html = html.replace("{top_replies}", str(top_replies))
    html = html.replace("{summary}", cover_title)
    html = html.replace("{subtitle}", cover_subtitle)
    html = html.replace("{value_tag}", value_tag)
    html = html.replace("{replies}", str(replies))
    html = html.replace("{accent}", accent)
    html = html.replace("{branding}", branding)

    tmp = cwd / "__cover.html"
    tmp.write_text(html, encoding="utf-8")
    out = OUT_DIR / "cover_wechat.png"
    try:
        page = _new_page(viewport={"width": 1200, "height": 675})
        page.goto(tmp.as_uri(), wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(out), full_page=True)
        _close_page(page)
        return out
    except Exception:
        return None
    finally:
        if tmp.exists(): tmp.unlink()
def gen_preview():
    """精选 3 张最有吸引力的卡片拼预览图（封面 + info + top3）"""
    from PIL import Image
    # 优先选：cover > info_card(06/07) > top3 > 其余按编号
    candidates = []
    for name in ["cover_wechat.png", "card_top3.png"]:
        p = OUT_DIR / name
        if p.exists():
            candidates.append(p)
    # info card 通常是最大的编号（非 top3/cover）
    info_cards = sorted(
        [c for c in OUT_DIR.glob("card_*.png")
         if c.name not in ("card_top3.png",)],
        key=lambda x: x.name, reverse=True
    )
    if info_cards and info_cards[0] not in candidates:
        candidates.append(info_cards[0])
    # 补齐到 3 张
    for c in sorted(OUT_DIR.glob("card_*.png")):
        if len(candidates) >= 3:
            break
        if c not in candidates:
            candidates.append(c)
    cards = candidates[:3]
    if not cards:
        return None

    imgs = [Image.open(c) for c in cards]
    thumb_w, thumb_h = 240, 320
    thumbs = [img.resize((thumb_w, thumb_h), Image.LANCZOS) for img in imgs]

    gap = 8
    canvas_w = 3 * thumb_w + 2 * gap
    canvas_h = thumb_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 35))

    for i, thumb in enumerate(thumbs):
        x = i * (thumb_w + gap)
        canvas.paste(thumb, (x, 0))

    out = OUT_DIR / "preview.jpg"
    canvas.save(out, quality=88)
    return out


def main():
    data_path = cwd / "threads_filtered.json"
    if not data_path.exists():
        print("[-] 没有数据文件, 先跑 fetcher.py")
        return
    with open(data_path, encoding="utf-8") as f:
        threads = json.load(f)
    if not threads:
        print("[-] 数据为空")
        return

    # 尝试加载 LLM enriched 缓存（summary + value_tag + wechat_title + article）
    enriched_path = cwd / "threads_enriched.json"
    article_meta = None
    if enriched_path.exists():
        cached = json.loads(enriched_path.read_text(encoding="utf-8"))
        # 新格式：{"posts": [...], "article": {...}}
        if isinstance(cached, dict) and "posts" in cached:
            posts_cache = cached["posts"]
            article_meta = cached.get("article", None)
        else:
            posts_cache = cached  # 旧格式：直接是数组
        cmap = {t["tid"]: t for t in posts_cache if "summary" in t and "value_tag" in t}
        for t in threads:
            if t["tid"] in cmap:
                t["summary"] = cmap[t["tid"]]["summary"]
                t["value_tag"] = cmap[t["tid"]]["value_tag"]
                if "wechat_title" in cmap[t["tid"]]:
                    t["wechat_title"] = cmap[t["tid"]]["wechat_title"]

    for t in threads:
        t["replies"] = _int(t.get("replies", 0))
        t["views"] = _int(t.get("views", 0))
        t["category"] = _fmt_bank_name(t.get("category", ""))

    ds = date.today().isoformat()
    total = len(threads)
    OUT_DIR.mkdir(exist_ok=True)

    # 全局统计
    all_banks = [t.get("category", "其他") for t in threads]
    bank_counter = Counter(all_banks)
    bank_count = len(bank_counter)
    hot_bank = bank_counter.most_common(1)[0][0] if bank_counter else "—"
    top_replies = max(t["replies"] for t in threads)
    max_views = max(t["views"] for t in threads)
    avg_replies = sum(t["replies"] for t in threads) / len(threads) if threads else 0
    avg_views = sum(t["views"] for t in threads) / len(threads) if threads else 0
    avg_engagement = sum((t["views"] / t["replies"] * 100 if t["replies"] > 0 else 0) for t in threads) / len(threads) if threads else 0
    all_posts_meta = {"max_replies": top_replies, "max_views": max_views,
                      "avg_replies": avg_replies, "avg_views": avg_views, "avg_engagement": avg_engagement}

    # 按回复数降序
    threads.sort(key=lambda t: -t["replies"])

    # 分组
    hot = threads[:5]
    remaining = [t for t in threads if t not in hot]
    banks = {}
    for t in remaining:
        b = t.get("category", "其他")
        banks.setdefault(b, []).append(t)

    agri = banks.pop("农业银行", [])[:6]
    joint_stock = []
    for b in ["招商银行", "交通银行", "浦发银行", "平安银行", "兴业银行"]:
        if b in banks:
            joint_stock.extend(banks.pop(b))
    joint_stock.sort(key=lambda t: -t["replies"])

    # 低于阈值的帖子归入"更多讨论"池
    others_pool = []
    if len(agri) < 2:
        others_pool.extend(agri)
        agri = []
    if len(joint_stock) < 2:
        others_pool.extend(joint_stock)
        joint_stock = []
    # 更多讨论池 = 剩余银行 + 不足阈值回流的帖子
    for b in list(banks.keys()):
        others_pool.extend(banks.pop(b))
    others_pool.sort(key=lambda t: -t["replies"])
    others = others_pool[:6]

    all_compact = threads[:8]

    # 动态构建卡片列表：低于门槛的卡自动跳过
    # 合并农行/股份行/其他为"分类精选"，减少卡片数量
    category_posts = agri + joint_stock + others
    category_posts.sort(key=lambda t: -t["replies"])
    category_posts = category_posts[:5]  # 最多 5 条

    cards_data = []
    cards_data.append(("hot",   "今日热门",   hot,         PALETTES["hot"]))
    if category_posts:
        cards_data.append(("cat",   "分类精选",   category_posts, PALETTES["速览"]))
    if len(threads) > 10:
        cards_data.append(("速览", "全量速览",   all_compact, PALETTES["国有行"]))

    idx = 0
    ok_count = 0
    for key, name, posts, palette in cards_data:
        if not posts:
            continue
        idx += 1
        compact = (key == "速览")
        print(f"[{idx}] {name} ({len(posts)} 条)...", end=" ", flush=True)
        ok, res = _render_card(
            posts, ds, total, palette, idx, name, BRANDING,
            bank_count, hot_bank, top_replies, global_max_r=top_replies,
            compact=compact,
        )
        if ok:
            ok_count += 1
            print(f"OK -> {res.name}")
        else:
            print(f"FAIL: {res}")

    # ★ 前三甲详情卡片（提前到第 2 位）
    idx += 1
    print(f"\n[{idx}] 前三甲详情...", end=" ", flush=True)
    top3_posts = threads[:3]
    top3_data = []
    for i, p in enumerate(top3_posts):
        print("原文+热评...", end="", flush=True)
        main_content, replies = fetch_post_detail(p["tid"])
        hot_entries = [{"content": _smart_truncate(r["content"], 120)} for r in replies]
        rag_text = "\n".join(r["content"] for r in replies)
        opinion, action_tip = _gen_llm_opinion(p, rag_text, post_content=main_content)
        top3_data.append({
            "title": p["title"], "author": p.get("author", ""),
            "replies": p.get("replies", 0), "summary": p.get("summary", ""),
            "value_tag": p.get("value_tag", ""), "category": p.get("category", ""),
            "hot_replies": hot_entries,
            "editor_note": opinion + " → " + action_tip,
        })
        print(" 原文%d字 %d条" % (len(main_content), len(hot_entries)), end=" " if i < 2 else "")
    ok, res = _render_top3_card(top3_data, ds, total, BRANDING)
    if ok:
        ok_count += 1
        print("OK -> %s" % res.name)
    else:
        print("FAIL: %s" % res)

    # ★ 信息图卡片：选取当天最有信息量的帖子
    idx += 1
    info_post = threads[0]  # 回复数最高
    print(f"[{idx}] 信息图 (%s...)..." % info_post["title"][:20], end=" ", flush=True)

    # 抓取社区热评
    print("热评...", end="", flush=True)
    hot_replies_html = fetch_hot_replies(info_post["tid"])
    hot_replies_raw = fetch_hot_replies_list(info_post["tid"], max_items=4)
    if hot_replies_html:
        print(" %d 条" % hot_replies_html.count("hr-item"), end=" ", flush=True)
    else:
        print(" 无", end=" ", flush=True)

    info_bank = info_post.get("category", "其他")
    # 找对应银行的 palette，fallback 到 hot
    info_palette = PALETTES.get(info_bank.replace("银行", ""), PALETTES["hot"])
    if info_bank in [k for k in PALETTES]:
        info_palette = PALETTES[info_bank]
    elif "农" in info_bank or "农业" in info_bank:
        info_palette = PALETTES["农行"]
    else:
        info_palette = PALETTES["hot"]
    ok, res = _render_info_card(info_post, ds, info_palette, BRANDING, all_posts_meta,
                                hot_replies_html=hot_replies_html, hot_replies_raw=hot_replies_raw,
                                card_idx=idx)
    if ok:
        ok_count += 1
        print("OK -> %s" % res.name)
    else:
        print("FAIL: %s" % res)

    print("")
    # 公众号封面
    cover = render_cover(info_post, ds, total, bank_count, hot_bank, top_replies, BRANDING,
                         article_title=article_meta.get("article_title") if article_meta else None,
                         article_desc=article_meta.get("article_desc") if article_meta else None)
    if cover:
        print("  公众号封面 -> %s" % cover.name)
    else:
        print("  公众号封面 FAIL")

    # 合并预览图
    preview = gen_preview()
    if preview:
        print("  合并预览 -> %s" % preview.name)

    print("\n完成! %d 张 -> %s/" % (ok_count, OUT_DIR))
    _close_browser()


if __name__ == "__main__":
    main()
