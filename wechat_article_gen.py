# -*- coding: utf-8 -*-
"""公众号文章生成 — 将卡片贴图+文章元数据组装为可直接发布的 HTML
   v2: 正文文字化，每条帖子在图片前展示文字摘要块"""
import json, os, sys, re
from pathlib import Path
from datetime import date

cwd = Path(__file__).parent
sys.path.insert(0, str(cwd))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import settings
OUT_DIR = settings.OUT_DIR
ARTICLE_DIR = settings.ARTICLE_DIR

# 从 card_gen 复用模板化编辑点评
from card_gen import _gen_editor_note

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
/* 帖子文字摘要块 */
.post-card{background:#f8fafc;border-radius:8px;padding:12px 14px;margin-bottom:10px;border:1px solid #e5e7eb}
.post-card .tag{display:inline-block;font-size:10px;font-weight:700;padding:1px 7px;border-radius:3px;color:#fff;margin-right:6px}
.post-card .tag-限时{background:#dc2626}
.post-card .tag-避坑{background:#ea580c}
.post-card .tag-攻略{background:#16a34a}
.post-card .tag-公告{background:#2563eb}
.post-card .tag-实测{background:#7c3aed}
.post-card .tag-讨论{background:#78716c}
.post-card .title{font-size:15px;font-weight:600;color:#0f172a;margin-top:4px;line-height:1.4}
.post-card .meta{font-size:12px;color:#94a3b8;margin-top:3px}
.post-card .summary{font-size:13px;color:#475569;margin-top:4px;line-height:1.5}
.post-card .editor{font-size:12px;color:#6366f1;margin-top:6px;padding:6px 10px;background:#eef2ff;border-radius:6px;line-height:1.5}
.cta{margin-top:24px;padding:16px;background:linear-gradient(135deg,#0f172a,#1e293b);border-radius:10px;text-align:center;color:#fff}
.cta p{font-size:14px;font-weight:500;margin-bottom:4px}
.cta .sub{font-size:11px;color:#94a3b8}
"""

TAG_ICON = {"限时": "⏰", "避坑": "🚫", "攻略": "📖", "公告": "📢", "实测": "🔬", "讨论": "💬"}
TAG_BG = {"限时": "#dc2626", "避坑": "#ea580c", "攻略": "#16a34a", "公告": "#2563eb", "实测": "#7c3aed", "讨论": "#78716c"}


def _post_card(p):
    """生成一条帖子的文字摘要块 HTML，自动补齐编辑点评"""
    tag = p.get("value_tag", "讨论")
    icon = TAG_ICON.get(tag, "💬")
    wechat_title = p.get("wechat_title", "")
    summary = p.get("summary", "")
    title = p.get("title", "")
    replies = p.get("replies", "?")

    # 编辑点评：已有则用，没有则模板生成
    editor_note = p.get("editor_note", "")
    if not editor_note:
        note_summary, note_footnote = _gen_editor_note(p)
        editor_note = note_summary + (" → " + note_footnote if note_footnote else "")

    display_title = wechat_title or summary or title[:20]
    post_url = p.get("url", "")
    tag_bg = TAG_BG.get(tag, "#78716c")
    tag_html = f'<span style="display:inline-block;font-size:10px;font-weight:700;padding:1px 7px;border-radius:3px;color:#fff;background:{tag_bg};margin-right:6px">{tag}</span>'
    summary_html = f'<div style="font-size:13px;color:#475569;margin-top:4px;line-height:1.5">{summary}</div>' if summary and summary != display_title else ""
    editor_html = f'<div style="font-size:12px;color:#6366f1;margin-top:6px;padding:6px 10px;background:#eef2ff;border-radius:6px;line-height:1.5">📝 {editor_note}</div>' if editor_note else ""
    link_html = f'<div style="margin-top:6px"><a href="{post_url}" style="font-size:12px;color:#6366f1;text-decoration:none">🔗 查看原帖</a></div>' if post_url else ""

    return f'''<div style="background:#f8fafc;border-radius:8px;padding:12px 14px;margin-bottom:10px;border:1px solid #e5e7eb">
  {tag_html}{icon} <span style="font-size:15px;font-weight:600;color:#0f172a;margin-top:4px;line-height:1.4">{display_title}</span>
  <div style="font-size:12px;color:#94a3b8;margin-top:3px">{replies} 条回复 · {title[:30]}</div>
  {summary_html}{editor_html}{link_html}
</div>'''


def _build_article_body(posts, article, cover, card_files, card_top3, img_path_fn):
    """构建文章 body HTML（内联样式，可直接粘贴到微信编辑器）"""
    ds = article.get("date", "")
    bank_count = article.get("bank_count", "—")
    total = article.get("total_posts", len(posts))
    top_replies = article.get("top_replies", "—")
    top_tag = article.get("top_tag", "讨论")

    parts = []

    # ── 封面图 ──
    parts.append(f'<p style="text-align:center;margin-bottom:20px"><img src="{img_path_fn(cover)}" alt="封面" style="max-width:100%;border-radius:8px"></p>')

    # ── 今日概览 ──
    parts.append(f'<p style="font-size:14px;color:#666;margin-bottom:20px;padding:12px 14px;background:#f8f9fa;border-radius:8px;line-height:1.6">📊 <strong>今日概览</strong> — {bank_count} 家银行共 {total} 条讨论，最热帖 {top_replies} 条回复</p>')

    # ── ✨ 编辑精选 ──
    if posts:
        pick = posts[0]
        pick_title = pick.get("wechat_title", "") or pick.get("summary", "") or pick.get("title", "")
        pick_summary = pick.get("summary", "")
        pick_replies = pick.get("replies", "?")
        pick_tag = pick.get("value_tag", "讨论")

        # 取编辑点评的第一句作为推荐理由（去掉"开头引号样式）
        pick_note = pick.get("editor_note", "")
        if not pick_note:
            ns, nf = _gen_editor_note(pick)
            pick_note = ns + (" → " + nf if nf else "")
        # 截取第一句作为推荐摘要
        first_sentence = re.split(r'[。！？]', pick_note)[0].strip()
        if len(first_sentence) > 60:
            first_sentence = first_sentence[:60] + "…"

        pick_html = f'''<div style="margin-bottom:20px;padding:14px 16px;background:linear-gradient(135deg,#eef2ff,#faf5ff);border-radius:10px;border:1px solid #c7d2fe">
  <p style="font-size:13px;font-weight:700;color:#4338ca;margin-bottom:6px">
    ✨ 今日编辑精选
    <span style="font-size:11px;font-weight:400;color:#6366f1;margin-left:6px">· 最热帖 {pick_replies} 条回复</span>
  </p>
  <p style="font-size:15px;font-weight:600;color:#0f172a;line-height:1.5">{pick_title}</p>
  <p style="font-size:13px;color:#475569;margin-top:4px;line-height:1.5">{pick_summary}</p>
  <p style="font-size:12px;color:#6366f1;margin-top:6px;line-height:1.5">📝 {first_sentence}</p>
</div>'''
        parts.append(pick_html)

    # ── ⚠️ 避坑/限时专区 ──
    alert_posts = [p for p in posts if p.get("value_tag") in ("避坑", "限时")]
    if alert_posts:
        alerts = "\n".join(_post_card(p) for p in alert_posts)
        parts.append(f'<p style="font-size:15px;font-weight:600;color:#333;margin-bottom:10px;padding-left:10px;border-left:3px solid #6366f1">⚠️ 今日提醒</p>{alerts}')

    # ── 🏆 前三甲 ──
    top3 = posts[:3]
    if top3:
        top3_html = f'<p style="font-size:15px;font-weight:600;color:#333;margin-bottom:10px;padding-left:10px;border-left:3px solid #6366f1">🏆 前三甲详情</p>'
        for p in top3:
            top3_html += _post_card(p)
        if card_top3.exists():
            top3_html += f'<p style="text-align:center;margin-top:4px"><img src="{img_path_fn(card_top3)}" alt="前三甲" style="max-width:100%;border-radius:8px"></p>'
        parts.append(top3_html)

    # ── 📋 更多讨论（去重：排除已展示的避坑/限时帖子） ──
    alert_tids = {p.get("tid") for p in alert_posts}
    rest = [p for p in posts if p.get("tid") not in alert_tids]

    # 始终显示全部文字摘要（完整信息），图片按节奏分组
    all_html = f'<p style="font-size:15px;font-weight:600;color:#333;margin-bottom:10px;padding-left:10px;border-left:3px solid #6366f1">📋 更多热帖</p>'
    for p in rest:
        all_html += _post_card(p)

    # 卡片图按板块分组，每组前加文字说明
    card_labels = {
        1: "🔥 今日热门",
        2: "📂 分类精选",
    }
    for i, cf in enumerate(card_files):
        label = card_labels.get(i + 1, "")
        if label:
            all_html += f'<p style="font-size:12px;font-weight:600;color:#6366f1;margin:16px 0 4px 0">{label}</p>'
        all_html += f'<p style="text-align:center;margin-bottom:10px"><img src="{img_path_fn(cf)}" alt="卡片" style="max-width:100%;border-radius:8px"></p>'
    parts.append(all_html)

    # ── 🔗 原帖链接汇总 ──
    link_list = []
    for i, p in enumerate(posts, 1):
        url = p.get("url", "")
        title = p.get("wechat_title", "") or p.get("summary", "") or p.get("title", "")
        if url:
            link_list.append(f'<p style="font-size:12px;color:#6366f1;margin:3px 0"><a href="{url}" style="color:#6366f1;text-decoration:none">{i}. {title}</a></p>')
    if link_list:
        parts.append(f'<div style="margin-top:24px;padding:14px 16px;background:#f8fafc;border-radius:10px;border:1px solid #e5e7eb"><p style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px">🔗 原帖链接</p>{"".join(link_list)}</div>')

    # ── 💬 互动 + CTA ──
    tag_keywords = {"限时": "活动", "避坑": "避坑", "攻略": "攻略", "公告": "公告", "讨论": "讨论"}
    keyword = tag_keywords.get(top_tag, "信用卡")
    parts.append(f'''<div style="margin-top:24px;padding:16px;background:#0f172a;border-radius:10px;text-align:center;color:#fff">
  <p style="font-size:14px;font-weight:500;margin-bottom:4px">💬 你觉得今天哪条最有价值？评论区聊聊</p>
  <p style="font-size:13px;margin-top:8px">关注 <strong>飞客信用卡日报</strong></p>
  <p style="font-size:11px;color:#94a3b8;margin-top:4px">每日获取信用卡圈最新情报 · 回复「{keyword}」获取完整攻略</p>
  <p style="font-size:11px;color:#94a3b8;margin-top:2px">转发给需要的朋友，一起避坑省钱</p>
  <p style="font-size:12px;margin-top:12px"><a href="https://bagget541541.github.io/flyertrss/" style="color:#818cf8;text-decoration:none">🌐 在线阅读完整日报</a></p>
</div>''')

    return "\n".join(parts)


def gen_article():
    # 读取 enriched 数据
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

    # 检查卡片图片是否存在
    cover = OUT_DIR / "cover_wechat.png"
    card_files = sorted(OUT_DIR.glob("card_0*.png"))
    card_top3 = OUT_DIR / "card_top3.png"

    if not cover.exists():
        print("[-] 封面图不存在，先跑 card_gen.py")
        return

    def img_path(p):
        return str(p.relative_to(cwd)).replace("\\", "/")
    def img_placeholder(p):
        """图片上传占位（用户上传到微信素材库后替换 src）"""
        return f"请上传: {p.name}"

    body_html = _build_article_body(posts, article, cover, card_files, card_top3, img_path)

    # ── 文件一：预览版（完整 HTML，可在浏览器打开预览） ──
    preview_html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>{article_title}</title>
<meta name="description" content="{article_desc}">
<style>{ARTICLE_CSS}</style>
</head>
<body>
<div style="max-width:640px;margin:0 auto;background:#fff;padding:20px 16px 30px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.8">
  <div style="font-size:20px;font-weight:700;line-height:1.4;margin-bottom:8px;color:#1a1a1a">{article_title}</div>
  <div style="font-size:13px;color:#999;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #eee">{ds} · {total} 条讨论</div>
  {body_html}
</div>
</body>
</html>'''

    fn_preview = ARTICLE_DIR / f"公众号文章_{ds}.html"
    fn_preview.write_text(preview_html, encoding="utf-8")
    print(f"[OK] 预览版 -> {fn_preview}")

    # ── 文件二：粘贴版（纯 body，带上传占位，可直接贴到微信编辑器） ──
    paste_body = _build_article_body(posts, article, cover, card_files, card_top3, img_placeholder)
    paste_html = f'''<div style="max-width:640px;margin:0 auto;background:#fff;padding:20px 16px 30px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.8">
  <div style="font-size:20px;font-weight:700;line-height:1.4;margin-bottom:8px;color:#1a1a1a">{article_title}</div>
  <div style="font-size:13px;color:#999;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #eee">{ds} · {total} 条讨论</div>
  {paste_body}
</div>'''

    fn_paste = ARTICLE_DIR / f"公众号粘贴版_{ds}.html"
    fn_paste.write_text(paste_html, encoding="utf-8")
    print(f"[OK] 粘贴版 -> {fn_paste}")

    # ── 元数据 JSON ──
    meta_fn = ARTICLE_DIR / f"公众号元数据_{ds}.json"
    meta = {
        "title": article_title,
        "description": article_desc,
        "date": ds,
        "edition": edition,
        "total_posts": total,
        "bank_count": bank_count,
        "cover_image": img_path(cover),
        "card_images": [img_path(f) for f in card_files],
    }
    meta_fn.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 元数据 -> {meta_fn}")

    print(f"\n{'='*45}")
    print(f"📰 标题: {article_title}")
    print(f"📝 摘要: {article_desc}")
    print(f"📋 帖子: {len(posts)} 条（含文字摘要）")
    print(f"\n💡 操作步骤：")
    print(f"  1. 打开 {fn_preview.name} 预览效果")
    print(f"  2. 打开 {fn_paste.name}，全选复制")
    print(f"  3. 在公众号编辑器粘贴（样式会自动保留）")
    print(f"  4. 上传图片到微信素材库，替换 img src 地址")
    print(f"{'='*45}")

if __name__ == "__main__":
    gen_article()
