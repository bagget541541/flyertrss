# -*- coding: utf-8 -*-
"""飞客信用卡日报 - LLM分类+日报渲染"""
import json,os,httpx,jinja2,sys
from datetime import date
from pathlib import Path
from collections import Counter

def o(t): sys.stdout.buffer.write((t+"\n").encode("utf-8"));sys.stdout.buffer.flush()
C=Path("C:/Users/idriver/.llm_config.json")
LLM_OK=False;KEY="";BASE="";MODEL=""
try:
 with open(C,encoding="utf-8") as f:
  d=json.load(f);KEY=d.get("api_key","");BASE=d.get("api_base","");MODEL=d.get("model","mimo-v2.5");LLM_OK=bool(KEY and BASE)
except: print("no LLM, rule-only")
CATS=[chr(30003)+chr(21345)+chr(19979)+chr(21345),chr(26435)+chr(30410)+chr(21464)+chr(21270),chr(27963)+chr(21160)+chr(20248)+chr(24871),chr(30097)+chr(38382)+chr(27714)+chr(21161),chr(29992)+chr(21345)+chr(32463)+chr(39564),chr(38957)+chr(24230)+chr(35770)+chr(35770),chr(20854)+chr(20182)]
RULES={
 chr(30003)+chr(21345)+chr(19979)+chr(21345):[chr(19979)+chr(21345),chr(25209)+chr(21345),chr(30003)+chr(21345),chr(30003)+chr(35831),chr(31186)+chr(25209),chr(23457)+chr(26680),chr(36976)+chr(35831)],
 chr(26435)+chr(30410)+chr(21464)+chr(21270):[chr(26435)+chr(30410),chr(32553)+chr(27700),chr(21462)+chr(28040),chr(28201)+chr(26262)+chr(21319)+chr(32423),chr(35843)+chr(25972),chr(31215)+chr(20998)+chr(36133)+chr(20540)],
 chr(27963)+chr(21160)+chr(20248)+chr(24871):[chr(27963)+chr(21160),chr(20248)+chr(24871),chr(36820)+chr(29616),chr(28385)+chr(20943),chr(36865)+chr(31215)+chr(20998),chr(32418)+chr(21253),chr(23545)+chr(25442)],
 chr(30097)+chr(38382)+chr(27714)+chr(21161):[chr(38382),chr(27714)+chr(21161),chr(35831)+chr(25945),chr(24590)+chr(20040)+chr(20040)+chr(21150),chr(32418)+chr(32467),chr(36873)+chr(25362)],
 chr(29992)+chr(21345)+chr(32463)+chr(39564):[chr(32463)+chr(39564),chr(25216)+chr(24039),chr(29609)+chr(27861),chr(25915)+chr(30053),chr(23455)+chr(27979),chr(20998)+chr(20139)],
 chr(38957)+chr(24230)+chr(35770)+chr(35770):[chr(38957)+chr(24230),chr(25552)+chr(38957),chr(20020)+chr(38957),chr(22266)+chr(38957),chr(26354)+chr(32447),chr(25480)+chr(20449)],
}

def classify_rules(ts):
 r={}
 for t in ts:
  cat=t.get("category","")
  if cat in CATS: r[t["tid"]]=cat; continue
  matched=[]
  for cn,kws in RULES.items():
   for kw in kws:
    if kw in t["title"]: matched.append(cn); break
  r[t["tid"]]=max(set(matched),key=matched.count) if matched else CATS[-1]
 return r

def classify_llm(ts):
 L=[f"tid={p['tid']}"+chr(124)+f"{p['title']}"+chr(124)+f"{p['replies']}r/{p['views']}v" for p in ts]
 sp="你是一个信用卡论坛内容分析师。对以下帖子分类。选项："+chr(47).join(CATS)+"。返回JSON数组。只返回JSON。"
 pl={"model":MODEL,"messages":[{"role":"system","content":sp},{"role":"user","content":chr(10).join(L)}],"temperature":0.1,"max_tokens":8192}
 with httpx.Client(timeout=90) as x:
  r=x.post(BASE.rstrip(chr(47))+chr(47)+"chat/completions",json=pl,headers={"Authorization":"Bearer "+KEY})
  r.raise_for_status()
  ct=r.json()["choices"][0]["message"]["content"].strip()
  if not ct:ct=r.json()["choices"][0]["message"].get("reasoning_content","").strip()
  if ct.startswith("```"):ct=ct.split(chr(10),1)[1]
  if ct.endswith("```"):ct=ct[:-3];ct=ct.strip()
  try:
   d=json.loads(ct)
   if isinstance(d,list):return {i["tid"]:i["category"] for i in d}
   return d
  except:raise ValueError("非JSON:"+ct[:200])

def _build_ctx(ts,cats):
 gr={c:[] for c in CATS}
 for t in ts:
  ca=cats.get(t["tid"],CATS[-1]);gr[ca if ca in gr else CATS[-1]].append(t)
 for g in gr.values():g.sort(key=lambda x:int(str(x.get("replies","0")).replace(",","0")),reverse=True)
 ht=[p for p in ts if int(str(p.get("replies","0")).replace(",","0"))>30]
 ht.sort(key=lambda x:int(str(x.get("replies","0")).replace(",","0")),reverse=True)
 return dict(ds=date.today().isoformat(),total=len(ts),ht=ht,gr=gr,CATS=CATS)

def render_md(ts,cats):
 ctx=_build_ctx(ts,cats)
 tpl=open("report_tpl.md",encoding="utf-8").read()
 return jinja2.Environment().from_string(tpl).render(**ctx)

def render_html(ts,cats):
 ctx=_build_ctx(ts,cats)
 tpl=open("report_tpl.html",encoding="utf-8").read()
 return jinja2.Environment().from_string(tpl).render(**ctx)

def export_png(html_path,png_path):
 try:
  from playwright.sync_api import sync_playwright
 except ImportError:
  return False,"playwright 未安装，跳过 PNG"
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch()
   page=browser.new_page(viewport={"width":800,"height":1080})
   page.goto("file:///"+html_path.replace("\\","/"),wait_until="networkidle")
   page.wait_for_timeout(500)
   page.screenshot(path=png_path,full_page=True)
   browser.close()
  return True,"OK "+os.path.basename(png_path)
 except Exception as e:
  return False,f"截图失败: {e}"

def main():
 try:
  with open("threads_filtered.json",encoding="utf-8") as f:ts=json.load(f)
 except:o("没有数据");return
 if not ts:o("无新帖");return
 o(f"{len(ts)}条")
 if LLM_OK:
  try:cats=classify_llm(ts)
  except Exception as e:o(f"LLM失败:{e},降级");cats=classify_rules(ts)
 else:cats=classify_rules(ts)
 for c,n in Counter(cats.values()).most_common():o(f"  {c}:{n}")
 md=render_md(ts,cats)
 fn_md="日报_"+date.today().isoformat()+".md"
 with open(fn_md,"w",encoding="utf-8") as f:f.write(md)
 o("OK "+fn_md)
 try:
  html=render_html(ts,cats)
  fn_html="日报_"+date.today().isoformat()+".html"
  with open(fn_html,"w",encoding="utf-8") as f:f.write(html)
  o("OK "+fn_html)
  # 顺便转 PNG 长截图（供公众号贴图）
  fn_png="日报_"+date.today().isoformat()+".png"
  ok,msg=export_png(fn_html,fn_png)
  o(msg)
 except Exception as e:
  o(f"HTML 渲染失败: {e}")
if __name__=="__main__":main()
