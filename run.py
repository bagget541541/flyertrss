# -*- coding: utf-8 -*-
"""飞客信用卡日报 - 一键生成（抓取→分类→渲染→部署预备）"""
import subprocess,sys,os,shutil,io
from datetime import datetime

cwd=os.path.dirname(os.path.abspath(__file__))or"."
os.chdir(cwd)
def log(m):
 t=datetime.now().strftime("%H:%M:%S")
 print(f"[{t}] {m}")

def _run(script):
 """运行子进程，返回 (returncode, stdout_lines) 自动处理 GBK 编码"""
 p=subprocess.run([sys.executable,script],capture_output=True,cwd=cwd)
 enc="utf-8"
 out=p.stdout.decode(enc,errors="replace")
 if p.stderr: err=p.stderr.decode(enc,errors="replace")
 else: err=""
 if not out.strip() and err.strip():
  out=p.stdout.decode("gbk",errors="replace")
  err=p.stderr.decode("gbk",errors="replace")
 lines=out.splitlines()
 for l in lines: sys.stdout.buffer.write((f"  {l}\n").encode("utf-8"));sys.stdout.buffer.flush()
 if err:
  for l in err.splitlines():
   if "Exception" in l or "Traceback" in l or "Error" in l:
    sys.stdout.buffer.write((f"  ! {l}\n").encode("utf-8"));sys.stdout.buffer.flush()
 return p.returncode,lines

print()
print("="*54)
print("  飞客信用卡日报")
print("="*54)

log("Step 1: 抓取...")
rc1,_=_run("fetcher.py")
if rc1!=0:
 sys.exit(1)

log("Step 2: 分类+日报...")
rc2,lines=_run("summary.py")
if rc2!=0:
 sys.exit(2)

# --- Step 3 部署预备 ---
log("Step 3: 部署预备...")

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
log("完成！")
print("="*54)
