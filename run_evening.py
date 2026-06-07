# -*- coding: utf-8 -*-
"""临时脚本：绕过代理，跑晚报全流程"""
import os, sys, json, time

for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ.pop(k, None)

import httpx
_orig = httpx.Client.__init__
def _np(self, *a, **kw):
    kw.setdefault("trust_env", False)
    kw.setdefault("proxy", None)
    _orig(self, *a, **kw)
httpx.Client.__init__ = _np

sys.path.insert(0, ".")
import settings; os.chdir(str(settings.CWD))

def log(m):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")

edition = "晚报"
log("版本: " + edition)

# Step 1
log("Step 1: 抓取...")
import fetcher
url = fetcher.build_page_url(1)
html = fetcher.fetch_page_httpx(url)
if html:
    total = fetcher.detect_total_pages(html)
    all_t = fetcher.parse_threads(html)
    log(f"  Page1: {len(all_t)} posts, total_pages={total}")
    for p in range(2, min(4, total + 1)):
        time.sleep(1.5)
        h2 = fetcher.fetch_page_httpx(fetcher.build_page_url(p))
        if h2:
            t2 = fetcher.parse_threads(h2)
            all_t.extend(t2)
            log(f"  Page{p}: {len(t2)} posts")
    kept, dropped = fetcher.filter_threads(all_t)
    log(f"  共{len(all_t)}帖, 保留{len(kept)}, 过滤{len(dropped)}")
    with open("threads_raw.json", "w", encoding="utf-8") as f:
        json.dump(all_t, f, ensure_ascii=False, indent=2)
    with open("threads_filtered.json", "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)
    new = {t["tid"] for t in kept}
    if new:
        seen = fetcher.load_seen()
        seen.update(new)
        fetcher.save_seen(seen)
        log(f"  已保存{len(new)}新tid")
    for i, t in enumerate(kept, 1):
        print(f"  {i}. [{t['category']}] {t['title']} ({t['replies']}r/{t['views']}v)")
else:
    log("  抓取失败!")

# Step 2
log("Step 2: LLM 富化...")
import enrich
sys.argv = ["enrich.py", "--edition", edition]
try:
    enrich.main()
except Exception as e:
    log(f"  富化失败(降级): {e}")

# Step 3
log("Step 3: 分类+日报...")
import summary
try:
    summary.main()
except Exception as e:
    log(f"  分类失败: {e}")

# Step 4
log("Step 4: 卡片生成...")
import card_gen
try:
    card_gen.main()
except Exception as e:
    log(f"  卡片失败: {e}")

# Step 4.5
log("Step 4.5: QA 质检...")
try:
    from wechat_image_qa import run_qa
    ok, msg = run_qa()
    log(f"  QA: {msg}")
except Exception as e:
    log(f"  QA 跳过: {e}")

from datetime import date
ds = date.today().isoformat()
log(f"完成! 日报_{ds}.md/.html 已生成")
