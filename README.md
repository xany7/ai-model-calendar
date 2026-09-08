# 头部 AI 大模型里程碑发布日历

**订阅源：[calendar.ics](https://xany7.github.io/ai-model-calendar/calendar.ics)**  
**在线页面：[AI 里程碑](https://xany7.github.io/ai-model-calendar/)**

一个无需常驻服务器、无需付费模型 API 的公开订阅服务。GitHub 保存来源、规则和事件；GitHub Actions 每日检查并生成标准 ICS；GitHub Pages 通过固定 HTTPS URL 提供订阅。

## 订阅

复制 `https://xany7.github.io/ai-model-calendar/calendar.ics`，在客户端选择**通过网址订阅**。

- **Apple 日历**：Mac「文件 → 新建日历订阅」。iPhone 在日历账户中添加「已订阅的日历」，或使用网页上的订阅按钮。不同系统版本的菜单名称可能不同。
- **Google 日历**：网页版「其他日历 → ＋ → 通过网址」。
- **Outlook**：网页版「添加日历 → 从 Web 订阅」。

直接下载并导入 ICS 不会持续更新。客户端控制自己的抓取/缓存周期；网站更新后可能要等待数小时或更久。ICS 提供 12 小时刷新建议，但不能强制客户端采纳。

## 自动更新与来源

[Daily update & deploy](https://github.com/xany7/ai-model-calendar/actions/workflows/calendar.yml) 默认每天 **北京时间 09:23**（UTC 01:23）运行，也可点击 **Run workflow** 立即检查。

| 厂商 | 官方发现入口 |
| --- | --- |
| OpenAI | 官方 News RSS（含标题、摘要、公告时间） |
| Anthropic | Newsroom 和发布正文 |
| Google | 官方 AI RSS、Gemini 模型博客 |
| xAI | 官方 News 和发布正文 |
| DeepSeek | 官方新闻、API 文档新闻链接 |
| 阿里千问 | 官方 QwenLM GitHub 仓库列表、博客入口 |
| 月之暗面 Kimi | 官方 Research Blog |
| 智谱 GLM | 官方中文模型发布记录 |
| 字节豆包 | Seed 官方博客目录及正文 |

另外每天检查 TechCrunch、The Verge 和 Google News 搜索 RSS。新闻用于发现遗漏，不直接作为自动批准依据。Google News 只是聚合线索，来源可信度必须在审核时逐条确认。千问博客当前依赖客户端渲染；官方 GitHub 作为可用的替代入口。来源异常会在网站及 Actions 摘要中显示。目录解析为空会被当作异常，不被当作「没有新发布」。

每次回看最近 45 天；没有发布日期的仓库/候选保留待核实。每个入口每次最多读取 12 篇新的官方正文，超额留待下次重试。请求有超时、大小限制和重试；单个来源失败不会删除已有日历。数据和健康状态在部署前提交入仓库，构建失败不覆盖现有站点。

首批记录是 **2025 年起的精选历史**，不是完整模型史。每条附公告、日期口径、收录理由；首批由 Codex 逐条核对官方材料。此后的自动收录标记 `rules-v1`，人工工作流审核记录实际 GitHub 操作者。

## 收录与日期口径

- 收录通用旗舰跨代发布、重要推理模型和经审核确认的重大能力跃迁。首次已公开可用的预览版可收录，摘要注明阶段。
- 不单独收录小尺寸/高效型号、例行补丁、降价、产品接入、技术报告，也不把独立图像/视频模型混入通用大模型日历。
- 一个模型记首次公开可用发布。API 后续接入、地区开放、权重补发不重复收录；系列同场发布尽量合并。
- **有可信非午夜时区时间戳**：换算为 `Asia/Shanghai` 的日期，写入全天事件，避免随设备时区漂移。
- **只有日期或疑似午夜占位值**：不虚构时间。自动候选必须审核；首批已核实记录保留官方公告日期，并在事件内注明不能确定北京时间跨日。国外公告日可能与真实北京时间相差一天。
- 官方来源互相冲突时保留证据并进入审核。例如首批 Qwen3.5 使用官方仓库 News 的 2026-02-16，且明确披露博客 02-15 的差异。

规则评分：官方源 40 / 新闻 10；明确已发布 20；旗舰或代际措辞 15；整数主代际 10；有效时区时间戳 15。**达到 95 分还必须同时满足**官方来源、已核实正文/可信官方 RSS、明确发布、旗舰/代际证据、整数主代际、非未来日期、非传闻。小数版本即使宣称旗舰，也默认进入审核。

模型名由标题识别，不从竞品对照表提取。按厂商与标准化模型名去重；追踪参数被去除。未知命名进入候选。新闻不能自动通过；未来日期、命名/日期冲突和正文读取失败均需要审核。

**无法保证完全无人值守或零漏报。** 页面改版、反爬、厂商只在社交媒体首发、RSS 窗口过短、未知命名、规则过严都可能造成遗漏。建议维护者每周查看一次待审核清单及来源状态；用厂商官网核实线索。没有依据时宁可保留待审。收录错误可按下文修正，Git 历史提供可追溯记录。

## 审核、补录与纠错

1. 打开 [待审核清单](https://xany7.github.io/ai-model-calendar/#review)，检查官方原文，复制候选 ID。
2. 打开 [Review a candidate](https://github.com/xany7/ai-model-calendar/actions/workflows/review.yml) → **Run workflow**。
3. 选择 `approve` 或 `reject`。批准时填写模型规范名称、核实后的日历日期 `YYYY-MM-DD`、中文一句话要点、里程碑理由、日期依据。新闻线索必须补充该厂商官方链接。拒绝时只需 ID，可填写排除理由。
4. 工作流记录决策并自动触发部署。审核权限由仓库写权限控制；公开网页不能匿名修改日历。

手动补录：在 `data/events.json` 追加事件，参照现有字段；提交会自动测试、构建与部署。可本地调用 `calendar_service.model_key(vendor, model)` 生成稳定 ID。

纠错：修改现有事件，**保持 id 和 created_at 不变**；`sequence` 加 1，`updated_at` 更新为 UTC ISO 时间。误收录时设 `status` 为 `cancelled` 并增加 sequence，ICS 会保留同 UID 的撤销事件。客户端如何处理撤销和历史缓存由其实现决定。不要仅因暂时下架/服务中断而撤销真实的历史发布。

## 一键下线与恢复

打开 **[Service on-off](https://github.com/xany7/ai-model-calendar/actions/workflows/service.yml)** → **Run workflow**。默认 `offline`，运行后自动保存关闭状态并部署下线页：

- `calendar.ics` 从发布目录中移除，部署生效后返回 404。
- 每日来源抓取被跳过；每日工作流本身仍可能运行以保持关闭状态。
- 原始数据与审核历史留在仓库，方便恢复。它们是公开数据，不会因为下线而从 Git 历史中删除。

要恢复：同一入口选择 `online` 并运行，原订阅 URL 恢复。若还需停掉所有定时执行，在 Daily update & deploy 的菜单中选择 **Disable workflow**；恢复时先 **Enable workflow**。

仅移除个人订阅：在 Apple/Google/Outlook 中删除这个已订阅日历即可。**下线源无法远程清除客户端已缓存事件**；订阅者应自行取消订阅。CDN 缓存和正在进行的工作流可能使关闭延迟数分钟。

彻底停止托管也可在仓库 Settings → Pages 中 Unpublish site。恢复时需重新启用 Pages；通常没有必要删除仓库。

## 状态、费用与稳定性边界

- [网站来源状态](https://xany7.github.io/ai-model-calendar/#status) 和 [health.json](https://xany7.github.io/ai-model-calendar/health.json) 显示最近检查、解析结果和连续异常次数。超过 48 小时未检查，网页在客户端自动显示逾期。
- 某厂商全部官方入口失败时，先部署健康报告和保留的日历，再将工作流标记失败。可在 GitHub 通知设置中启用 Actions 失败通知。系统没有主动发送邮件/聊天消息，也没有偷偷创建提醒任务。
- 公共仓库使用 GitHub Free 可用的 Pages 与标准 GitHub-hosted Actions；当前用量很低，无常驻服务器、域名费或模型 API 费。平台政策和配额可能变化。
- 地址在账号、仓库名和 Pages 配置不变时保持固定；不要重命名账号或仓库。GitHub/CDN、网络环境和客户端可达性仍会影响服务，没有 SLA 或永久可用保证。
- GitHub 定时执行可能排队、延迟甚至漏跑。成功的每日健康记录会产生仓库活动；如果长期未活动，GitHub 可能在 60 天后关闭公共仓库定时工作流，届时需重新启用。停服后尤其应留意。

## 本地维护

Python 3.12+：

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt pytest==9.1.1
.venv/bin/python -m pytest -q
.venv/bin/python calendar_service.py collect
.venv/bin/python calendar_service.py build
.venv/bin/python -m http.server 8000 --directory site
```

本地 GitHub 入口可能触发匿名限流，可通过环境变量 `GH_TOKEN` 提供令牌；Actions 使用短期 `GITHUB_TOKEN`，不需要另存个人凭据。不要把令牌写进文件或提交。`data/sources.json` 可增减入口；`data/service.json` 可修改窗口和自动批准开关。依赖固定版本；定期更新并运行测试。

ICS 使用 RFC 5545 库生成：UTF-8、CRLF、75 字节折行、稳定 UID、全天 DTSTART 和次日排他 DTEND、UTC DTSTAMP/LAST-MODIFIED、SEQUENCE、URL、DESCRIPTION。测试覆盖中文转义、日期跨日、去重、保守批准、撤销及停服后文件移除。

## 规范与平台依据

- [RFC 5545 / iCalendar](https://www.rfc-editor.org/rfc/rfc5545)
- [GitHub Pages 自定义工作流](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions schedule 限制](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions 计费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
