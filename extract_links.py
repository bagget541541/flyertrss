#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_links.py — 从公众号日报 HTML 提取底部「原帖链接」区块

输入：_site/公众号文章_YYYY-MM-DD.html（docx_to_wechat.py 生成的预览版）
输出：output/links_MMDD.json —— 链接列表 [{title, url, tid}]，仅标题+URL

流程（微信发布.bat 第 1 步）：
  HTML → 只取最下方「🔗 原帖链接」区块的标题+URL → 输出链接列表 JSON
  后续的点评/归类/排版由 LLM 脚本（skill 能力实现）完成。

用法：
  python extract_links.py                    # 自动找 _site 当天最新 HTML
  python extract_links.py <html_path>
  python extract_links.py --print-path       # 只打印输出 JSON 路径（供 bat 捕获）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("[-] 需要 BeautifulSoup：pip install beautifulsoup4", file=sys.stderr)
    sys.exit(2)


def parse_date(html: str) -> str:
    """从 <title>飞客晚报 | YYYY-MM-DD</title> 取日期。"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", html[:500])
    return m.group(1) if m else ""


def extract_links(html: str) -> list[dict]:
    """提取底部「🔗 原帖链接」区块的 {title, url, tid} 列表。

    精确定位：找到文本恰为「🔗 原帖链接」的 <p>（板块标题，font-size:14px 加粗），
    取其父容器，只提取容器内 <p><a> 中的链接（编号. 标题 + href）。
    """
    soup = BeautifulSoup(html, "html.parser")
    target = None
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt in {"🔗 原帖链接", "原帖链接"} and p.find("a") is None and p.parent:
            target = p.parent
            break
    if target is None:
        return []
    links = []
    for a in target.find_all("a", href=True):
        title = a.get_text(strip=True)
        url = a["href"].replace("&amp;", "&").strip()
        if not url.startswith("http"):
            continue
        # 去「1. 」编号前缀
        title = re.sub(r"^\d+[.、]\s*", "", title).strip()
        m = re.search(r"tid=(\d+)", url)
        tid = m.group(1) if m else ""
        links.append({"title": title, "url": url, "tid": tid})
    return links


def find_today_html(site_dir: Path, ds: str | None = None) -> Path:
    """找当天预览版 HTML：优先 公众号文章_{ds}.html，其次当天最新。"""
    if ds:
        p = site_dir / f"公众号文章_{ds}.html"
        if p.exists():
            return p
    cands = [p for p in site_dir.glob("公众号文章_*.html")]
    if not cands:
        raise FileNotFoundError(f"{site_dir} 下没有 公众号文章_*.html")
    return max(cands, key=lambda p: p.stat().st_mtime)


def main() -> int:
    ap = argparse.ArgumentParser(description="从日报 HTML 提取底部原帖链接列表")
    ap.add_argument("html_path", nargs="?", default=None,
                    help="公众号文章_YYYY-MM-DD.html 路径（默认 _site 当天最新）")
    ap.add_argument("--site-dir", default="_site", help="site 目录（默认 _site）")
    ap.add_argument("--out-dir", default="output", help="JSON 输出目录（默认 output）")
    ap.add_argument("--dry-run", action="store_true", help="只打印链接列表不写文件")
    ap.add_argument("--print-path", action="store_true",
                    help="成功时只打印输出 JSON 路径（供 bat 捕获）")
    args = ap.parse_args()

    site_dir = Path(args.site_dir)
    html_path = Path(args.html_path) if args.html_path else find_today_html(site_dir)
    if not html_path.exists():
        print(f"[-] HTML 不存在: {html_path}", file=sys.stderr)
        return 1

    html = html_path.read_text(encoding="utf-8-sig")
    ds = parse_date(html) or date.today().isoformat()
    links = extract_links(html)
    if not links:
        print("[-] 未从 HTML 底部提取到原帖链接", file=sys.stderr)
        return 2

    if args.dry_run:
        for it in links:
            print(f"{it['tid']} {it['title']} -> {it['url']}")
        return 0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mmdd = ds.replace("-", "")[4:]
    out_path = out_dir / f"links_{mmdd}.json"
    out_path.write_text(json.dumps(links, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    if args.print_path:
        print(out_path)
    else:
        print(f"[OK] 已提取 {len(links)} 条链接 -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
