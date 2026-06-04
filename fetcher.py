# fresh
import argparse,json,os,re,sys,time,subprocess
from pathlib import Path
from bs4 import BeautifulSoup
if sys.platform=="win32": sys.stdout.reconfigure(encoding="utf-8",errors="replace")
import settings
PROXY=settings.PROXY
BASE_URL=settings.BASE_URL
AD_KW=settings.AD_KW
MIN_TITLE=settings.MIN_TITLE
MIN_REP=settings.MIN_REP
MIN_VIEW=settings.MIN_VIEW
WRD=settings.WAF_RETRY_DELAYS
_b=None;_ctx=None


_b=None;_ctx=None

def f(x):
 if not x: return None
 return True

def _ensure_browser():
 global _b,_ctx
 if _b: return _ctx
 from playwright.sync_api import sync_playwright
 pw=sync_playwright().start()
 _b=pw.chromium.launch(headless=True)
 _ctx=_b.new_context()
 return _ctx

def _is_waf(h):
 return ("403 Forbidden" in h[:200] and "Access Denied" in h[:200])

def close_browser():
 global _b,_ctx
 if _b: _b.close();_b=None;_ctx=None

def fetch_page_pw(url):
 ctx=_ensure_browser();pg=ctx.new_page()
 try:
  pg.goto(url,wait_until="domcontentloaded",timeout=25000)
  import time;time.sleep(2)
  h=pg.content()
  if _is_waf(h): return None
  return h
 except: return None
 finally: pg.close()

def fetch_page_httpx(url):
 try:
  import httpx
  h={"User-Agent":"Mozilla/5.0","Accept":"text/html,*/*"}
  with httpx.Client(verify=False,follow_redirects=True) as c:
   c.get(BASE_URL+"/",headers=h,timeout=15)
   r=c.get(url,headers={**h,"Referer":BASE_URL+"/"},timeout=15)
   if r.status_code==200 and not _is_waf(r.text): return r.text
 except: return None
 return None

def fetch_page_curl(url):
 import subprocess as sp
 cmd=["curl","-sSL","--connect-timeout","10","--max-time","20","-A","Mozilla/5.0","-H","Referer: https://www.flyert.com.cn/","-x",PROXY,url]
 try:
  raw=sp.check_output(cmd)
  t=raw.decode("gbk",errors="replace")
  return None if _is_waf(t) else t
 except: return None

def detect_total_pages(html):
 pg=re.search(chr(62)+chr(60)+chr(47)+chr(100)+chr(105)+chr(118)+chr(62),html,re.DOTALL)
 if not pg: return 1
 nums=re.findall(chr(62)+chr(92)+chr(100)+chr(43)+chr(60),pg.group())
 if nums: return max(int(n) for n in nums)
 return 1
def build_page_url(p):
 if p==1: return BASE_URL+chr(47)+chr(102)+chr(111)+chr(114)+chr(117)+chr(109)+chr(45)+chr(99)+chr(114)+chr(101)+chr(100)+chr(105)+chr(116)+chr(99)+chr(97)+chr(114)+chr(100)+chr(45)+chr(49)+chr(46)+chr(104)+chr(116)+chr(109)+chr(108)
 return BASE_URL+chr(47)+chr(102)+chr(111)+chr(114)+chr(117)+chr(109)+chr(46)+chr(112)+chr(104)+chr(112)+chr(63)+chr(109)+chr(111)+chr(100)+chr(61)+chr(102)+chr(111)+chr(114)+chr(117)+chr(109)+chr(100)+chr(105)+chr(115)+chr(112)+chr(108)+chr(97)+chr(121)+chr(38)+chr(102)+chr(105)+chr(100)+chr(61)+chr(53)+chr(57)+chr(38)+chr(112)+chr(97)+chr(103)+chr(101)+chr(61)+str(p)

def parse_threads(html):
 from bs4 import BeautifulSoup as BS
 soup=BS(html,'html.parser')
 threads=[]
 for tb in soup.find_all('tbody',id=lambda x: x and x.startswith('normalthread_')):
  tid=tb.get('id','').replace('normalthread_','')
  te=tb.find('a',href=lambda h: h and 'tid='+tid in (h or ''))
  if not te: continue
  title=te.get_text(strip=True)
  link=te.get('href','')
  if link and not link.startswith('http'): link=BASE_URL+'/'+link.lstrip('/')
  cat='';ce=tb.select_one('em a')
  if ce: cat=ce.get_text(strip=True)
  au='';ae=tb.select_one('a.poster_t')
  if ae: au=ae.get_text(strip=True)
  vw='?';rp='?';ve=tb.select_one('.viewreply_t');re=tb.select_one('.viewreply_b')
  if ve: vw=ve.get_text(strip=True)
  if re: rp=re.get_text(strip=True)
  threads.append({'tid':tid,'title':title,'category':cat,'author':au,'views':vw,'replies':rp,'url':link})
 return threads

