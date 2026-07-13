#!/usr/bin/env python3
"""
docx_to_wechat.py — 基于精选日报 Word 底稿生成公众号粘贴 HTML

输入：精选日报_YYYY-MM-DD_*.docx（Coze AI 产出的结构化底稿）
输出：
  公众号文章_{date}.html      浏览器预览版（含 <style> 外壳）
  公众号粘贴版_{date}.html    纯内联片段，粘贴进公众号编辑器
  公众号元数据_{date}.json    元数据

设计依据：Word 底稿的稳定结构规律（兼容 Word 原生列表经 Pandoc 转换后的写法）
  # 飞客日报 📋 YYYY-MM-DD
  抓取时间 HH:MM | 共 N 条讨论 | 新卡X 权益变更X 活动X 其他X | 数据源：...
  ## 一级板块（6 个：热门讨论/新卡发行/权益变更/退发退市/活动优惠/其他）
  ### {银行} {一句话摘要} {标签emoji?}      埖子卡片头
  • 🔗 {标题}：{url}                          银行+标题+原帖
  • 📊 {N}回 / {N}阅                          回复数+阅读数
  • 💬 点评：{定制批注}                       编辑点评
  （本日无相关讨论）                            餽板块占位
  本内容由 Coze AI 生成...                     AI 合规声明

视觉模板复用 0709 前两条卡片：左边色条+银行标签+分类副标+数据行+点评气泡+按钮式原帖链接。
约束：公众号粘贴只认内联 style，禁用 <style>/JS/外部资源/外部字体/class。

格式兼容：卡体列表兼容 `-`、`*`、`•` 前缀；热门榜单兼容 `1.` 和 `1\.`；
元信息兼容 Pandoc 引用块；分类标签支持 `🔴`、`🟡`、`🐷`、`⚪`。

Skill 选型：docx（解析 .docx）+ frontend-design 设计原则（产出模板）。

用法：
  python docx_to_wechat.py 精选日报_0709_*.docx
  python docx_to_wechat.py 精选日报_0709_*.docx --paste-only
  python docx_to_wechat.py 精选日报_0709_*.docx --out-dir _site
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    from publishing_helpers import gen_editor_note
except Exception:  # 独立运行时降级
    gen_editor_note = None

# ── 银行→主色 映射（扫读时一眼区分）────────────────────────────────
BANK_COLOR = {
    "工商银行": "#dc2626", "工行": "#dc2626", "工银": "#dc2626",
    "汇丰银行": "#ea580c", "汇丰": "#ea580c", "比丰": "#ea580c",
    "中信银行": "#2563eb", "中信": "#2563eb",
    "农行": "#16a34a", "农业银行": "#16a34a", "老农": "#16a34a",
    "交通银行": "#7c3aed", "交行": "#7c3aed", "沃德": "#7c3aed",
    "邮储银行": "#d97706", "邮储": "#d97706",
    "招商银行": "#db2777", "招行": "#db2777", "招行": "#db2777",
    "浦发银行": "#0d9488", "浦发": "#0d9488", "浦发": "#0d9488",
    "中国银行": "#475569", "中行": "#475569",
    "平安银行": "#059669", "平安": "#059669",
    "光大银行": "#9333ea", "光大": "#9333ea",
}
DEFAULT_BANK_COLOR = "#78716c"

# 标签 emoji → 分类副标签文案
TAG_LABEL = {
    "🔴": "高价值", "🟡": "中等", "🐷": "套路",
    "⚪": "套路",
}

# 板块图标
SECTION_ICON = {
    "热门讨论": "🔥", "新卡发行": "🆕", "权益变更": "⚠️",
    "退发退市": "📉", "活动优惠": "🎁", "其他": "📌",
}

ARTICLE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;background:#f5f5f5;color:#1a1a1a;padding:0;max-width:640px;margin:0 auto;line-height:1.8}
.article{background:#fff;padding:20px 16px 30px}
"""


def extract_markdown(docx_path: Path) -> str:
    """用 pandoc 把 .docx 抽成 markdown；pandoc 不可用时降级 python-docx。"""
    try:
        result = subprocess.run(
            ["pandoc", str(docx_path), "-t", "markdown", "--wrap=none"],
            capture_output=True, text=True, check=True, encoding="utf-8",
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, FileNotFoundError):
            print("[-] pandoc 未安装，降级到 python-docx", file=sys.stderr)
        return _extract_via_python_docx(docx_path)


