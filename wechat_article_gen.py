# -*- coding: utf-8 -*-
"""公众号文章生成 — 将卡片贴图+文章元数据组装为可直接发布的 HTML"""
import json, os, sys
from pathlib import Path
from datetime import date

cwd = Path(__file__).parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = cwd / "_cards"
ARTICLE_DIR = cwd  # 文章输出到根目录

# 文章 CSS — 模拟公众号手机阅读效果
ARTICLE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;background:#f5f5f5;color:#1a1a1a;padding:0;max-width:640px;margin:0 auto;line-height:1.8}
.article{background:#fff;padding:20px 16px 30px}
.article-title{font-size:20px;font-weight:700;line-height:1.4;margin-bottom:8px;color:#1a1a1a}
.article-meta{font-size:13px;color:#999;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #eee}
.article-desc{font-size:14px;color:#666;margin-bottom:20px;padding:12px 14px;background:#f8f9fa;border-radius:8px;line-height:1.6}
.card-section{margin-bottom:24px}
.card-section h3{font-size:15px;font-weight:600;color:#333;margin-bottom:10px;padding-left:10px;border-left:3px solid #6366f1}
.card-section img{display:block;width:100%;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,0.08)}
.card-caption{font-size:12px;color:#999;margin-top:6px;text-align:center}
.cta{margin-top:24px;padding:16px;background:linear-gradient(135deg,#0f172a,#1e293b);border-radius:10px;text-align:center;color:#fff}
.cta p{font-size:14px;font-weight:500;margin-bottom:4px}
.cta .sub{font-size:11px;color:#94a3b8}
"""

def gen_article():
    # 读取 enriched 数据（文章元数据）
    enriched_path = cwd / "threads_enriched.json"
    if not enriched_path.exists():
        print("[-] 没有 enriched 数据，先跑 enrich.py")
        return

    raw = json.loads(enriched_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "posts" in raw:
        posts = raw["posts"]
        article = raw.get("article", {})
    else:
        posts = raw
        article = {}

    article_title = article.get("article_title", f"飞客晚报 | {date.today().isoformat()}")
    article_desc = article.get("article_desc", f"今日 {len(posts)} 条讨论")
    ds = article.get("date", date.today().isoformat())
    edition = article.get("edition", "晚报")
    total = article.get("total_posts", len(posts))
    bank_count = article.get("bank_count", "—")
    hot_bank = article.get("hot_bank", "—")

    # 取 top3 帖子的标题（正文中使用）
    top3 = []
    for p in posts[:3]:
        top3.append({
            "title": p.get("title", ""),
            "summary": p.get("summary", ""),
            "wechat_title": p.get("wechat_title", ""),
            "value_tag": p.get("value_tag", ""),
            "replies": p.get("replies", "?"),
        })

    # 检查卡片图片是否存在
    cover = OUT_DIR / "cover_wechat.png"
    card_top3 = OUT_DIR / "card_top3.png"
    card_files = sorted(OUT_DIR.glob("card_0*.png"))

    if not cover.exists():
        print("[-] 封面图不存在，先跑 card_gen.py")
        return

    # 构造卡片引用路径（相对根目录，GitHub Pages 友好）
    def img_path(p):
        return str(p.relative_to(cwd)).replace("\\", "/")

    # 构建文章 body
    body_parts = []

    # 封面
    body_parts.append(f'''<div class="card-section">
  <img src="{img_path(cover)}" alt="封面">
</div>''')

    # 今日概览
    top_replies = article.get("top_replies", "—")
    body_parts.append(f'''<div class="article-desc">
  📊 <strong>今日概览</strong> — {bank_count} 家银行共 {total} 条讨论，
  最热帖 {top_replies} 条回复
</div>''')

    # 前三甲
    if top3:
        top3_html = '<div class="card-section"><h3>🏆 前三甲详情</h3><ul style="padding-left:20px;font-size:14px;margin-bottom:10px">'
        for i, p in enumerate(top3, 1):
            wt = p.get("wechat_title") or p.get("summary") or p["title"]
            tag = p.get("value_tag", "")
            tag_badge = f'<span style="background:#6366f1;color:#fff;font-size:10px;padding:1px 6px;border-radius:3px;margin-right:6px">{tag}</span>' if tag else ""
            top3_html += f'<li style="margin-bottom:6px;line-height:1.5">{tag_badge}<strong>{p["title"][:25]}</strong> <span style="color:#999;font-size:12px">({p["replies"]} 回复)</span></li>'
        top3_html += "</ul>"
        if card_top3.exists():
            top3_html += f'<img src="{img_path(card_top3)}" alt="前三甲">'
        top3_html += "</div>"
        body_parts.append(top3_html)

    # 分类卡片
    body_parts.append('<div class="card-section"><h3>📋 分类精选</h3>')
    for cf in card_files:
        body_parts.append(f'  <img src="{img_path(cf)}" alt="卡片" style="margin-bottom:12px">')
    body_parts.append("</div>")

    # 预览图
    preview = OUT_DIR / "preview.jpg"
    body_parts.append('<div class="card-section"><h3>📸 精华一瞥</h3>')
    if preview.exists():
        body_parts.append(f'  <img src="{img_path(preview)}" alt="预览">')
    body_parts.append("</div>")

    # CTA
    body_parts.append(f'''<div class="cta">
  <p>关注 <strong>飞客信用卡日报</strong></p>
  <div class="sub">每日获取信用卡圈最新情报 · {ds}</div>
</div>''')

    body_html = "\n".join(body_parts)

    # 完整文章 HTML
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>{article_title}</title>
<meta name="description" content="{article_desc}">
<meta property="og:title" content="{article_title}">
<meta property="og:description" content="{article_desc}">
<meta property="og:image" content="{img_path(cover)}">
<style>{ARTICLE_CSS}</style>
</head>
<body>
<div class="article">
  <div class="article-title">{article_title}</div>
  <div class="article-meta">{ds} · {total} 条讨论</div>
  {body_html}
</div>
</body>
</html>'''

    fn = ARTICLE_DIR / f"公众号文章_{ds}.html"
    fn.write_text(html, encoding="utf-8")
    print(f"[OK] 公众号文章 -> {fn}")

    # 同时输出元数据 JSON（方便外部使用）
    meta_fn = ARTICLE_DIR / f"公众号元数据_{ds}.json"
    meta = {
        "title": article_title,
        "description": article_desc,
        "date": ds,
        "edition": edition,
        "total_posts": total,
        "bank_count": bank_count,
        "hot_bank": hot_bank,
        "top_replies": article.get("top_replies", ""),
        "cover_image": img_path(cover),
        "card_images": [img_path(f) for f in card_files],
        "top3_image": img_path(card_top3) if card_top3.exists() else "",
        "preview_image": img_path(preview) if preview.exists() else "",
    }
    meta_fn.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 公众号元数据 -> {meta_fn}")

    # 输出文章标题+摘要摘要（可直接复制到公众号后台）
    print(f"\n{'='*45}")
    print(f"📰 文章标题: {article_title}")
    print(f"📝 文章摘要: {article_desc}")
    print(f"🖼️  封面图: {img_path(cover)}")
    print(f"📋 卡片图:  {len(card_files)} 张")
    print(f"{'='*45}")

if __name__ == "__main__":
    gen_article()
