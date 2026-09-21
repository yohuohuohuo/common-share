# 参考项目源码评审与采用边界（R2）

记录日期：2026-09-21。用途：落实用户已同意的参考项目建议；这是固定版本的静态源码观察，不是两个项目的当前收益证明、完整安全审计或本项目实盘验收。

## 1. 固定版本

| 项目 | 评审commit | 项目性质 |
|---|---|---|
| jarrodwatts/jev-trader | `b587759e459ea049590102e54a0b07800864cdc3` | Monad/Kuru单市场限价挂单实验 |
| irfndi/prism-liquidity-agent | `22c67bdbe30bab608226832256a5013ad826b707` | Solana/Meteora流动性管理；Jev为辅助判断 |

以下链接固定commit，不自动跟随main。最新main之后的改动不在本评审结论中；GMGN路由、价格、Plus额度和Jev API规则仍以[官方核验记录](2026-09-21-api-evidence.md)及接入实测为准。

## 2. 证据索引

| ID | 固定源码 | 已观察内容及边界 |
|---|---|---|
| J01 | [model.ts](https://github.com/jarrodwatts/jev-trader/blob/b587759e459ea049590102e54a0b07800864cdc3/src/model.ts) | 独立TradeState/Model接口、概率/耗时/usage；模型指令包含IOC/cross-spread和特定信号偏好，不作为本项目提示词模板照搬 |
| J02 | [trader.ts](https://github.com/jarrodwatts/jev-trader/blob/b587759e459ea049590102e54a0b07800864cdc3/src/trader.ts) | busy、异步确认、动作可能被改成另一方向；历史不足部分数值填0；计入jevUsd但pnlUsd公式未扣这项成本 |
| J03 | [market.ts](https://github.com/jarrodwatts/jev-trader/blob/b587759e459ea049590102e54a0b07800864cdc3/src/market.ts) | post-only批量撤挂单，与J01中的执行描述存在差异；不是GMGN ExactIn Swap实现 |
| J04 | [server.ts](https://github.com/jarrodwatts/jev-trader/blob/b587759e459ea049590102e54a0b07800864cdc3/src/server.ts) | snapshot/history/SSE，分开发送block、quote和fill；公开CORS不适用于管理写接口 |
| J05 | [README.md](https://github.com/jarrodwatts/jev-trader/blob/b587759e459ea049590102e54a0b07800864cdc3/README.md) | 默认mock及无私钥模拟成交说明；展示数据不能当作已验证Jev实盘收益 |
| P01 | [jev-service.ts](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/engine/jev-service.ts) | 旁路Jev判断、数据来源/已知标记、错误分类；失败继续规则结果与本项目不一致 |
| P02 | [jev-gate.ts](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/engine/jev-gate.ts) | 统一发送节奏和进程级429冷却；其中固定两秒节奏不是供应商官方额度 |
| P03 | [jev-gate.test.ts](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/bench/jev-gate.test.ts) | 虚拟时钟、请求计数，验证冷却期间没有真实请求；可借鉴测试方法 |
| P04 | [memory-service.ts](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/engine/memory-service.ts) | 记录结果、检索历史上下文；不能据此声称模型权重自动训练或持续盈利 |
| P05 | [reconcile-positions.test.ts](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/bench/reconcile-positions.test.ts) | RPC失败保留持仓、变化后同步等回归；本项目扩展为GMGN分页/掉榜/未知订单测试 |
| P06 | [audit-service.ts](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/engine/audit-service.ts) | 动作、检查、是否执行、模式、签名和错误分离；借鉴可追踪性，不复制投资风控规则 |
| P07 | [profitability-review-2026-09-05.md](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/docs/profitability-review-2026-09-05.md) | 项目自己的历史复盘指出持仓管理被入场筛选跳过、动作未进入执行、账本与钱包收益口径等问题；这是作者记录，不是本次复现实测 |

## 3. 采用与不采用

| 建议 | 本项目处理 | 需求编号 |
|---|---|---|
| 清晰的模型state及模型适配边界 | 继续统一快照/紧凑摘要，缺失保留unknown，不引入策略权重 | U01、U04 |
| 提示词和执行描述一致 | 共用ExecutionSemantics并对真实序列化请求做变异测试 | U01 |
| 模型选择与实际执行分离 | 原始选择不可变，失败不改SELL/降档/规则fallback | U02 |
| 冷却与持仓故障测试 | 两个供应商独立状态，GMGN仍遵守Plus共享预算 | U03 |
| 记忆和结果检索 | 同账户/资产、截至当轮已知的本地历史；不引入向量库 | U04 |
| 决策、提交与成交事件 | 数据库不可变事件、稳定游标、分别统计 | U05 |
| 成本、耗时可观察 | 各阶段记录；交易/钱包/运行成本调整结果分别展示 | U06 |
| SSE | 后续增强，第一版DB+SWR足够 | D01 |

不采用：Monad逐块高频节奏、Kuru特定编码/固定Gas、LP区间/无常损失策略、规则入场筛选、confidence投资门槛、程序翻转动作、Jev故障时启用规则交易、用当前信息重写历史、用模拟表现作收益承诺。测试mock仍可使用，但不作为生产备用模型或投资对照组。

## 4. 许可与复用方式

两个固定版本的[jev-trader LICENSE](https://github.com/jarrodwatts/jev-trader/blob/b587759e459ea049590102e54a0b07800864cdc3/LICENSE)与[Prism LICENSE](https://github.com/irfndi/prism-liquidity-agent/blob/22c67bdbe30bab608226832256a5013ad826b707/LICENSE)声明MIT。当前修订只是整理工程启示和编写本项目计划，不导入第三方实现。今后直接复制实质代码时，将原版权/许可及来源commit记入THIRD_PARTY_NOTICES，并逐段审阅依赖与执行行为，不能因许可证宽松就整仓接入。

## 5. 文档关联及验证范围

[主设计第15节](../superpowers/specs/2026-09-21-jev-gmgn-trader-design.md#15-r2参考项目评审的工程增补)明确新增要求；[专项实施清单](../superpowers/plans/2026-09-21-reference-review-implementation.md)提供文件/接口/失败测试/验收，主计划T01—T22保持稳定编号。

已知限制：未运行参考仓库、未验证其部署、未调用私人API、未复现实盘盈亏；引用使用固定commit以便后续独立核查。
