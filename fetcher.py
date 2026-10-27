# fresh
import argparse,json,os,re,sys,time,subprocess
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
if sys.platform=="win32": sys.stdout.reconfigure(encoding="utf-8",errors="replace")
import settings
from flyert_access import guarded_main, before_request, pause, check_response, AccessPaused
from flyert_access import curl_fetch as guarded_curl_fetch, chrome_cdp_fetch
PROXY=settings.PROXY
BASE_URL=settings.BASE_URL
AD_KW=settings.AD_KW
MIN_TITLE=settings.MIN_TITLE
MIN_REP=settings.MIN_REP
MIN_VIEW=settings.MIN_VIEW
WRD=settings.WAF_RETRY_DELAYS
_b=None;_ctx=None;_pw=None
_method='auto'


_b=None;_ctx=None

def f(x):
 if not x: return None
 return True

def _ensure_browser():
 global _b,_ctx,_pw
 if _b: return _ctx
 from playwright.sync_api import sync_playwright
 raise RuntimeError('legacy browser launcher disabled; use Chrome CDP session')

def _is_waf(h):
 head = h[:8192].lower()
 return any(x in head for x in (
  "403 forbidden", "access denied", "too many requests",
  "cf-chl-", "checking your browser", "just a moment...",
 ))

def close_browser():
 global _b,_ctx,_pw
 if _b: _b.close();_b=None;_ctx=None
 if _pw: _pw.stop();_pw=None

def fetch_page_pw(url):
 return chrome_cdp_fetch(url)

def fetch_page_httpx(url):
 try:
  before_request()
  import httpx
  h={"User-Agent":"Mozilla/5.0","Accept":"text/html,*/*"}
  with httpx.Client(follow_redirects=True,trust_env=False) as c:
   r=c.get(url,headers={**h,"Referer":BASE_URL+"/"},timeout=15)
   check_response(r.status_code,r.headers,r.text)
   if r.status_code==200: return r.text
 except AccessPaused: raise
 except Exception: raise
 return None

def fetch_page_curl(url):
 return guarded_curl_fetch(url).decode('gbk',errors='replace')

def detect_total_pages(html):
 pg=re.search(chr(62)+chr(60)+chr(47)+chr(100)+chr(105)+chr(118)+chr(62),html,re.DOTALL)
 if not pg: return 1
 nums=re.findall(chr(62)+chr(92)+chr(100)+chr(43)+chr(60),pg.group())
 if nums: return max(int(n) for n in nums)
 return 1
def build_page_url(p):
 if p==1: return BASE_URL+'/forum.php?mod=forumdisplay&fid=59'
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
  vw='?';rp='?';ve=tb.select_one('.viewreply_t');reply_node=tb.select_one('.viewreply_b')
  if ve: vw=ve.get_text(strip=True)
  if reply_node: rp=reply_node.get_text(strip=True)
  activity = ''
  for node in tb.select('[title], .by em, .by span, .lastpost'):
   value = node.get('title') or node.get_text(' ', strip=True)
   if re.search(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}', value):
    activity = value
    break
  threads.append({'tid':tid,'title':title,'category':cat,'author':au,'views':vw,
                  'replies':rp,'url':link,'last_activity':activity})
 return threads


def parse_activity(value):
 if not value: return None
 match = re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:\D+(\d{1,2}):(\d{2}))?', value)
 if not match: return None
 try:
  return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)),
                  int(match.group(4) or 0), int(match.group(5) or 0))
 except ValueError: return None

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
 method = {'auto': fetch_page_pw, 'pw': fetch_page_pw,
           'httpx': fetch_page_httpx, 'curl': fetch_page_curl}[_method]
 client = 'pw' if _method == 'auto' else _method
 try:
  html = method(url)
 except AccessPaused: raise
 except Exception as exc:
  # Keep the first diagnostic line; Playwright may append a long call log.
  detail = next((line.strip() for line in str(exc).splitlines() if line.strip()), '')[:400]
  pause(f'List fetch failed [{client}]: {type(exc).__name__}: {detail}; no automatic client switching', 30 * 60)
 if not html:
  pause(f'List fetch failed [{client}]: empty response; no automatic client switching', 30 * 60)
 return html

def fetch_with_retry(url,waf_retries=0):
 for a in range(waf_retries+1):
  html=fetch_page(url)
  if html: return html
  if a<waf_retries:
   d=[30,120,600][a];print(f"WAF block,wait {d}s");import time;time.sleep(d)
 return None