def _extract_via_python_docx(docx_path: Path) -> str:
    """pandoc 不可用时的降级解析：逐段拼 markdown。"""
    import docx
    d = docx.Document(str(docx_path))
    lines = []
    for p in d.paragraphs:
        txt = p.text.strip()
        if not txt:
            lines.append("")
            continue
        style = (p.style.name or "").lower()
        if style.startswith("heading 1") or style == "title":
            lines.append(f"# {txt}")
        elif style.startswith("heading 2"):
            lines.append(f"## {txt}")
        elif style.startswith("heading 3"):
            lines.append(f"### {txt}")
        else:
            lines.append(txt)
    return "\n".join(lines)


# ── 解析 markdown 成结构化日报 ─────────────────────────────────────
def parse_daily(md: str) -> dict:
    """把 markdown 解析成 {date, meta, sections:[{name, posts:[...]}], ai_notice}。"""
    lines = md.splitlines()
    daily = {"date": "", "meta": "", "sections": [], "ai_notice": ""}

    # 日报标题行取日期
    for line in lines:
        m = re.match(r"^#\s*飞客日报\s*📋?\s*(\d{4}-\d{2}-\d{2})", line)
        if m:
            daily["date"] = m.group(1)
            break

    # 元信息行
    for line in lines:
        # Pandoc 会把 Word 中的摘要段落转换成 Markdown 引用块（> ...）。
        meta_line = line.strip()
        if meta_line.startswith(">"):
            meta_line = meta_line[1:].strip()
        meta_line = meta_line.replace(r"\|", "|")
        if meta_line.startswith("抓取时间") or meta_line.startswith("|"):
            daily["meta"] = meta_line
            break

    # AI 合规声明
    for line in lines:
        if "本内容由" in line and "生成" in line:
            daily["ai_notice"] = line.strip()
            break

    # 板块解析
    cur_section = None
    cur_post = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 一级板块
        m1 = re.match(r"^##\s+(.+)$", line)
        if m1:
            # 落尾
            if cur_post and cur_section:
                cur_section["posts"].append(cur_post)
                cur_post = None
            if cur_section:
                daily["sections"].append(cur_section)
            name = m1.group(1).strip()
            # 剥离板块名前的 emoji
            name_clean = re.sub(r"^[^\u4e00-\u9fa5a-zA-Z]+", "", name)
            cur_section = {"name": name_clean, "raw": name, "posts": []}
            i += 1
            continue
        # 空板块占位
        if "（本日无相关讨论）" in line or "(本日无相关讨论)" in line:
            if cur_section:
                cur_section["empty"] = True
            i += 1
            continue
        # 三级帖子卡片头
        m3 = re.match(r"^###\s+(.+)$", line)
        if m3 and cur_section is not None:
            if cur_post:
                cur_section["posts"].append(cur_post)
            head = m3.group(1).strip()
            cur_post = _parse_post_head(head)
            i += 1
            continue
        # 榜单行（热门讨论等有序列表：pandoc 转义为 `1\. **标题**（N回/N阅）[银行]`）
        # Pandoc 可能输出 `1.`，也可能输出转义后的 `1\.`。
        m_num = re.match(r"^(\d+)(?:\\)?\.\s+(.+)$", line)
        if m_num and cur_section is not None:
            if cur_post:
                cur_section["posts"].append(cur_post)
                cur_post = None
            cur_section["posts"].append(_parse_list_item(m_num.group(2).strip()))
            i += 1
            continue
        # 三行卡体
        if cur_post is not None:
            # Word 原生列表经 Pandoc 通常变成 `-`，旧底稿可能是字面量 `•`。
            if re.match(r"^(?:[-*•]\s*)?🔗", line):
                _parse_post_link(line, cur_post)
            elif re.match(r"^(?:[-*•]\s*)?📊", line):
                _parse_post_stats(line, cur_post)
            elif re.match(r"^(?:[-*•]\s*)?💬", line):
                _parse_post_note(line, cur_post)
        i += 1

    # 落尾
    if cur_post and cur_section:
        cur_section["posts"].append(cur_post)
    if cur_section:
        daily["sections"].append(cur_section)

    return daily


