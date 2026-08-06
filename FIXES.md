# 修复记录

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

## 2026-08-03：微信发布流程改进

### 修复内容
1. **标题截断**：`fetch_threads_detail.py` 补全标题
2. **LLM 重试**：5 次重试 + 指数退避（1s/2s/4s/8s）
3. **链接数**：动态链接数，不再硬编码 8 条限制

详见 `fixes_2026-08-03.md`
