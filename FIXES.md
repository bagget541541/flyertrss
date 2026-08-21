# 修复记录

## 2026-08-07：概览清理 + 日期格式修复

### 改进 1：概览部分移除 0 条的分类

#### 问题
生成的日报概览行显示所有分类，包括没有帖子的分类：
```
> 共 17 条讨论 | 新卡发行 0 条 | 权益变更 1 条 | 停发退市 0 条 | ... | 其他 0 条 | 数据源：...
```

这使概览行冗长而不必要。

#### 改进
**位置**：`llm_daily_gen.py:78`

更新 LLM 系统提示，明确指示只列出有内容的分类：
```
- 概览行：`> 共 N 条讨论 | 分类统计 | 数据源：flyert.com.cn 信用卡版块`
  （只列出有内容的分类及其数量，不显示 0 条的分类；去掉抓取时间）
```

**位置**：`docx_to_wechat.py:445-459, 617`

添加 `_clean_category_stats()` 函数做后处理清理，移除任何包含 " 0 条" 的分类项。

#### 效果
改进后的概览行：
```
> 共 17 条讨论 | 权益变更 1 条 | 疑问求助 10 条 | 用卡经验 6 条 | 数据源：...
```

---

### 改进 2：修复微信发布.bat 日期格式问题

#### 问题
`微信发布.bat --resume` 找不到今日 state 日志文件。

原因：Windows 中文系统上 `%date%` 返回 `2026年08月07日` 这样的格式，不是标准 YYYY-MM-DD，导致日期提取失败（`date:~0,4%%date:~5,2%%date:~8,2` 无法正确截取）。

#### 修复
**位置**：`微信发布.bat:5-16`

使用 PowerShell 替代系统 `%date%` 变量，确保一致的日期格式：
```batch
REM 用 PowerShell 取得可靠的日期格式 (YYYYMMDD)
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd'"`) do set "TODAY_DATE=%%i"
for /f "usebackq tokens=*" %%i in (`powershell -NoProfile -Command "Get-Date -Format 'HHmm'"`) do set "TODAY_TIME=%%i"

set "STATE_FILE=%LOG_DIR%\wechat_pub_state_%TODAY_DATE%.txt"
set "LOG_FILE=%LOG_DIR%\wechat_pub_%TODAY_DATE%_%TODAY_TIME%.log"
```

#### 验证
✅ 生成的 state 文件：`wechat_pub_state_20260807.txt`（固定格式）
✅ `--resume` 能正确找到文件并继续运行

---

## 2026-08-06：文件名清理鲁棒性修复

### 问题
`微信发布.bat --resume` Step 3 出错：
```
OSError: [Errno 22] Invalid argument: 'output\精选日报_0806-...*.md'
```

生成的 markdown 文件名中包含 Windows 非法字符 `*`。

### 原因
`llm_daily_gen.py` 第 772 行的文件名清理逻辑不完善：
- 只处理了特定的中文英文标点，但覆盖不全
- 末尾点号 `.` 没有处理（Windows 不允许）
- 某些特殊字符转义不当

### 修复
**位置**：`llm_daily_gen.py:767-774`

改进文件名清理逻辑：
```python
sub = sub.replace("：", "-").replace("｜", " ").replace("…", "")
sub = re.sub(r'[:<>"/\\|?\*]', '', sub)  # 正则表达式统一清理
sub = sub.strip().rstrip(".")  # 移除前后空格和末尾点
if not sub:
    sub = "今日日报"
```

现在通过以下方式处理 Windows 非法字符：
- 正则表达式统一匹配所有非法字符：`< > : " / \ | ? *`
- 明确处理末尾点号（Windows 特殊限制）
- 清理后为空时使用默认值

### 验证
✅ 正则表达式正确转义：`\*` 匹配星号
✅ 支持中文标点正常化
✅ 支持清理边界情况

### 重新运行
```bash
del logs\wechat_pub_state_20260806.txt
微信发布.bat
```

或恢复前次中断：
```bash
微信发布.bat --resume
```

---

## 2026-08-21：HTML 问号 + 概览条目数错误

### 问题 1：HTML 部分帖子显示「? 条回复 · ? 次阅读」

#### 根因
`llm_daily_gen.py` 的 fallback 逻辑（L891-912）在 `len(links) < 10` 时从
`threads_enriched.json` / `threads_filtered.json` 补充旧帖到 `links`，
污染了 `clean_final_markdown` 的 `expected` 集合。LLM 随之把 15 个旧帖
塞进日报，这些旧帖没有 detail 统计，HTML 渲染成 `? 条回复`。

#### 修复
**位置**：`llm_daily_gen.py:886-913`（main）、`616-688`（clean_final_markdown）

1. 在 fallback 之前保存原始 today links 的 tid 集合：
   ```python
   today_tids = {str(it.get("tid", "")) for it in links if it.get("tid")}
   ```
2. `clean_final_markdown` 新增 `today_tids` 参数，严格按 today links
   过滤：
   - tid 不在 today_tids 里的 `###` 块整块剔除（含标题）
   - 热门榜单项若无 tid 且无「N回/N阅」数据，视为旧帖幻觉剔除

### 问题 2：概览显示「共 7 条」但实际有更多帖子

#### 根因
`normalize_category_stats`（L702-735）按 `## 板块` 分组计数 `###` 帖子，
但 LLM 漏写 `## 板块` 标题时，散落的 `###` 被跳过；热门讨论板块下的
`###` 详情卡片也被 `in_hot=True` 跳过，导致概览条目数小于实际。

#### 修复
重写 `normalize_category_stats` 计数逻辑：
- 移除 `in_hot` 跳过逻辑
- 热门讨论板块下的 `###` 详情卡片计入「其他」
- 散落在板块外的 `###` 归入「其他」
- 保证概览总数 = 真实 `###` 帖子数

### 验证（2026-08-21）
- ✅ today links 8 条，md 渲染 8 个 `###` 块，概览「共 8 条」
- ✅ HTML 中 8 条帖子的回复/阅读数全部为真实数字，无 `? 条回复` 残留
- ✅ 旧帖（VISA尊享白金卡申请避坑等 15 个）全部被剔除

---

## 2026-08-03：微信发布流程改进

### 修复内容
1. **标题截断**：`fetch_threads_detail.py` 补全标题
2. **LLM 重试**：5 次重试 + 指数退避（1s/2s/4s/8s）
3. **链接数**：动态链接数，不再硬编码 8 条限制

详见 `fixes_2026-08-03.md`