def _parse_post_head(head: str) -> dict:
    """`{银行} {一句话摘要} {标签emoji?}` → {bank, summary, tag, tag_label}。"""
    # 末尾 emoji 标签（如 🔴高价值/🟡中等/🐷套路）
    tag = ""
    tag_label = ""
    m = re.search(r"(🔴|🟡|🐷|⚪)([\u4e00-\u9fa5]+)?\s*$", head)
    if m:
        tag = m.group(1)
        tag_label = m.group(2) or TAG_LABEL.get(tag, "")
        head = head[: m.start()].strip()

    # 银行名：首个空格前，支持两字、三字、四字银行名
    bank = ""
    # 优先匹配已知银行名
    for name in sorted(BANK_COLOR.keys(), key=len, reverse=True):
        if head.startswith(name):
            bank = name
            break
    if bank:
        summary = head[len(bank) :].strip()
    else:
        # fallback：首个空格切
        parts = head.split(maxsplit=1)
        bank = parts[0] if parts else head
        summary = parts[1] if len(parts) > 1 else ""

    return {
        "bank": bank,
        "summary": summary,
        "tag": tag,
        "tag_label": tag_label,
        "title": "",
        "url": "",
        "replies": "?",
        "views": "?",
        "note": "",
    }


def _parse_post_link(line: str, post: dict) -> None:
    """`• 🔗 {标题}：{url}` 或标题内含空格再接 url。"""
    body = re.sub(r"^[-*•]\s*", "", line).strip()
    body = body[1:].strip() if body.startswith("🔗") else body  # 去图标
    # 按 url 切：第一个 http 出现处
    m = re.search(r"(https?://\S+)", body)
    if m:
        post["url"] = m.group(1).rstrip("：:")
        title_part = body[: m.start()].rstrip("：:").strip()
        post["title"] = title_part
    else:
        post["title"] = body


def _parse_post_stats(line: str, post: dict) -> None:
    """`• 📊 {N}回 / {N}阅`。"""
    body = re.sub(r"^[-*•]\s*", "", line).strip()
    body = body[1:].strip() if body.startswith("📊") else body
    m = re.search(r"(\d+)\s*回\s*/\s*(\d+)\s*阅", body)
    if m:
        post["replies"] = int(m.group(1))
        post["views"] = int(m.group(2))


def _parse_post_note(line: str, post: dict) -> None:
    """`• 💬 点评：{定制批注}`。"""
    body = re.sub(r"^[-*•]\s*", "", line).strip()
    body = body[1:].strip() if body.startswith("💬") else body
    body = re.sub(r"^点评[：:]\s*", "", body)
    post["note"] = body.strip()


def _parse_list_item(body: str) -> dict:
    """热门讨论榜单行：`**标题**（N回/N阅）[银行]`（pandoc 转义后）。

    pandoc 输出会把 markdown 的 `*` `[` `]` 反斜杠转义为 `\\*` `\\[` `\\]`，
    本函数剥掉转义再抽字段。无 url/点评，但有标题/银行/回复/阅读数。
    """
    # 剥 pandoc 转义反斜杠
    clean = body.replace("\\*", "*").replace("\\[", "[").replace("\\]", "]").replace("\\(", "(").replace("\\)", ")")
    # 标题在 **...** 内
    title = ""
    m = re.search(r"\*\*([^*]+)\*\*", clean)
    if m:
        title = m.group(1).strip()
        clean = clean[: m.start()] + clean[m.end() :]
    # 回复/阅读在 （N回/N阅）
    replies = "?"
    views = "?"
    m = re.search(r"（(\d+)\s*回\s*/\s*(\d+)\s*阅）", clean)
    if m:
        replies = int(m.group(1))
        views = int(m.group(2))
        clean = clean[: m.start()] + clean[m.end() :]
    # 银行在 [xxx]
    bank = ""
    m = re.search(r"\[([^\]]+)\]", clean)
    if m:
        bank = m.group(1).strip()
    # 银行名归一（榜单用简称，归一到色映射键）
    for name in sorted(BANK_COLOR.keys(), key=len, reverse=True):
        if bank.startswith(name) or name.startswith(bank):
            bank = name
            break
    return {
        "bank": bank,
        "summary": "",
        "tag": "",
        "tag_label": "",
        "title": title,
        "url": "",
        "replies": replies,
        "views": views,
        "note": "",
        "is_list_item": True,
    }


