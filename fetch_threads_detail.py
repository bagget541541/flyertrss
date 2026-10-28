# -*- coding: utf-8 -*-
"""抓取帖子详情页并解析标题/楼层数/首楼内容 (WAF 限频版)

输入：links_MMDD.json（extract_links.py 产物，含 title/url/tid）
输出：threads_detail_MMDD.json（每条含 tid/title/url/views/replies/content 首楼内容及 reply_samples 回复摘要）

用途：为 LLM 点评提供帖子原文依据（现象/问题 → 判断评估 → 依据）。

WAF 对抗（关键）：
- 逐条抓取，间隔 4~8s，另受共享的最小请求间隔控制
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
from flyert_access import guarded_main, curl_fetch as guarded_curl_fetch, chrome_cdp_fetch, AccessPaused

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
MIN_DELAY, MAX_DELAY = 4.0, 8.0
COOLDOWN_SECONDS = 8 * 60 * 60


def curl_fetch(url, cookie_file=None, retries=1):
    # Chrome CDP returns decoded Unicode text. Keep it as text so the caller
    # does not mistake UTF-8 bytes for the forum's legacy GBK response.
    return chrome_cdp_fetch(url)


def is_waf(text):
    return ("403 Forbidden" in text[:300] or "Access Denied" in text[:300])


def parse_detail(html, url):
    soup = BeautifulSoup(html, "html.parser")
    tid = re.search(r"tid=(\d+)", url).group(1)

    # 标题提取（多方案降级）
    title = ""
    # 方案1：从 <title> 标签提取
    t = soup.find("title")
    if t:
        title = t.get_text(strip=True).replace(" - 飞客论坛", "").replace("-飞客论坛", "").strip()
    # 方案2：尝试 h1.thread-title 等页面标题区
    if not title:
        for sel in ["h1.thread-title", "h1", ".page-title", ".titletext"]:
            h = soup.select_one(sel)
            if h:
                title = h.get_text(strip=True)
                break
    # 方案3：从主帖容器的标题属性提取（某些论坛版本）
    if not title:
        th = soup.find(["h2", "div"], class_=lambda c: c and any(x in (c or "") for x in ["title", "subject"]))
        if th:
            title = th.get_text(strip=True)

    # 查看数/回复数
    views = replies = ""
    m = re.search(r'<em class="views"[^>]*>([\d,]+)</em>', html)
    if m:
        views = m.group(1).replace(",", "")
    m = re.search(r'<em class="replies"[^>]*>([\d,]+)</em>', html)
    if m:
        replies = m.group(1).replace(",", "")

    # 首楼内容: 常见 Discuz 结构；同时保留前几条回复，供点评判断使用。
    content = ""
    pnode = soup.find("td", id=re.compile(r"^postmessage_"))
    if not pnode:
        pnode = soup.find("div", class_=re.compile(r"t_fsz"))
    if pnode:
        content = pnode.get_text("\n", strip=True)

    reply_samples = []
    for node in soup.find_all("td", id=re.compile(r"^postmessage_"))[1:7]:
        text = node.get_text("\n", strip=True)
        if text:
            reply_samples.append(text[:800])

    return {"tid": tid, "title": title, "views": views, "replies": replies,
            "url": url, "content": content[:3000], "reply_samples": reply_samples}


def is_invalid_detail(detail):
    """Discuz may return a prompt page with HTTP 200 for an unavailable thread."""
    return (
        detail.get("title") == "提示信息"
        and not detail.get("views")
        and not detail.get("replies")
        and not detail.get("content")
    )


def find_latest_links(out_dir: Path) -> Path:
    cands = list(out_dir.glob("links_*.json"))
    if not cands:
        raise FileNotFoundError(f"{out_dir} 下没有 links_*.json，先运行 extract_links.py")
    return max(cands, key=lambda path: path.stat().st_mtime)


def save_rows(path: Path, rows):
    """原子写入，WAF/中断时保留已抓成功的详情。"""
    from flyert_access import read_json
    existing = read_json(path, []) or []
    merged = {str(row.get("tid")): row for row in existing if row.get("tid")}
    for row in rows:
        tid = str(row.get("tid", ""))
        if not merged.get(tid, {}).get("content", "").strip() or row.get("content", "").strip():
            merged[tid] = row
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取帖子详情页（WAF 限频）")
    ap.add_argument("links_json", nargs="?", default=None,
                    help="output/links_MMDD.json（默认最新）")
    ap.add_argument("--out-dir", default="output", help="输出目录（默认 output）")
    ap.add_argument("--print-path", action="store_true",
                    help="成功时只打印输出 json 路径（供 bat 捕获）")
    ap.add_argument("--force", action="store_true", help="兼容旧参数；共享站点冷却仍然生效")
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
    links = list({str(it.get("tid")): it for it in links if it.get("tid")}.values())
    if not links:
        return 1

    mmdd = links_path.stem.replace("links_", "").removesuffix("_failed")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"threads_detail_{mmdd}.json"
    cooldown_path = out_dir / f"threads_detail_{mmdd}.waf.json"
    existing = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            existing = []
    by_tid = {str(row.get("tid")): row for row in existing if row.get("tid")}
    out = []
    ok = fail = 0
    total = len(links)
    requested = 0
    cookie_file = None
    for i, it in enumerate(links, 1):
        url = it.get("url", "")
        tid = it.get("tid", "")
        cached = by_tid.get(str(tid), {})
        if cached.get("content", "").strip():
            out.append(cached)
            ok += 1
            print(f"[{i}/{total}] 缓存命中 {tid}")
            continue
        if not url:
            fail += 1
            out.append({"tid": tid, "title": it.get("title", ""), "url": url,
                        "error": "no-url", "content": ""})
            continue
        try:
            requested += 1
            raw = curl_fetch(url, cookie_file=cookie_file)
            # Keep compatibility with byte-returning fetch adapters, while
            # preserving Unicode returned by the visible Chrome session.
            html = raw.decode("gbk", errors="replace") if isinstance(raw, bytes) else raw
            if is_waf(html):
                print(f"[{i}/{total}] WAF 封禁，停止抓取: {url}")
                fail += 1
                out.append({"tid": tid, "title": it.get("title", ""), "url": url,
                            "error": "WAF", "content": ""})
                save_rows(out_path, out)
                cooldown_path.write_text(json.dumps({
                    "detected_at": time.time(),
                    "retry_after": time.time() + COOLDOWN_SECONDS,
                    "reason": "WAF",
                    "completed": len(out),
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                break
            d = parse_detail(html, url)
            if is_invalid_detail(d) or not d.get("content", "").strip():
                raise ValueError("论坛返回提示信息页，未取得帖子正文或统计")
            # The list snapshot is the canonical title for this run. A detail
            # page title can contain site suffixes or stale/misdecoded text.
            if it.get("title"):
                d["title"] = it["title"]
            else:
                d.setdefault("title", "")
            print(f"[{i}/{total}] {d['tid']} {d['title'][:40]} "
                  f"v={d['views']} r={d['replies']} len={len(d['content'])}")
            ok += 1
            out.append(d)
        except AccessPaused as exc:
            print(f"[暂停] {exc}")
            save_rows(out_path, out)
            completed = {str(row.get("tid")) for row in out if row.get("content", "").strip()}
            missing = [str(item.get("tid")) for item in links if str(item.get("tid")) not in completed]
            print(f"[续跑] 待补抓 tid ({len(missing)}): {','.join(missing)}")
            if args.print_path:
                print(out_path)
            return 2
        except Exception as e:
            print(f"[{i}/{total}] ERR {url}: {e}")
            fail += 1
            out.append({"tid": tid, "title": it.get("title", ""), "url": url,
                        "error": str(e), "content": ""})
            # 网络/代理不可用时也暂停本轮，避免连续撞击 16 个链接。
            if requested and ("curl" in str(e).lower() or "connect" in str(e).lower()):
                save_rows(out_path, out)
                cooldown_path.write_text(json.dumps({
                    "detected_at": time.time(),
                    "retry_after": time.time() + 30 * 60,
                    "reason": "network-error",
                    "completed": len(out),
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                print("[暂停] 网络/代理连接失败，30 分钟后再续抓。")
                break
        if i < total and requested:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

        # 每条成功/失败都落盘，下一次只请求缺失 tid。
        save_rows(out_path, out)
    if ok == total and cooldown_path.exists():
        cooldown_path.unlink()
    save_rows(out_path, out)
    if args.print_path:
        print(out_path)
    else:
        missing = [str(it.get("tid")) for it in links
                   if not by_tid.get(str(it.get("tid")), {}).get("content", "").strip()
                   and not any(str(row.get("tid")) == str(it.get("tid")) and row.get("content", "").strip()
                               for row in out)]
        print(f"\n[OK] OK={ok} FAIL={fail} -> {out_path}")
        if missing:
            print(f"[续跑] 待补抓 tid ({len(missing)}): {','.join(missing)}")
    return 0 if ok == total else 2


main = guarded_main(main)

if __name__ == "__main__":
    sys.exit(main())
