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

# --- Step 3 在 Step 2 成功后才执行 ---
log("Step 3: 部署预备（_site/）...")
os.makedirs("_site",exist_ok=True)
for f in os.listdir("."):
 if f.startswith("日报_") and f.endswith(".html"):
  shutil.copy2(f,"_site/"+f);log(f"  _site/{f}")

# 生成 _site/index.html（按日期倒序）
ds=datetime.now().strftime("%Y-%m-%d")
htmls=sorted([f for f in os.listdir(".") if f.startswith("日报_") and f.endswith(".html")],reverse=True)
idx="""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>飞客信用卡日报</title><meta name="viewport" content="width=device-width,initial-scale=1.0"><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;background:#f0f2f5;color:#1f2937;max-width:700px;margin:40px auto;padding:0 20px;line-height:1.8}h1{font-size:24px;border-bottom:2px solid #e5e7eb;padding-bottom:12px}a{color:#4f46e5;text-decoration:none}a:hover{text-decoration:underline}.date{color:#6b7280;font-size:14px;margin-top:30px}}</style></head><body><h1>📬 飞客信用卡日报</h1><ul>"""
for h in htmls:
 d=h.replace("日报_","").replace(".html","")
 idx+=f"<li><a href=\"{h}\">{d}</a></li>"
idx+="</ul><div class=\"date\">自动生成 · "+ds+"</div></body></html>"
with open("_site/index.html","w",encoding="utf-8") as f:f.write(idx)
log("  _site/index.html")
print()
log("完成！")
print("="*54)
