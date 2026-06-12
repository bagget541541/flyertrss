"""飞客信用卡日报 - 一键生成（抓取→富化→分类→卡片→部署→文章）"""
import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import subprocess,sys,os,shutil,io,argparse
from datetime import datetime
import settings

cwd=settings.CWD
os.chdir(str(cwd))

# ── 版次 + 模式参数 ──
parser=argparse.ArgumentParser(description="飞客信用卡日报 一键生成")
parser.add_argument("--edition",choices=["早报","晚报"],default=None,
                    help="版次，默认 12:00 前=早报, 12:00 后=晚报")
parser.add_argument("--mode",choices=["simple","full"],default="simple",
                    help="运行模式: simple(默认,仅公众号文章+封面), full(含卡片图+QA+部署)")
args=parser.parse_args()
edition=args.edition
if edition is None:
    h=datetime.now().hour
    edition="早报" if h<12 else "晚报"

def log(m):
 t=datetime.now().strftime("%H:%M:%S")
 print(f"[{t}] {m}")

log(f"版次: {edition}   模式: {'完整' if args.mode == 'full' else '简易'}")

def _run(script,step_timeout=120,extra_args=None):
 """运行子进程（最多等待 step_timeout 秒），流式输出"""
 import threading
 cmd=[sys.executable,script]
 if extra_args:
  cmd.extend(extra_args)
 p=subprocess.Popen(cmd,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 lines=[]
 def _out(src):
  for line in iter(src.readline,''):
   if not line: break
   ln=line.decode("utf-8",errors="replace").rstrip()
   lines.append(ln)
   sys.stdout.buffer.write(("  "+ln+"\n").encode("utf-8"))
   sys.stdout.buffer.flush()
 t1=threading.Thread(target=_out,args=(p.stdout,),daemon=True);t1.start()
 # 读取 stderr（后台线程）
 def _err():
  for line in iter(p.stderr.readline,''):
   if not line: break
   ln=line.decode("utf-8",errors="replace").rstrip()
   if "Exception" in ln or "Traceback" in ln or "Error" in ln:
    sys.stdout.buffer.write(("  ! "+ln+"\n").encode("utf-8"));sys.stdout.buffer.flush()
 threading.Thread(target=_err,daemon=True).start()
 try:
  p.wait(timeout=step_timeout)
 except subprocess.TimeoutExpired:
  p.kill()
  p.wait()
  log(f"  ⏰ {script} 超时 ({step_timeout}s)，已终止")
 return p.returncode,lines

print()
print("="*54)
print("  飞客信用卡日报")
print("="*54)

# ── Step 1-3: 公共步骤（无论模式都执行） ──

log("Step 1: 抓取...")
_rc, _ = _run("fetcher.py")
if _rc != 0:
    log("  ⚠️ 抓取失败，继续...")

log("Step 2: LLM 富化...")
_rc, _ = _run("enrich.py", step_timeout=600, extra_args=["--edition", edition])
if _rc != 0:
    log("  ⚠️ enrich 失败，继续...")

log("Step 3: 分类+日报...")
if args.mode == "full":
    _rc, _ = _run("summary.py")
else:
    # 简易模式：规则分类（不调LLM）+ 跳过 PNG 截图（不启动 Playwright）
    _rc, _ = _run("summary.py", extra_args=["--rule-only", "--skip-png"])
if _rc != 0:
    log("  ⚠️ summary 失败，继续...")

if args.mode == "full":
    # ======== 完整模式 ========

    # --- Step 4: 卡片生成 ---
    log("Step 4: 卡片生成...")
    _rc, _ = _run("card_gen.py", step_timeout=900)
    if _rc != 0:
        log("  ⚠️ card_gen 失败，继续...")

    # --- Step 4.5: QA 质检 ---
    log("Step 4.5: QA 质检...")
    try:
        from wechat_image_qa import run_qa
        ok, msg = run_qa()
        if ok:
            log(f"  QA 完成: {msg}")
        else:
            log(f"  ⚠️ QA 失败: {msg}")
    except Exception as e:
        log(f"  ⚠️ QA 跳过: {e}")

    # --- Step 5: 部署预备 ---
    log("Step 5: 部署预备...")

    # 日报 .html 文件已在根目录，生成 index.html
    ds=datetime.now().strftime("%Y-%m-%d")
    htmls=sorted([f for f in os.listdir(".") if f.startswith("日报_") and f.endswith(".html")],reverse=True)
    if not htmls:
        log("  ⚠️ 未找到日报文件，跳过 index.html 生成")
    else:
        idx='''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>飞客信用卡日报</title><link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@600;700;900&family=Inter+Tight:wght@400;500;600;700;800&display=swap" rel="stylesheet"><style>*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}body{font-family:"Inter Tight",-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f6f8fa;color:#1e293b;padding:0 0 60px}.hero{background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%);color:#fff;padding:44px 0 36px;margin-bottom:28px;position:relative;overflow:hidden}.hero .container{max-width:640px;margin:0 auto;padding:0 20px;position:relative;z-index:1}.hero h1{font-family:"Noto Serif SC",serif;font-size:28px;font-weight:900}.hero h1 span{color:#fbbf24}.hero .sub{display:flex;align-items:center;gap:12px;margin-top:8px;font-size:14px;color:#94a3b8}.container{max-width:640px;margin:0 auto;padding:0 20px}.card{background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04);padding:24px 28px;margin-bottom:16px}.card ul{list-style:none;padding:0}.card li{padding:10px 0;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;gap:12px}.card li:last-child{border-bottom:none}.card li a{color:#1e293b;text-decoration:none;font-weight:500;font-size:15px;transition:color 0.15s}.card li a:hover{color:#4f46e5}.card .idx{font-size:13px;font-weight:700;color:#6366f1;min-width:28px;text-align:right}.footer{text-align:center;padding:32px 16px 0;color:#94a3b8;font-size:13px}@media(max-width:600px){.hero{padding:32px 0 28px}.hero h1{font-size:22px}.container{padding:0 12px}.card{padding:18px 16px;border-radius:12px}.card li a{font-size:14px}}</style></head><body><div class="hero"><div class="container"><h1>飞客<span>信用卡</span>日报</h1><div class="sub">历史归档</div></div></div><div class="container"><div class="card"><ul>'''
        for i, h in enumerate(htmls, 1):
            d=h.replace("日报_","").replace(".html","")
            idx+=f'<li><span class="idx">#{i}</span><a href="{h}">{d}</a></li>'
        idx+='</ul></div><div class="footer">自动生成 · '+ds+'</div></body></html>'

        with open("index.html","w",encoding="utf-8") as f:
            f.write(idx)
        log("  index.html（根目录）")

    # 同时保留 _site/（供 COS 部署用）
    os.makedirs("_site",exist_ok=True)
    for f in htmls:
        shutil.copy2(f,"_site/"+f)
    with open("_site/index.html","w",encoding="utf-8") as f:
        f.write(idx)
    print()
    log("全部完成！")
    print("="*54)

    # --- Step 6: 公众号文章（完整模式：含卡片图） ---
    print()
    log("Step 6: 公众号文章...")
    subprocess.run([sys.executable, "wechat_article_gen.py"], cwd=cwd)
    print("="*54)

else:
    # ======== 简易模式（默认）：仅封面 + 公众号文章 ========

    # --- Step 4: 轻量封面生成（跳过卡片生成，只产出 cover_wechat.png） ---
    log("Step 4: 封面生成...")
    _rc, _ = _run("cover_gen.py", step_timeout=120)
    if _rc != 0:
        log("  ⚠️ 封面生成失败（公众号文章将缺少封面图）")

    # --- Step 5: 公众号文章（简易模式：--no-cards 不触发 card_gen） ---
    print()
    log("Step 5: 公众号文章...")
    _rc, _ = _run("wechat_article_gen.py", step_timeout=120, extra_args=["--no-cards"])
    if _rc != 0:
        log("  ⚠️ 公众号文章生成失败")
    print("="*54)

    log("简易模式完成！输出文件：")
    ds = datetime.now().strftime("%Y-%m-%d")
    from pathlib import Path
    article_dir = Path(cwd) / "_site"
    cover_file = Path(cwd) / "_cards" / "cover_wechat.png"
    if cover_file.exists():
        log(f"  📷 封面图: {cover_file}")
    paste_file = article_dir / f"公众号粘贴版_{ds}.html"
    if paste_file.exists():
        log(f"  📄 粘贴版: {paste_file}")
    else:
        log(f"  ⚠️ 粘贴版未生成，请检查错误日志")
    print("="*54)
    log("提示: 如需卡片图 + QA + 部署，请使用 --mode full")
    print("="*54)