def load_seen(path='seen_tids.json'):
 import json
 try:
  with open(path,'r',encoding='utf-8') as f: return set(json.load(f))
 except: return set()

def save_seen(tids,path='seen_tids.json'):
 import json
 with open(path,'w',encoding='utf-8') as f: json.dump(sorted(tids),f,ensure_ascii=False)

def is_noise(t):
 title=t.get('title','')
 try: replies=int(str(t.get('replies','0')).replace(',',''))
 except: replies=0
 try: views=int(str(t.get('views','0')).replace(',',''))
 except: views=0
 for kw in [chr(25910),chr(20195)]:
  if kw in title:
   if replies>=10 and views>=5000: return None
   return 'ad:'+kw
 if len(title.replace(' ',''))<MIN_TITLE: return 'too short'
 if replies<MIN_REP and views<MIN_VIEW: return 'low engagement'
 return None

def fetch_page(url):
 return fetch_page_pw(url) or fetch_page_httpx(url) or fetch_page_curl(url)

def fetch_with_retry(url,waf_retries=3):
 for a in range(waf_retries+1):
  html=fetch_page(url)
  if html: return html
  if a<waf_retries:
   d=[30,120,600][a];print(f"WAF block,wait {d}s");import time;time.sleep(d)
 return None

def filter_threads(threads):
 seen=load_seen()
 kept=[];dropped=[]
 for t in threads:
  if t['tid'] in seen: t['_dr']='seen';dropped.append(t);continue
  r=is_noise(t)
  if r: t['_dr']=r;dropped.append(t);continue
  kept.append(t)
 return kept,dropped

def main():
 import argparse,json,time
 parser=argparse.ArgumentParser(description='flyert crawler v2')
 parser.add_argument('--pages',type=int,default=1,help='pages to fetch (default 1)')
 parser.add_argument('--all',action='store_true',help='fetch all pages')
 parser.add_argument('--no-waf-retry',action='store_true',help='skip waf retry (debug)')
 parser.add_argument('--method',choices=['pw','httpx','curl','auto'],default='auto')
 args=parser.parse_args()
 
 url=build_page_url(1)
 print(chr(128269)+' Page 1: '+url)
 if args.no_waf_retry: html=fetch_page(url)
 else: html=fetch_with_retry(url)
 
 if not html:
  print(chr(10060)+' Failed (WAF or network)')
  close_browser()
  return
 
 total=detect_total_pages(html)
 print(chr(128196)+' Total pages: '+str(total))
 pages=total if args.all else min(args.pages,total)
 
 all_threads=[]
 t=parse_threads(html)
 all_threads.extend(t)
 print('  Page 1 -> '+str(len(t))+' posts')
 
 for p in range(2,pages+1):
  delay=1.0+(hash(str(p))%10)/10
  time.sleep(delay)
  u=build_page_url(p)
  print(chr(128269)+' Page '+str(p)+': '+u)
  if args.no_waf_retry: h=fetch_page(u)
  else: h=fetch_with_retry(u)
  if not h: print('  skip page '+str(p));continue
  t=parse_threads(h)
  all_threads.extend(t)
  print('  Page '+str(p)+' -> '+str(len(t))+' (total '+str(len(all_threads))+')')
 
 print(chr(10004)+' Total fetched: '+str(len(all_threads)))
 close_browser()
 
 kept,dropped=filter_threads(all_threads)
 print(chr(10)+'=== Kept: '+str(len(kept))+' ===')
 for i,t in enumerate(kept,1):
  print(str(i)+'. ['+t['category']+'] '+t['title']+' ('+t['replies']+'r/'+t['views']+'v)')
 
 if dropped:
  print(chr(10)+'=== Dropped: '+str(len(dropped))+' ===')
  for t in dropped: print('  x ['+t['category']+'] '+t['title']+' -> '+t.get('_dr','?'))
 
 new={t['tid'] for t in kept}
 if new:
  seen=load_seen()
  seen.update(new)
  save_seen(seen)
  print(chr(10)+chr(128187)+' Saved '+str(len(new))+' new tids')
 
 import json
 with open('threads_raw.json','w',encoding='utf-8') as f: json.dump(all_threads,f,ensure_ascii=False,indent=2)
 with open('threads_filtered.json','w',encoding='utf-8') as f: json.dump(kept,f,ensure_ascii=False,indent=2)
 print(chr(128187)+' threads_raw.json ('+str(len(all_threads))+') + threads_filtered.json ('+str(len(kept))+')')

if __name__=='__main__': main()