# ── HTML 生成 ─────────────────────────────────────────────────────
def _bank_color(bank: str) -> str:
    return BANK_COLOR.get(bank, DEFAULT_BANK_COLOR)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _post_card(post: dict, paste_mode: bool) -> str:
    """单帖卡片：左边色条+银行标签+分类副标+标题+数据行+点评气泡+按钮式原帖链接。

    榜单项（is_list_item=True，无 url/点评）走精简榜单行：
    排名+标题+银行标签+回复阅读数一行，无点评气泡、无原帖链接。
    """
    color = _bank_color(post["bank"])
    bank = _esc(post["bank"])

    # 榜单行：热门讨论等有序列表项，精简渲染
    if post.get("is_list_item"):
        title = _esc(post["title"])
        replies = post["replies"]
        views = post["views"]
        replies_str = f"{replies}" if replies != "?" else "?"
        views_str = f"{views}" if views != "?" else "?"
        rank = post.get("rank", "")
        rank_html = (
            f'<span style="display:inline-block;min-width:22px;font-size:13px;font-weight:700;'
            f'color:{color};text-align:center">{rank}</span>'
        ) if rank else ""
        bank_tag = (
            f'<span style="display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;'
            f'border-radius:4px;color:#fff;background:{color};margin-left:8px">{bank}</span>'
        )
        return (
            f'<div style="position:relative;background:#f8fafc;border-radius:8px;padding:10px 14px 10px 16px;'
            f'margin-bottom:8px;border:1px solid #e5e7eb;overflow:hidden">'
            f'<div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:{color}"></div>'
            f'<div style="display:flex;align-items:center;gap:0">'
            f'{rank_html}<span style="font-size:14px;font-weight:600;color:#0f172a;line-height:1.4;margin-left:6px;flex:1">{title}</span>{bank_tag}'
            f'</div>'
            f'<div style="font-size:11px;color:#94a3b8;margin-top:4px;margin-left:28px">{replies_str} 条回复 · {views_str} 次阅读</div>'
            f'</div>'
        )

    summary = _esc(post["summary"])
    title = _esc(post["title"]) or summary
    replies = post["replies"]
    views = post["views"]
    replies_str = f"{replies}" if replies != "?" else "?"
    views_str = f"{views}" if views != "?" else "?"

    # 银行标签
    bank_tag = f'<span style="display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;color:#fff;background:{color}">{bank}</span>'
    # 分类副标签（如有）
    sub_tag = ""
    if post.get("tag_label"):
        sub_tag = f'<span style="display:inline-block;font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;color:{color};background:#fff">{_esc(post["tag_label"])}</span>'
    sub_row = f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">{bank_tag}{sub_tag}</div>' if sub_tag else f'<div style="margin-bottom:4px">{bank_tag}</div>'

    # 数据行
    stats = f"{replies_str} 条回复 · {views_str} 次阅读"
    if summary and summary != title:
        stats += f" · {summary}"
    stats_html = f'<div style="font-size:12px;color:#94a3b8;margin-top:3px">{stats}</div>'

    # 点评气泡（缺失时 fallback 套话）
    note = post.get("note") or ""
    if not note and gen_editor_note is not None:
        try:
            ns, nf = gen_editor_note(post)
            note = ns + (" → " + nf if nf else "")
        except Exception:
            note = ""
    if not note:
        note = "「" + (post["title"] or summary) + "」见原帖讨论。"
    note_html = (
        f'<div style="font-size:12px;color:#1e293b;margin-top:8px;padding:8px 10px;'
        f'background:#fff;border:1px solid #e5e7eb;border-radius:6px;line-height:1.6">'
        f'<span style="color:{color};font-weight:700">📝 编辑点评：</span>{_esc(note)}</div>'
    )

    # 原帖链接：粘贴版用纯文本 URL，预览版用 <a>
    url = post.get("url", "")
    if paste_mode:
        link_html = (
            f'<div style="margin-top:6px;font-size:11px;color:#94a3b8;word-break:break-all">'
            f'🔗 原帖 {_esc(url)}</div>'
        ) if url else ""
    else:
        link_html = (
            f'<div style="margin-top:8px"><a href="{_esc(url)}" style="display:inline-block;'
            f'font-size:11px;font-weight:600;color:{color};padding:3px 10px;border:1px solid {color};'
            f'border-radius:4px;text-decoration:none">🔗 查看原帖</a></div>'
        ) if url else ""

    return (
        f'<div style="position:relative;background:#f8fafc;border-radius:8px;padding:12px 14px 12px 16px;'
        f'margin-bottom:10px;border:1px solid #e5e7eb;overflow:hidden">'
        f'<div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:{color}"></div>'
        f'{sub_row}'
        f'<div style="font-size:15px;font-weight:600;color:#0f172a;line-height:1.4;margin-top:2px">💬 {title}</div>'
        f'{stats_html}{note_html}{link_html}</div>'
    )


