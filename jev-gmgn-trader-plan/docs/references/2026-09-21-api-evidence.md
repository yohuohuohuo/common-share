# API 核验记录与接入验证清单

核验日期：2026-09-21。适用项目：Jev + GMGN 多链交易实验 V0.1。

本文区分“公开文档／源码中已找到”和“使用项目账号实际验证”。本轮未使用 API Key，没有请求真实报价、没有验证钱包权限，也没有发起交易。下列地址是官方文档或官方公开仓库；`main` 分支内容可能更新，实施任务 T01 必须固定实际采用的上游 commit，并保留相关文档文件的 SHA-256。不要把本记录当作接口 SLA、Plus 全部商业条款或账号实测报告。

## 1. 来源索引

| ID | 官方资料 | 地址 |
|---|---|---|
| S01 | GMGN Agent API 总览 | `https://docs.gmgn.ai/cn/gmgn-agent-api` |
| S02 | GMGN Market | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/skills/gmgn-market/SKILL.md` |
| S03 | GMGN Token | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/skills/gmgn-token/SKILL.md` |
| S04 | GMGN Portfolio | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/skills/gmgn-portfolio/SKILL.md` |
| S05 | GMGN Track | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/skills/gmgn-track/SKILL.md` |
| S06 | GMGN Swap | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/skills/gmgn-swap/SKILL.md` |
| S07 | 官方 HTTP 客户端实现 | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/src/client/OpenApiClient.ts` |
| S08 | 官方签名实现 | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/src/client/signer.ts` |
| S09 | 官方客户端配置 | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/src/config.ts` |
| S10 | GMGN Callout OpenAPI | `https://docs.gmgn.ai/cn/gmgn-callout-openapi` |
| S11 | Jev 模型与上下文限制 | `https://docs.typesafe.ai/models` |
| S12 | Jev Choice | `https://docs.typesafe.ai/primitives/choice` |
| S13 | TypeSafe HTTP API | `https://docs.typesafe.ai/api` |
| S14 | TypeSafe JavaScript SDK | `https://docs.typesafe.ai/sdk/javascript` |
| S15 | Node.js 支持周期 | `https://nodejs.org/en/about/previous-releases` |
| S16 | Next.js 安装与运行要求 | `https://nextjs.org/docs/app/getting-started/installation` |
| S17 | GMGN Portfolio CLI 参数实现 | `https://raw.githubusercontent.com/GMGNAI/gmgn-skills/main/src/commands/portfolio.ts` |

## 2. 已找到的接口、请求权重与鉴权

Base URL 根据官方客户端配置为 `https://openapi.gmgn.ai`。[S09]

以下为本项目实际需要的路由集合。表中的鉴权以所读官方客户端方法和更细粒度的接口文档为依据；实施时用项目账号验证，不依赖总览的简化分类。[S02–S08]

| 能力 | 方法与路径 | 权重 | 鉴权模式 |
|---|---|---:|---|
| 热榜 | GET `/v1/market/rank` | 3 | API Key + 时间戳／请求 ID |
| 普通 K 线 | GET `/v1/market/token_kline` | 2 | 同上 |
| 基本信息／价格 | GET `/v1/token/info` | 1 | 同上 |
| 安全数据 | GET `/v1/token/security` | 1 | 同上 |
| 池信息 | GET `/v1/token/pool_info` | 1 | 同上 |
| 持有人 | GET `/v1/market/token_top_holders` | 5 | 同上 |
| 交易者 | GET `/v1/market/token_top_traders` | 5 | 同上 |
| KOL 交易流 | GET `/v1/user/kol` | 1 | 同上 |
| 钱包统计／关注度 | GET `/v1/user/wallet_stats` | 3 | 同上 |
| API Key 关联账户 | GET `/v1/user/info` | 2 | 同上 |
| 持仓 | GET `/v1/user/wallet_holdings` | 2 | **另需请求签名** |
| 单币余额 | GET `/v1/user/wallet_token_balance` | 2 | API Key + 时间戳／请求 ID |
| 钱包活动 | GET `/v1/user/wallet_activity` | 3 | 同上 |
| Gas 信息 | GET `/v1/trade/gas_price` | 1 | 同上 |
| 报价 | GET `/v1/trade/quote` | 10 | 当前客户端是非签名查询；文档存在冲突，须实测 |
| 提交 Swap | POST `/v1/trade/swap` | 10 | **另需请求签名** |
| 查询订单 | GET `/v1/trade/query_order` | 5 | **另需请求签名** |

可选的市场 KOL 信号接口权重 1，不作为第一版必需采集任务。第一版不使用 multi-swap、条件单、自动止盈止损、发币或自动喊单接口。

### Plus 限频

标准接口文档列出的 Plus 为漏桶 `rate=20`、`capacity=20`，请求按上表权重消耗，不是任意接口每秒都能调用 20 次。持续吞吐约为 `20 / 请求权重`，短时突发也受桶容量限制。1 秒 K 线单独标记为 Pro-only，第一版不依赖它。[S02–S06]

