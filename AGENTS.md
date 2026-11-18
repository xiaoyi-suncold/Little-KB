# AGENTS.md — Little KB（本地文件夹知识库）

本文件给 AI / QQ 远程协助用：在这个目录里工作时先读这里。

## 这是什么

一个零第三方依赖的个人知识库系统：文件以原始格式存放在 `kb/`，SQLite FTS5 做全文检索，
自带深色 Web 界面。没有向量库、没有 embedding、不需要装包。

## 目录

```
kbcore/      核心库：config / textutil / extract / index / library / keywords / graph
server.py    HTTP 服务（标准库实现，静态资源 + JSON API）
web/         前端 index.html / style.css / app.js / graph.js（原生 JS，无构建）
scripts/kb.py 命令行工具（写笔记 / 检索 / 统计），给 Agent 用，不依赖服务
scripts/smoke_test.py  端到端冒烟（上传→检索→改标签→删除→重建索引）
kb/          知识库正文，子文件夹即分类（协议/研究/记忆/无人机/技术笔记/工作记录…）
data/        kb.sqlite3（索引，可删可重建）、kb.port
run.cmd / run.ps1   启动脚本（run.cmd 会自动挑 .venv 或 DSH 自带 python）
```

## 怎么跑

- 启动：`run.cmd`（或 `.\run.ps1 --port 9000`）。默认端口 8777，被占用会顺延，实际端口写在 `data\kb.port`。
- 已经在跑时不要重复启动：先 `netstat -ano | findstr :8777` 或读 `data\kb.port`。
- python 用哪个都行；机器上可用的是 DSH 自带那份：
  `C:\Users\84216\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`
  `run.cmd` 已内置该回退，直接调用 `run.cmd` 最省事。

## 常用命令（在仓库根目录执行）

```bat
python scripts\kb.py stats                       :: 概况：文档数、切片数、分类
python scripts\kb.py search "中文 索引" --limit 5 :: 检索（多词 AND）
python scripts\kb.py note "标题" "正文" --category 记忆 --tags 检索,sqlite
python scripts\kb.py log "一句话结论" "细节" --source "来源"
python scripts\kb.py digest 3 --preview 160      :: 看结构：标题树/切片/关键词
python scripts\kb.py show 3 --chars 4000         :: 读正文
```

HTTP 等价接口：`POST /api/note`、`POST /api/reindex`、`GET /api/search?q=`（服务在跑时可直接 curl）。

## 作答约定

- 规则写死在库内：`kb/协议/学习与作答协议.md`（收到材料怎么入库、怎么验证、答案结构）。涉及知识库内容的问题先按它走。
- 答案结构：结论先行 → 机制 → 实现 → 代价与失败模式 → 怎么验证 → 参考；没跑过的写「设计」，不写「实现」。
- 事实性结论尽量两个独立来源；只有一个来源要标注「单一来源，待验证」。

## 在 QQ 里被问到时

- 用户是在 QQ 私聊里提问，回答会被原样转发到 QQ：**纯文本、不用 Markdown**（QQ 不渲染）、代码块用缩进或短行、控制在 10 行以内。
- 需要动手时就直接做（读文件、检索、跑 kb.py、起服务），做完用一两句话给结论 + 关键路径；不要把整段日志贴回去。
- 涉及删除/覆盖 `kb/` 里的文件时先说明要删什么，等用户确认。

## 刷抖音（可选玩法）

桥接侧有两个脚本，可以在 QQ 里被指挥着跑：

- `node D:\ruanjian\qq-bridge\scripts\douyin-scroll.mjs --minutes 2 --notify`
  用本机 Chrome（独立 profile：`qq-bridge\state\chrome-douyin-profile`）打开抖音推荐流，
  人类式滚动/停留，抓标题+作者到 `qq-bridge\state\douyin\seen-<日期>.jsonl`；
  加 `--notify` 会把前三条发到群里。第一次跑如果要求登录，在那个 Chrome 窗口扫码一次即可。
- 定时任务 `QQB-DouyinDigest`（每天 13:30 / 21:30，各 4 分钟）跑完会把标题写进
  `kb\记忆\抖音刷到的 <日期>.md`，所以被问"最近刷到什么"时直接 `kb.py search 抖音` 就能答。

注意：抖音有风控，别连着刷很久；脚本已经做了随机幅度滚动和 2.5–12 秒随机停留。