def _section_block(section: dict, paste_mode: bool) -> str:
    """板块块：标题 + 帖子卡片列表 或 空板块占位。"""
    icon = SECTION_ICON.get(section["name"], "")
    head = (
        f'<p style="font-size:15px;font-weight:600;color:#333;margin-bottom:10px;'
        f'padding-left:10px;border-left:3px solid #6366f1">{icon} {section["name"]}</p>'
    )
    if section.get("empty") or not section["posts"]:
        return head + '<div style="font-size:12px;color:#94a3b8;padding:8px 14px;background:#f8fafc;border-radius:8px;margin-bottom:10px">（本日无相关讨论）</div>'
    # 榜单板块：给每个 list_item 灌排名序号
    posts = section["posts"]
    if any(p.get("is_list_item") for p in posts):
        for idx, p in enumerate(posts, 1):
            if p.get("is_list_item"):
                p["rank"] = f"NO.{idx}"
    cards = "".join(_post_card(p, paste_mode) for p in posts)
    return head + cards


def build_body(daily: dict, paste_mode: bool) -> str:
    """组装正文：今日概览 + 各板块 + 原帖链接汇总 + CTA。"""
    parts = []

    # 今日概览
    meta = daily.get("meta", "")
    parts.append(
        '<p style="font-size:14px;color:#666;margin-bottom:20px;padding:12px 14px;background:#f8f9fa;border-radius:8px;line-height:1.6">'
        f'📊 <strong>今日概览</strong> — {_esc(meta) or "精选日报"}</p>'
    )

    # 各板块
    for section in daily["sections"]:
        parts.append(_section_block(section, paste_mode))

    # 原帖链接汇总
    link_list = []
    idx = 0
    for section in daily["sections"]:
        for post in section["posts"]:
            url = post.get("url", "")
            if not url:
                continue
            idx += 1
            title = _esc(post["title"] or post["summary"])
            if paste_mode:
                link_list.append(
                    f'<p style="font-size:12px;color:#6366f1;margin:3px 0;word-break:break-all">{idx}. {title}<br>'
                    f'<span style="font-size:11px;color:#94a3b8">{_esc(url)}</span></p>'
                )
            else:
                link_list.append(
                    f'<p style="font-size:12px;color:#6366f1;margin:3px 0">'
                    f'<a href="{_esc(url)}" style="color:#6366f1;text-decoration:none">{idx}. {title}</a></p>'
                )
    if link_list:
        parts.append(
            '<div style="margin-top:24px;padding:14px 16px;background:#f8fafc;border-radius:10px;border:1px solid #e5e7eb">'
            '<p style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px">🔗 原帖链接</p>'
            f'{"".join(link_list)}</div>'
        )

    # AI 合规声明
    ai = daily.get("ai_notice", "")
    if ai:
        parts.append(
            '<div style="margin-top:12px;padding:8px 12px;background:#fff7ed;border-radius:6px;border:1px solid #fed7aa;text-align:center">'
            f'<p style="font-size:11px;color:#9a3412;line-height:1.6">{_esc(ai)}</p></div>'
        )

    # CTA
    if paste_mode:
        parts.append(
            '<div style="margin-top:24px;padding:16px;background:#0f172a;border-radius:10px;text-align:center;color:#fff">'
            '<p style="font-size:14px;font-weight:500;margin-bottom:4px">💬 你觉得今天哪条最有价值？评论区聊聊</p>'
            '<p style="font-size:13px;margin-top:8px">关注 <strong>飞客信用卡日报</strong></p>'
            '<p style="font-size:11px;color:#94a3b8;margin-top:2px">转发给需要的朋友，一起避坑省钱</p></div>'
        )
    else:
        parts.append(
            '<div style="margin-top:24px;padding:16px;background:#0f172a;border-radius:10px;text-align:center;color:#fff">'
            '<p style="font-size:14px;font-weight:500;margin-bottom:4px">💬 你觉得今天哪条最有价值？评论区聊聊</p>'
            '<p style="font-size:13px;margin-top:8px">关注 <strong>飞客信用卡日报</strong></p>'
            '<p style="font-size:11px;color:#94a3b8;margin-top:4px">每日获取信用卡圈最新情报 · 回复「讨论」获取完整攻略</p>'
            '<p style="font-size:11px;color:#94a3b8;margin-top:2px">转发给需要的朋友，一起避坑省钱</p>'
            '<p style="font-size:12px;margin-top:12px"><a href="https://bagget541541.github.io/flyertrss/" style="color:#818cf8;text-decoration:none">🌐 在线阅读完整日报</a></p></div>'
        )

    return "\n".join(parts)


