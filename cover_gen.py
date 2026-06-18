# -*- coding: utf-8 -*-
"""轻量封面生成器 — 只生成 cover_wechat.png（+ cover_43.png），不生成任何卡片
   简易模式：用 PIL 直接渲染（无需 Playwright / 无浏览器依赖）
"""
import sys; sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json, math
from datetime import date
from pathlib import Path
from collections import Counter

from PIL import Image, ImageDraw, ImageFont

import settings
cwd = settings.CWD
OUT_DIR = settings.OUT_DIR
BRANDING = settings.BRANDING

# ── 查找系统字体 ──
_FONT_DIR = Path("C:/Windows/Fonts")
_FONT_CANDIDATES = [
    ("msyhbd.ttc", "Microsoft YaHei Bold"),   # 微软雅黑粗体
    ("msyh.ttc", "Microsoft YaHei"),           # 微软雅黑
    ("simhei.ttf", "SimHei"),                  # 黑体
    ("simsun.ttc", "SimSun"),                  # 宋体
]
_FONT_REG = None
_FONT_BOLD = None
for _fn, _name in _FONT_CANDIDATES:
    _fp = _FONT_DIR / _fn
    if _fp.exists():
        try:
            _FONT_BOLD = ImageFont.truetype(str(_fp), 36)
            _FONT_REG = ImageFont.truetype(str(_fp), 22)
            break
        except Exception:
            continue
if _FONT_BOLD is None:
    _FONT_BOLD = ImageFont.load_default()
    _FONT_REG = ImageFont.load_default()
    _FONT_TITLE = _FONT_BOLD
else:
    # 主标题用 42pt，从同一字体文件加载
    try:
        _FONT_TITLE = ImageFont.truetype(str(_FONT_BOLD.path), 42)
    except Exception:
        _FONT_TITLE = _FONT_BOLD


def _draw_gradient(draw, w, h, c1="#0f172a", c2="#1e293b"):
    """绘制线性渐变背景"""
    def _hex_to_rgb(hx):
        hx = hx.lstrip("#")
        return tuple(int(hx[i:i+2], 16) for i in (0, 2, 4))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    for y in range(h):
        t = y / h
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _render_cover_pil(info_post, ds, total, bank_count, hot_bank, top_replies,
                      branding, article_title=None, article_desc=None):
    """用 PIL 生成封面图（1200x675，16:9），无需 Playwright"""
    W, H = 1200, 675

    # 提取数据
    title = info_post.get("title", "飞客信用卡日报")
    summary = info_post.get("summary", title[:12])
    wechat_title = info_post.get("wechat_title", "")
    replies = info_post.get("replies", 0)
    value_tag = info_post.get("value_tag", "讨论")
    cover_title = wechat_title or (article_title.replace("飞客早报 | ", "").replace("飞客晚报 | ", "") if article_title else "") or summary
    if len(cover_title) > 22:
        cover_title = cover_title[:20] + "…"
    cover_subtitle = article_desc or f"{replies} 条讨论 · {bank_count} 家银行"
    hot_bank_short = hot_bank[:4] if len(hot_bank) > 4 else hot_bank

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # 渐变背景：浅蓝（蓝白风格，与 template-cover.html 一致）
    _draw_gradient(draw, W, H, "#e0f2fe", "#f0f9ff")

    # 品牌标题
    draw.text((40, 28), "飞客", fill="#0f172a", font=_FONT_BOLD)
    draw.text((40 + _FONT_BOLD.getbbox("飞客")[2], 28), "信用卡日报", fill="#2563eb", font=_FONT_BOLD)

    # 右上角日期+统计
    meta_text = f"{ds}  |  {total} 条讨论 · {bank_count} 家银行"
    meta_bbox = _FONT_REG.getbbox(meta_text)
    draw.text((W - 40 - meta_bbox[2], 34), meta_text, fill="#94a3b8", font=_FONT_REG)

    # 标签 + 回复数
    tag_badge_colors = {"限时": "#dc2626", "避坑": "#ea580c", "攻略": "#16a34a",
                        "公告": "#2563eb", "实测": "#7c3aed", "讨论": "#78716c"}
    tag_color = tag_badge_colors.get(value_tag, "#78716c")
    badge_x = 48
    badge_y = 160
    # 标签色块
    tag_text = f"  {value_tag}  "
    tag_bbox = _FONT_REG.getbbox(tag_text)
    draw.rounded_rectangle(
        [(badge_x, badge_y), (badge_x + tag_bbox[2] + 16, badge_y + tag_bbox[3] + 8)],
        radius=4, fill=tag_color
    )
    draw.text((badge_x + 8, badge_y + 4), tag_text, fill="#ffffff", font=_FONT_REG)

    # 回复数
    view_text = f"★ 最热帖 · {replies} 回复"
    draw.text((badge_x + tag_bbox[2] + 32, badge_y + 4), view_text, fill="#94a3b8", font=_FONT_REG)

    # 主标题
    draw.text((48, 230), cover_title, fill="#0f172a", font=_FONT_TITLE)

    # 副标题
    draw.text((48, 290), cover_subtitle, fill="#64748b", font=_FONT_REG)

    # 统计区
    stats = [
        ("今日最热", str(top_replies)),
        ("有动静", str(bank_count)),
        ("热点", hot_bank_short),
    ]
    stat_x = 48
    stat_y = 360
    for label, value in stats:
        draw.text((stat_x, stat_y), value, fill="#2563eb", font=_FONT_BOLD)
        draw.text((stat_x, stat_y + 38), label, fill="#64748b", font=_FONT_REG)
        stat_x += 140

    # 二维码
    qr_path = cwd / "qr_code.jpg"
    if qr_path.exists():
        try:
            qr = Image.open(qr_path).convert("RGBA").resize((90, 90))
            # 右下角
            img.paste(qr, (W - 120, H - 140), qr)
        except Exception:
            pass

    # 底部条
    draw.line([(0, H - 50), (W, H - 50)], fill="#d1d5db", width=1)
    draw.text((40, H - 40), f"关注 {branding} 每日获取信用卡情报", fill="#64748b", font=_FONT_REG)

    # 输出
    out = OUT_DIR / "cover_wechat.png"
    img.save(out, quality=95)
    return out


