# -*- coding: utf-8 -*-
"""手机竖屏卡片图 v2 (3:4 | P0 优化: 统计栏+银行标签+热力条+底部CTA+紧凑排版)"""
import sys, os, json
from datetime import date
from pathlib import Path
from collections import Counter

cwd = Path(__file__).parent
os.chdir(str(cwd))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CARD_W, CARD_H = 1080, 1440
BRANDING = "@moat成长"
OUT_DIR = cwd / "_cards"

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

TPL_SRC = (cwd / "template.html").read_text(encoding="utf-8")


def _render_card(posts, ds, total, palette, idx, section, branding,
                 bank_count, hot_bank, top_replies, global_max_r=None, compact=False):
    """渲染一张卡片"""
    max_r = global_max_r or max((t.get("replies", 0) for t in posts), default=1)

    # value_tag 颜色映射
    TAG_COLORS = {
        "限时": "#dc2626", "避坑": "#ea580c", "攻略": "#16a34a",
        "公告": "#2563eb", "讨论": "#78716c", "实测": "#7c3aed",
    }

    posts_html = []
    for t in posts:
        r = t.get("replies", 0)
        title = t.get("title", "")
        author = t.get("author", "")
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
            tag_cls = f' style="background:{tc};color:#fff;position:absolute;top:12px;right:12px;font-size:10px;font-weight:700;padding:1px 8px;border-radius:4px;"'

        posts_html.append('<div class="post">')
        if has_summary:
            # 有摘要：摘要作为主行，原标题作为副行
            posts_html.append(f'<div class="left-bar"></div>')
            if vt and vt != "讨论":
                posts_html.append(f'<span{tag_cls}>{vt}</span>')
            posts_html.append(f'<div class="title" style="font-size:15px;font-weight:700;color:#0f172a;line-height:1.5;margin-bottom:2px;padding-right:56px;">{summary}</div>')
            posts_html.append(f'<div class="title" style="font-size:12px;font-weight:400;color:#64748b;line-height:1.4;margin-bottom:5px;padding-right:56px;">&#x2192; {title}</div>')
        else:
            posts_html.append(f'<div class="left-bar"></div>')
            if cat:
                posts_html.append(f'<span class="tag">{cat}</span>')
            posts_html.append(f'<div{title_cls} style="padding-right:60px;">{title}</div>')

        posts_html.append(
            f'<div class="meta" style="display:flex;align-items:center;gap:12px;font-size:12px;color:#94a3b8;">'
            f'<span class="replies" style="color:var(--accent,{palette["accent"]});font-weight:700;">{r} 回复</span>'
            f'<span>{author}</span>'
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
    tmp.write_text(html, encoding="utf-8")
    out = OUT_DIR / f"card_{idx:02d}.png"

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": CARD_W, "height": CARD_H})
            page.goto(tmp.as_uri(), wait_until="networkidle")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(out), full_page=True)
            browser.close()
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
            if len(content) < 12:
                continue
            if any(kw in content for kw in NOISE_KW):
                continue
            author_el = post_div.select_one("a.poster_t, .authi a.xw1, .authi a")
            author = author_el.get_text(strip=True) if author_el else "卡友"
            replies.append({"author": author, "content": content[:180]})
        return replies

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context()
            pg = ctx.new_page()
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            html = pg.content()
            browser.close()
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

    parts = ['<div class="hot-reviews"><div class="hr-label">&#x1f4ac; 社区热评</div>']
    for r in items:
        parts.append(
            '<div class="hr-item"><span class="hr-author">%s</span>'
            '<span class="hr-text">%s</span></div>'
            % (r["author"], r["content"][:150])
        )
    parts.append("</div>")
    return "".join(parts)


def _render_info_card(post, ds, palette, branding, all_posts_meta, hot_replies="", card_idx=6):
    """渲染信息图卡片（第 6 张），可选 hot_replies HTML 片段"""
    replies = int(post.get("replies", 0))
    views = int(post.get("views", 0))
    summary = post.get("summary", post["title"][:12])
    title = post.get("title", "")
    author = post.get("author", "")
    bank = post.get("category", "其他")
    vt = post.get("value_tag", "讨论")

    # 热度百分比（基于回复数在当天所有帖子中的排名）
    max_r = all_posts_meta["max_replies"]
    max_v = all_posts_meta["max_views"]
    heat_pct = min(100, int((replies / max_r * 0.6 + views / max_v * 0.4) * 100))
    heat_pct = max(10, heat_pct)  # 最低 10%，太低了不好看

    # 浏览数格式化
    views_display = f"{views:,}" if views >= 1000 else str(views)
    views_label = "%s 次浏览" % views_display

    header_grad = f"linear-gradient(135deg,{palette['header_start']} 0%,{palette['header_end']} 60%,{palette['header_start']} 100%)"

    tpl = (cwd / "template-info.html").read_text(encoding="utf-8")

    html = tpl
    html = html.replace("{w}", str(CARD_W))
    html = html.replace("{h}", str(CARD_H))
    html = html.replace("{accent}", palette["accent"])
    html = html.replace("{accent_light}", palette["bar"])
    html = html.replace("{bg_color}", palette["bg"])
    html = html.replace("{footer_bg}", palette["bg"])
    html = html.replace("{header_grad}", header_grad)
    html = html.replace("{gold}", "#fbbf24")
    html = html.replace("{ds}", ds)
    html = html.replace("{replies}", str(replies))
    html = html.replace("{summary}", summary)
    html = html.replace("{title}", title)
    html = html.replace("{heat_pct}", str(heat_pct))
    html = html.replace("{views_label}", views_label)
    html = html.replace("{views_display}", views_display)
    html = html.replace("{bank}", bank)
    html = html.replace("{author}", author)
    html = html.replace("{value_tag}", vt)
    html = html.replace("{hot_replies}", hot_replies)
    html = html.replace("{branding}", branding)

    tmp = cwd / f"__card_info.html"
    tmp.write_text(html, encoding="utf-8")
    out = OUT_DIR / f"card_{card_idx:02d}.png"

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": CARD_W, "height": CARD_H})
            page.goto(tmp.as_uri(), wait_until="networkidle")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(out), full_page=True)
            browser.close()
        return True, out
    except Exception as e:
        return False, str(e)
        if tmp.exists(): tmp.unlink()