def gen_outputs(daily: dict, out_dir: Path, paste_only: bool) -> int:
    ds = daily["date"] or date.today().isoformat()
    article_title = f"飞客晚报 | {ds}"
    desc = daily["meta"] or f"今日精选日报 {ds}"

    body_paste = build_body(daily, paste_mode=True)
    paste_html = (
        f'<div style="max-width:640px;margin:0 auto;background:#fff;padding:20px 16px 30px;'
        f"font-family:'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.8\">"
        f'<div style="font-size:20px;font-weight:700;line-height:1.4;margin-bottom:8px;color:#1a1a1a">{_esc(article_title)}</div>'
        f'<div style="font-size:13px;color:#999;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #eee">{ds} · 精选日报</div>'
        f'{body_paste}</div>'
    )
    fn_paste = out_dir / f"公众号粘贴版_{ds}.html"
    fn_paste.write_text(paste_html, encoding="utf-8")
    print(f"[OK] 粘贴版 -> {fn_paste}")

    if not paste_only:
        body_preview = build_body(daily, paste_mode=False)
        preview_html = (
            '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">\n'
            f"<title>{_esc(article_title)}</title>\n"
            f'<meta name="description" content="{_esc(desc)}">\n'
            f"<style>{ARTICLE_CSS}</style>\n</head>\n<body>\n"
            f'<div style="max-width:640px;margin:0 auto;background:#fff;padding:20px 16px 30px;'
            f"font-family:'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.8\">"
            f'<div style="font-size:20px;font-weight:700;line-height:1.4;margin-bottom:8px;color:#1a1a1a">{_esc(article_title)}</div>'
            f'<div style="font-size:13px;color:#999;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid #eee">{ds} · 精选日报</div>'
            f'{body_preview}\n</div>\n</body>\n</html>'
        )
        fn_preview = out_dir / f"公众号文章_{ds}.html"
        fn_preview.write_text(preview_html, encoding="utf-8")
        print(f"[OK] 预览版 -> {fn_preview}")

    # 元数据
    total_posts = sum(len(s["posts"]) for s in daily["sections"])
    meta = {
        "title": article_title,
        "description": desc,
        "date": ds,
        "edition": "精选日报",
        "total_posts": total_posts,
        "sections": [{"name": s["name"], "count": len(s["posts"])} for s in daily["sections"]],
        "ai_notice": daily.get("ai_notice", ""),
        "source": "docx",
    }
    fn_meta = out_dir / f"公众号元数据_{ds}.json"
    fn_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 元数据 -> {fn_meta}")

    print(f"\n{'='*45}")
    print(f"📰 标题: {article_title}")
    print(f"📋 帖子: {total_posts} 条 / {len(daily['sections'])} 个板块")
    print(f"💡 操作：打开 {fn_paste.name} 全选复制 → 公众号编辑器粘贴")
    print(f"{'='*45}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="基于精选日报 Word 底稿生成公众号粘贴 HTML")
    ap.add_argument("docx", help="精选日报 .docx 文件路径")
    ap.add_argument("--out-dir", default="_site", help="输出目录（默认 _site）")
    ap.add_argument("--paste-only", action="store_true", help="只出粘贴版")
    args = ap.parse_args()

    docx_path = Path(args.docx)
    if not docx_path.exists():
        print(f"[-] 文件不存在: {docx_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md = extract_markdown(docx_path)
    if not md.strip():
        print("[-] 抽出的内容为空，检查 docx 是否正常", file=sys.stderr)
        return 2

    daily = parse_daily(md)
    if not daily["date"]:
        daily["date"] = date.today().isoformat()
        print(f"[!] 未解析到日期，用今天: {daily['date']}", file=sys.stderr)
    if not daily["sections"]:
        print("[-] 未解析到任何板块，检查底稿格式", file=sys.stderr)
        return 3

    return gen_outputs(daily, out_dir, args.paste_only)


if __name__ == "__main__":
    sys.exit(main())
