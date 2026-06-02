# 飞客信用卡日报 — {{ ds }}

> 共 **{{ total }}** 条讨论

{% if ht %}
## 🔥 热门讨论（回复 > 30）
{% for t in ht %}
1. [{{ t.title }}]({{ t.url }}) — *{{ t.author }}*（{{ t.replies }}回 / {{ t.views }}阅）
{% endfor %}
{% endif %}

{% for cat in CATS %}{% if gr[cat] %}
## {{ cat }}
{% for t in gr[cat] %}
- [{{ t.title }}]({{ t.url }}) — {{ t.author }}（{{ t.replies }}回 / {{ t.views }}阅）
{% endfor %}
{% endif %}{% endfor %}

---
*自动生成于 {{ ds }} | 数据来源：[飞客茶馆](https://www.flyert.com.cn/)*