def render_cover(info_post, ds, total, bank_count, hot_bank, top_replies, branding):
    """生成公众号 16:9 封面卡片"""
    summary = info_post.get("summary", info_post["title"][:12])
    title = info_post.get("title", "")
    value_tag = info_post.get("value_tag", "讨论")
    replies = info_post.get("replies", 0)
    # 用 hot 色系作为封面 accent
    accent = PALETTES["hot"]["accent"]

    tpl = (cwd / "template-cover.html").read_text(encoding="utf-8")
    html = tpl
    html = html.replace("{ds}", ds)
    html = html.replace("{total}", str(total))
    html = html.replace("{bank_count}", str(bank_count))
    html = html.replace("{hot_bank}", hot_bank[:4])
    html = html.replace("{top_replies}", str(top_replies))
    html = html.replace("{summary}", summary)
    html = html.replace("{title}", title)
    html = html.replace("{value_tag}", value_tag)
    html = html.replace("{replies}", str(replies))
    html = html.replace("{accent}", accent)
    html = html.replace("{branding}", branding)

    tmp = cwd / "__cover.html"
    tmp.write_text(html, encoding="utf-8")
    out = OUT_DIR / "cover_wechat.png"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 675})
            page.goto(tmp.as_uri(), wait_until="networkidle")
            page.wait_for_timeout(800)
            page.screenshot(path=str(out), full_page=True)
            browser.close()
        return out
    except Exception:
        return None
    finally:
        if tmp.exists(): tmp.unlink()


def gen_preview():
    """合并所有卡片为 3x2 预览图"""
    from PIL import Image
    cards = sorted(OUT_DIR.glob("card_*.png"))
    if not cards:
        return None

    # 确定列数：6 张用 3x2，5 张用 3x2(最后一列空)，4 张用 2x2，3 张用 3x1
    n = len(cards)
    cols = 3 if n >= 3 else 2
    rows = (n + cols - 1) // cols

    imgs = [Image.open(c) for c in cards]
    # 统一缩放为小图
    thumb_w, thumb_h = 240, 320
    thumbs = [img.resize((thumb_w, thumb_h), Image.LANCZOS) for img in imgs]

    # 画布
    gap = 8
    canvas_w = cols * thumb_w + (cols - 1) * gap
    canvas_h = rows * thumb_h + (rows - 1) * gap
    canvas = Image.new("RGB", (canvas_w, canvas_h), (30, 30, 35))

    for i, thumb in enumerate(thumbs):
        r, c = divmod(i, cols)
        x = c * (thumb_w + gap)
        y = r * (thumb_h + gap)
        canvas.paste(thumb, (x, y))

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

    # 尝试加载 LLM enriched 缓存（summary + value_tag）
    enriched_path = cwd / "threads_enriched.json"
    if enriched_path.exists():
        cached = json.loads(enriched_path.read_text(encoding="utf-8"))
        cmap = {t["tid"]: t for t in cached if "summary" in t and "value_tag" in t}
        for t in threads:
            if t["tid"] in cmap:
                t["summary"] = cmap[t["tid"]]["summary"]
                t["value_tag"] = cmap[t["tid"]]["value_tag"]

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
    all_posts_meta = {"max_replies": top_replies, "max_views": max_views}

    # 按回复数降序
    threads.sort(key=lambda t: -t["replies"])

    # 分组
    hot = threads[:6]
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
    cards_data = []
    cards_data.append(("hot",   "今日热门",   hot,         PALETTES["hot"]))
    if agri:
        cards_data.append(("农行",   "农业银行",   agri,        PALETTES["农行"]))
    if joint_stock:
        cards_data.append(("股份行", "股份行精选", joint_stock, PALETTES["股份行"]))
    if len(others) >= 3:
        cards_data.append(("其他",   "更多讨论",   others,      PALETTES["速览"]))
    cards_data.append(("速览",   "全量速览",   all_compact, PALETTES["国有行"]))

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


    # ★ 信息图卡片（第 6 张）：选取当天最有信息量的帖子
    info_post = threads[0]  # 回复数最高
    print("[6] 信息图 (%s...)..." % info_post["title"][:20], end=" ", flush=True)

    # 抓取社区热评
    print("热评...", end="", flush=True)
    hot_replies = fetch_hot_replies(info_post["tid"])
    if hot_replies:
        print(" %d 条" % hot_replies.count("hr-item"), end=" ", flush=True)
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
    ok, res = _render_info_card(info_post, ds, info_palette, BRANDING, all_posts_meta, hot_replies, card_idx=idx + 1)
    if ok:
        ok_count += 1
        print("OK -> %s" % res.name)
    else:
        print("FAIL: %s" % res)

    print("")
    # 公众号封面
    cover = render_cover(info_post, ds, total, bank_count, hot_bank, top_replies, BRANDING)
    if cover:
        print("  公众号封面 -> %s" % cover.name)
    else:
        print("  公众号封面 FAIL")

    # 合并预览图
    preview = gen_preview()
    if preview:
        print("  合并预览 -> %s" % preview.name)

    print("\n完成! %d 张 -> %s/" % (ok_count, OUT_DIR))


if __name__ == "__main__":
    main()