def main():
    enriched_path = cwd / "threads_enriched.json"
    if not enriched_path.exists():
        print("[-] 没有 enriched 数据，先跑 enrich.py")
        return

    raw = json.loads(enriched_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "posts" in raw:
        posts = raw["posts"]
        article_meta = raw.get("article", {})
    else:
        posts = raw
        article_meta = {}

    if not posts:
        print("[-] enriched 数据为空，跳过封面生成")
        return

    # 基础统计
    from card_gen import _int, _fmt_bank_name, _detect_bank, _post_score
    for t in posts:
        t["replies"] = _int(t.get("replies", 0))
        t["views"] = _int(t.get("views", 0))
        raw_cat = t.get("category", "")
        t["category"] = _fmt_bank_name(_detect_bank(t.get("title", ""), category=raw_cat))

    ds = date.today().isoformat()
    total = len(posts)
    OUT_DIR.mkdir(exist_ok=True)

    all_banks = [t.get("category", "其他") for t in posts]
    bank_counter = Counter(all_banks)
    bank_count = len(bank_counter)
    hot_bank = bank_counter.most_common(1)[0][0] if bank_counter else "—"
    top_replies = max(t["replies"] for t in posts)

    posts_sorted = sorted(posts, key=_post_score, reverse=True)
    info_post = posts_sorted[0]

    print(f"  封面帖: {info_post.get('title', '')[:30]}...")
    print(f"  统计: {total} 条, {bank_count} 家银行, 最热 {top_replies} 回复")

    # 用 PIL 生成封面（无需 Playwright）
    cover = _render_cover_pil(
        info_post, ds, total, bank_count, hot_bank, top_replies, BRANDING,
        article_title=article_meta.get("article_title") if article_meta else None,
        article_desc=article_meta.get("article_desc") if article_meta else None,
    )
    if cover and cover.exists():
        print(f"  OK -> {cover.name} ({cover.stat().st_size / 1024:.0f} KB)")
    else:
        print("  FAIL: cover_wechat.png 生成失败")


if __name__ == "__main__":
    main()
