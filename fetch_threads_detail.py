# -*- coding: utf-8 -*-
"""抓取指定帖子详情页并解析标题/楼层数/首楼内容 (WAF 限频版)"""
import subprocess, re, json, time, random, sys
from bs4 import BeautifulSoup

URLS = [
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861095",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861165",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861224",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4860913",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4752458",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4860886",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861185",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4714888",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861189",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861124",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4860814",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861146",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861156",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861199",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861179",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4858453",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861115",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4349284",
    "https://www.flyert.com.cn/forum.php?mod=viewthread&tid=4861226",
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


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
    if m: views = m.group(1).replace(",", "")
    m = re.search(r'<em class="replies"[^>]*>([\d,]+)</em>', html)
    if m: replies = m.group(1).replace(",", "")
    # 首楼内容: 常见 Discuz 结构
    content = ""
    pnode = soup.find("td", id=re.compile(r"^postmessage_"))
    if not pnode:
        pnode = soup.find("div", class_=re.compile(r"t_fsz"))
    if pnode:
        content = pnode.get_text("\n", strip=True)
    # 首楼作者
    author = ""
    ae = soup.find("a", class_=re.compile(r"xw1|author"))
    if ae:
        author = ae.get_text(strip=True)
    return {"tid": tid, "title": title, "views": views, "replies": replies,
            "author": author, "url": url, "content": content[:3000]}


def main():
    out = []
    ok = fail = 0
    for i, url in enumerate(URLS, 1):
        try:
            raw = curl_fetch(url)
            html = raw.decode("gbk", errors="replace")
            if is_waf(html):
                print(f"[{i}/19] WAF {url}")
                fail += 1
                out.append({"tid": re.search(r"tid=(\d+)", url).group(1), "title": "",
                            "url": url, "error": "WAF", "content": ""})
            else:
                d = parse_detail(html, url)
                print(f"[{i}/19] {d['tid']} {d['title'][:40]} v={d['views']} r={d['replies']} len={len(d['content'])}")
                ok += 1
                out.append(d)
        except Exception as e:
            print(f"[{i}/19] ERR {url}: {e}")
            fail += 1
            out.append({"tid": re.search(r"tid=(\d+)", url).group(1), "title": "",
                        "url": url, "error": str(e), "content": ""})
        if i < len(URLS):
            time.sleep(random.uniform(1.4, 2.2))
    with open("threads_detail.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nOK={ok} FAIL={fail}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
