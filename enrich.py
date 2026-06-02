import json,os,sys,httpx,re
from pathlib import Path
cwd=Path(".");os.chdir(str(cwd))
sys.stdout.reconfigure(encoding="utf-8",errors="replace")
cfg=json.loads(Path("C:/Users/idriver/.llm_config.json").read_text(encoding="utf-8"))
K,B,M=cfg["api_key"],cfg["api_base"],cfg.get("model","mimo-turbo")
data=json.loads((cwd/"threads_filtered.json").read_text(encoding="utf-8"))
print(f"data:{len(data)}")
S="You are a helpful assistant. Output ONLY JSON array. Each item: summary(Chinese 10chars) value_tag(one of: xianshi/bikeng/gonglue/gonggao/taolun/shiice)"
U=chr(10).join(f"{i+1}. {t["title"]}" for i,t in enumerate(data))
U+=chr(10)+"Return ONLY a JSON array. Example: "+chr(123)+chr(34)+"summary"+chr(34)+chr(58)+chr(34)+"经典白清退指南"+chr(34)+chr(44)+chr(34)+"value_tag"+chr(34)+chr(58)+chr(34)+"gonglue"+chr(34)+chr(125)
print("LLM...")
resp=httpx.post(f"{B}/chat/completions",headers={"Authorization":f"Bearer {K}"},json={"model":M,"messages":[{"role":"system","content":S},{"role":"user","content":U}],"temperature":0.3,"max_tokens":8192},timeout=120)
raw=resp.json()["choices"][0]["message"]["content"]
m=re.search(r"\[.*\]",raw,re.DOTALL)
if not m:print("err:",raw[:300]);exit()
enriched=json.loads(m.group())
if isinstance(enriched,dict):enriched=list(enriched.values())
print(f"parsed:{len(enriched)}")
TM={"xianshi":"限时","bikeng":"避坑","gonglue":"攻略","gonggao":"公告","taolun":"讨论","shiice":"实测"}
for i,t in enumerate(data):
    if i<len(enriched) and isinstance(enriched[i],dict):
        rt=enriched[i].get("value_tag","").lower()
        t["summary"]=enriched[i].get("summary",t["title"][:12])
        t["value_tag"]=TM.get(rt,"讨论")
    else: t["summary"]=t["title"][:12];t["value_tag"]="讨论"
(cwd/"threads_enriched.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
print("saved")