def filter_threads(threads, since=None):
 seen=load_seen()
 kept=[];dropped=[]
 timed=0
 for t in threads:
  activity_text = t.get('last_activity', '')
  activity = parse_activity(activity_text)
  if since and activity:
   timed += 1
   # Forum list pages often expose only the activity date, not its time.
   # Compare those values by calendar day so today's posts are not treated
   # as midnight activity before a same-day run window.
   date_only = bool(re.fullmatch(r'\s*20\d{2}[-/]\d{1,2}[-/]\d{1,2}\s*', activity_text))
   before_since = activity.date() < since.date() if date_only else activity < since
   if before_since:
    t['_dr']='before_since';dropped.append(t);continue
  if t['tid'] in seen and not (since and activity and activity >= since): t['_dr']='seen';dropped.append(t);continue
  r=is_noise(t)
  if r: t['_dr']=r;dropped.append(t);continue
  kept.append(t)
 return kept,dropped,timed

def main():
 global _method
 import argparse,json,time
 parser=argparse.ArgumentParser(description='flyert crawler v2')
 parser.add_argument('--pages',type=int,default=1,help='pages to fetch (default 1)')
 parser.add_argument('--all',action='store_true',help='fetch all pages')
 parser.add_argument('--no-waf-retry',action='store_true',help='skip waf retry (debug)')
 parser.add_argument('--method',choices=['pw','httpx','curl','auto'],default='auto')
 parser.add_argument('--defer-seen',action='store_true',
                     help='仅输出本轮帖子，不立即写入 seen_tids.json（由一键流程成功后提交）')
 parser.add_argument('--since', default='', help='仅保留该时间之后的最后活动帖子（ISO 格式）')
 args=parser.parse_args()
 _method=args.method
 
 url=build_page_url(1)
 print(chr(128269)+' Page 1: '+url)
 if args.no_waf_retry: html=fetch_page(url)
 else: html=fetch_with_retry(url)
 
 if not html:
  print(chr(10060)+' Failed (WAF or network)')
  close_browser()
  return 2
 
 total=detect_total_pages(html)
 print(chr(128196)+' Total pages: '+str(total))
 pages=total if args.all else min(args.pages,total)
 
 all_threads=[]
 t=parse_threads(html)
 all_threads.extend(t)
 print('  Page 1 -> '+str(len(t))+' posts')
 
 # 默认只抓请求的页数；简易模式不因首屏数量自动扩容。
 
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
 
 since = None
 if args.since:
  try: since = datetime.fromisoformat(args.since).replace(tzinfo=None)
  except ValueError: print('[!] since 时间格式无效，忽略时间窗口')
 kept,dropped,timed=filter_threads(all_threads, since)
 if since and not timed:
  print('[!] 列表未解析到可用最后活动时间，本次保留当前页结果，未执行时间过滤')
 elif since:
  print(f'[time] 窗口起点: {since.isoformat(sep=" ")}，解析到 {timed}/{len(all_threads)} 条')
 print(chr(10)+'=== Kept: '+str(len(kept))+' ===')
 for i,t in enumerate(kept,1):
  print(str(i)+'. ['+t['category']+'] '+t['title']+' ('+t['replies']+'r/'+t['views']+'v)')
 
 if dropped:
  print(chr(10)+'=== Dropped: '+str(len(dropped))+' ===')
  for t in dropped: print('  x ['+t['category']+'] '+t['title']+' -> '+t.get('_dr','?'))
 
 new={t['tid'] for t in kept}
 if new and not args.defer_seen:
  seen=load_seen()
  seen.update(new)
  save_seen(seen)
  print(chr(10)+chr(128187)+' Saved '+str(len(new))+' new tids')
 elif new:
  print(chr(10)+'[defer] 暂不提交 '+str(len(new))+' 个新 tids，等待整条流程成功')
 
 import json
 with open('threads_raw.json','w',encoding='utf-8') as f: json.dump(all_threads,f,ensure_ascii=False,indent=2)
 with open('threads_filtered.json','w',encoding='utf-8') as f: json.dump(kept,f,ensure_ascii=False,indent=2)
 print(chr(128187)+' threads_raw.json ('+str(len(all_threads))+') + threads_filtered.json ('+str(len(kept))+')')
 if not kept:
  return 3
 return 0

main = guarded_main(main)

if __name__=='__main__':
 try:
  sys.exit(main())
 finally:
  close_browser()