429 冷却依据响应头 `X-RateLimit-Reset` 和响应体 `reset_at`；官方提醒冷却期内反复请求可能延长禁用时间。[S02–S06] 本项目所有三链、后台采集、页面刷新请求共享同一个按凭证标识归集的调度器。实际服务若按账号或关联密钥合并限额，也必须合并该标识；不能通过轮换 Key 绕开限制。

Plus 的价格、按月调用总额、数据授权及 Callout 权限没有在这些速率表中一并承诺。管理页面记录套餐与实测响应，不把漏桶速率换算成已购买的包月调用量。

### 与业务有关的关键定义

- `wallet_stats.common.follow_count` 是 GMGN 用户追踪数；`remark_count` 是备注用户数；`followers_count` 是关联 X 的粉丝数。`common` 可能缺失，按未知处理。支持钱包数组不等于任意批量规模都受支持，预算按单钱包请求估算。[S04]
- Token／Market／Swap 文档均列出 `robinhood`、`bsc`、`sol`；各接口字段和路由是否对项目账号可用仍需验证。[S02–S06]
- `token info` 提供美元价格，持仓提供美元估值，报价提供原始输入／预期输出／最小输出数量。原生币地址表示及精度由链能力记录确认，不从代币简称推导。[S03、S04、S06]
- Jev 当前文档版本 `jev-1.13.0`；一个 Choice 至多 255 个选项；每请求 64k tokens，并有 `state + 单个最长问题 <= 32k` 的更严格约束。本项目顺序调用两次，每次都要独立满足约束。[S11–S13]
- Callout 是单独的合作伙伴 API，使用另行配置的 AK/SK。购买 Agent API Plus 不被本计划视为自动取得这项权限；第一版保留 `not_configured` 状态，不依赖它才能完成交易。[S10]

## 3. 已发现的文档不一致及处理规则

| 编号 | 不一致／未证实内容 | 明确处理 |
|---|---|---|
| V01 | Market 文档开头与 K 线响应字段表对 `volume`、`amount` 的单位解释相反 | 保存原始值；未核实前，归一化 USD／token 成交量字段为 `unknown_unit`，不得选一个含义猜测。用官方确认和响应样例固定映射。其他行情字段可继续使用。 |
| V02 | 总览把查询类简化为只需 API Key，但持仓方法明确签名 | 按签名持仓设计；关闭实盘只禁写交易，不禁签名读取。 |
| V03 | Swap 文档一处称 quote 需要签名，客户端 `quoteOrder` 使用非签名请求 | T01 做只读鉴权验证；按每条链能力保存结果，禁止遇到失败无限切换鉴权重试。 |
| V04 | 订单字段表列 pending／processed／confirmed，报告说明又使用 `state=30`／`successful` | 做版本化状态映射；未知状态进入 `RECONCILING`，没有可验证成交报告不得伪造填单。 |
| V05 | `client_id` 在鉴权中用于请求标识和重放限制 | **不当作 Swap 业务幂等键**；尚未证实服务支持由客户端 ID 查询丢失的订单。超时不自动再次 POST。 |
| V06 | 热榜 CLI 默认安全过滤可能生效；直接 REST 的默认行为需要确认 | 程序不添加策略过滤；记录请求参数和上游过滤可见性，不能声称返回是全市场无过滤榜单。 |
| V07 | Solana／BSC 货币地址列有示例，Robinhood 的货币表示和费用字段不完整 | 配置向导验证绑定网络、原生币 API 表示、decimals 和 quote；完成前该链标记未就绪，不能悄悄当作另一条 EVM 链。 |
| V08 | KOL 流只提供有限条最新记录；批量规模和覆盖不能推为无限 | 做去重和重叠观测，保存数据窗口、截断和缺口；不能从缺少卖出推出从未卖出。 |
| V09 | 上游源码 main 会更新，未取得固定 commit | T01 使用 Git 获取实际 commit 和文件哈希后更新引用；本轮没有伪造上游 SHA。 |

## 4. T01 的只读验证矩阵

三条链逐一执行，不通过多开 API Key 绕过限流，不自动生成或展示真实密钥。

| 检查 | 所需证据 | 失败影响 |
|---|---|---|
| IPv4、时钟、账户 Plus 权限 | 出站环境、服务器时间、脱敏响应状态与限频头 | 网络／鉴权未就绪，禁止交易 |
| 钱包绑定、结算资产和精度 | 关联账户与余额样例 | 对应链禁止创建交易意图 |
| 热榜、价格、普通 K 线 | 响应外形、时间和金额单位样例 | 相应字段 unavailable；关键支付资产价格未知时禁止金额换算 |
| 持仓分页、空持仓、签名 | 完整分页游标与签名读成功 | 不允许把第一页当完整账户；账户未对账时禁止发新交易 |
| KOL 与 wallet_stats | 有／无 common、零值、标签和数据窗口样例 | 缺失为 unknown；不是选币否决条件 |
| 所选四档 quote | 固定输入数量的预期／最小输出和鉴权证据 | 无可执行报价的档位不可提交 |
| 订单查询外形 | 官方样例或后续获授权实单查询证据 | 本地测试用明确标记的 synthetic fixture，不标记实盘通过 |

只读验证不要求购买任何测试代币。真实买入／卖出是最终验收的独立操作，必须显式开启 `TRADING_ENABLED=true` 并由项目所有者配置账户与资金。
