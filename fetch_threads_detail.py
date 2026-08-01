# -*- coding: utf-8 -*-
"""抓取帖子详情页并解析标题/楼层数/首楼内容 (WAF 限频版)

输入：links_MMDD.json（extract_links.py 产物，含 title/url/tid）
输出：threads_detail_MMDD.json（每条含 tid/title/url/views/replies/content 首楼内容）

用途：为 LLM 点评提供帖子原文依据（现象/问题 → 判断评估 → 依据）。

WAF 对抗（关键）：
- 逐条抓取，间隔 1.4~2.2s 随机抖动
- 响应含 "403 Forbidden" / "Access Denied" 判定 WAF，标记 error=WAF 不重试
- 被封后停止，避免密集请求触发 IP 封禁（冷却 8-10h）

用法：
  python fetch_threads_detail.py                    # 自动找 output/links_*.json 最新
  python fetch_threads_detail.py output/links_0801.json
  python fetch_threads_detail.py <links.json> --out-dir output
"""
import argparse, json, re, subprocess, sys, time, random
from datetime import datetime
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("[-] 需要 BeautifulSoup：pip install beautifulsoup4", file=sys.stderr)
    sys.exit(2)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MIN_DELAY, MAX_DELAY = 1.4, 2.2


def curl_fetch(url):
    cmd = ["curl", "-sSL", "--compressed", "--connect-timeout", "10", "--max-time", "25",
           "-A", UA,
           "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
           "-H", "Referer: https://www.flyert.com.cn/forum.php?mod=forumdisplay&fid=59",
           url]
    raw = subprocess.check_output(cmd)
    return raw


def is_waf(text):
    return ("403 Forbidden" in text[:300] or "Access Denied" in text[:300])


def parse_detail(html, url):
    soup = BeautifulSoup(html, "html.parser")
    tid = re.search(r"tid=(\d+)", url).group(1)
    title = ""
    t = soup.find("title")
    if t:
        title = t.get_text(strip=True).replace(" - 飞客论坛", "").replace("-飞客论坛", "").strip()
    # 查看数/回复数
    views = replies = ""
    m = re.search(r'<em class="views"[^>]*>([\d,]+)</em>', html)
    if m:
        views = m.group(1).replace(",", "")
    m = re.search(r'<em class="replies"[^>]*>([\d,]+)</em>', html)
    if m:
        replies = m.group(1).replace(",", "")
    # 首楼内容: 常见 Discuz 结构
    content = ""
    pnode = soup.find("td", id=re.compile(r"^postmessage_"))
    if not pnode:
        pnode = soup.find("div", class_=re.compile(r"t_fsz"))
    if pnode:
        content = pnode.get_text("\n", strip=True)
    return {"tid": tid, "title": title, "views": views, "replies": replies,
            "url": url, "content": content[:3000]}


def find_latest_links(out_dir: Path) -> Path:
    cands = sorted(out_dir.glob("links_*.json"))
    if not cands:
        raise FileNotFoundError(f"{out_dir} 下没有 links_*.json，先运行 extract_links.py")
    return cands[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取帖子详情页（WAF 限频）")
    ap.add_argument("links_json", nargs="?", default=None,
                    help="output/links_MMDD.json（默认最新）")
    ap.add_argument("--out-dir", default="output", help="输出目录（默认 output）")
    ap.add_argument("--print-path", action="store_true",
                    help="成功时只打印输出 json 路径（供 bat 捕获）")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    links_path = Path(args.links_json) if args.links_json else find_latest_links(out_dir)
    if not links_path.exists():
        print(f"[-] 链接列表不存在: {links_path}", file=sys.stderr)
        return 1
    links = json.loads(links_path.read_text(encoding="utf-8"))
    if not links:
        print("[-] 链接列表为空", file=sys.stderr)
        return 1

    mmdd = links_path.stem.replace("links_", "")
    out = []
    ok = fail = 0
    total = len(links)
    for i, it in enumerate(links, 1):
        url = it.get("url", "")
        tid = it.get("tid", "")
        if not url:
            fail += 1
            out.append({"tid": tid, "title": it.get("title", ""), "url": url,
                        "error": "no-url", "content": ""})
            continue
        try:
            raw = curl_fetch(url)
            html = raw.decode("gbk", errors="replace")
            if is_waf(html):
                print(f"[{i}/{total}] WAF 封禁，停止抓取: {url}")
                fail += 1
                out.append({"tid": tid, "title": it.get("title", ""), "url": url,
                            "error": "WAF", "content": ""})
                break
            d = parse_detail(html, url)
            d.setdefault("title", it.get("title", ""))
            print(f"[{i}/{total}] {d['tid']} {d['title'][:40]} "
                  f"v={d['views']} r={d['replies']} len={len(d['content'])}")
            ok += 1
            out.append(d)
        except Exception as e:
            print(f"[{i}/{total}] ERR {url}: {e}")
            fail += 1
            out.append({"tid": tid, "title": it.get("title", ""), "url": url,
                        "error": str(e), "content": ""})
        if i < total:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"threads_detail_{mmdd}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.print_path:
        print(out_path)
    else:
        print(f"\n[OK] OK={ok} FAIL={fail} -> {out_path}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
