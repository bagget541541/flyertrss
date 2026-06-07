# -*- coding: utf-8 -*-
"""沙箱外运行：card_gen + wechat_article_gen"""
import os, sys

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(k, None)

import httpx
_orig = httpx.Client.__init__
def _np(self, *a, **kw):
    kw.setdefault("trust_env", False)
    kw.setdefault("proxy", None)
    _orig(self, *a, **kw)
httpx.Client.__init__ = _np
_orig_post = httpx.post
def _np2(*a, **kw):
    kw.setdefault("trust_env", False)
    return _orig_post(*a, **kw)
httpx.post = _np2

sys.path.insert(0, ".")
import settings
os.chdir(str(settings.CWD))

print("=" * 50)
print("  card_gen (Playwright)")
print("=" * 50)
import card_gen
try:
    card_gen.main()
except Exception as e:
    print(f"card_gen 失败: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 50)
print("  QA 质检")
print("=" * 50)
try:
    from wechat_image_qa import run_qa
    ok, msg = run_qa()
    print(f"  QA: {msg}")
except Exception as e:
    print(f"  QA 跳过: {e}")

print()
print("=" * 50)
print("  公众号文章生成")
print("=" * 50)
import wechat_article_gen
try:
    wechat_article_gen.gen_article()
except Exception as e:
    print(f"公众号文章失败: {e}")
    import traceback; traceback.print_exc()
