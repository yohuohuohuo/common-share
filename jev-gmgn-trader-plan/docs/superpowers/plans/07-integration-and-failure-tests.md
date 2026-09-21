# P07 全流程集成与故障验收 Implementation Plan

> **For agentic workers:** 本次只执行P07。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 注册全套handler并通过三链全流程、故障矩阵、Plus负载和需求覆盖门禁。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第9—10、13—14及15.6；其余按失败涉及内容阅读。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

双Worker与在途重启；三链一共享限额；UI刷新不影响配额；多fill/重复事件计数；模型错误不阻止对账。

## 输入、范围与交付边界

**输入：** P01—P06接口与阶段交接；P02运行骨架和P03—P05handler；P06内部API和页面。

**输出：** 完整startWorker接线；全流程/故障/负载测试；requirement→phase→test→result矩阵；可重建状态证据。

**不做：** 不重新设计Worker/类型/schema，不开启实盘，不用synthetic收益证明盈利，不做SSE。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及`docs/execution/P06-handoff.md`和其中指定的已存在接口。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

```bash
pnpm typecheck
pnpm test
```
前置P06未通过本地验收时，不开始本阶段；外部账号NOT_RUN不是本地代码阶段的自动阻塞。

## P07.01：Worker生命周期、任务恢复和统一调度接线

**来源编号：** T19（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P02.03及P03—P06的阶段验收。**覆盖：** R01、R02、R12，Review Focus 3/4。

**文件（修改P02已有运行骨架，不重建）：** `apps/worker/src/{main,bootstrap,health}.ts`、`scheduler/dispatch.ts`；`packages/db/src/{jobs,worker}-repository.ts`；`tests/integration/worker-lifecycle.test.ts`。

**接口：** `startWorker({db,transport,clock,env,handlers}):Promise<WorkerHandle>`；`WorkerHandle.stop():Promise<void>`；`acquireActiveWorker(db):Promise<WorkerLease|null>`；lease含epoch与assertActive方法。

- [ ] 写双worker竞争测试：只有一个获得active advisory锁，另一个standby；Web刷新的jobs不会自己执行网络请求。
- [ ] 故障测试：持有DISPATCHING意图时kill active worker，接管实例恢复unknown且不再POST；持久化cooldown重启后仍有效。
- [ ] 在P02骨架中注册P03—P05真实handler并完成启动顺序：读取env→DB连接→迁移状态检查→active锁→读取cooldown和未决单→恢复对账→开始采集调度→按配置触发决策。退出停止新任务，等待可界定的在途请求，未知保持unknown。
- [ ] 复用并复测P02的任务原子claim、租约、resource去重和not_before；真实submit job不可通用retry。工作heartbeat与有效env标志写worker_control，页面只读；DB断开不继续新发送。
- [ ] 用户修改decisionInterval后由新config调整下次轮；旧轮仍旧快照，计时器不叠加。managed持仓和未决订单优先，不随enabledChains关闭而停止必要查询。
- [ ] 测试全部collector进入同一Plus队列，后台预算和snapshot覆盖可见；提交`feat: run durable single-executor trading workers`。

**验收：** 关闭浏览器交易循环仍运行；热重启不会多开循环或重复下单。

## P07.02：综合故障测试、Plus负载回放与需求追踪

**来源编号：** T20（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P07.01。**覆盖：** R01–R12，所有Review Focus。

**文件：** `tests/integration/full-cycle.test.ts`、`plus-load.test.ts`、`failure-matrix.test.ts`；`tests/helpers/fake-gmgn-server.ts`、`fake-jev-server.ts`；`docs/testing/acceptance-matrix.md`。

**接口：** 本地fake服务接受与生产同样的route schema，但只绑定127.0.0.1，fake场景由测试控制：成功、429、超时已成交、未知状态、部分字段缺失、分页遗漏、余额突变。

- [ ] 先建可失败的完整流程测试：三链synthetic行情→A选asset→B选USD20→fake成交→持仓更新→下一轮SELL50%→fake成交→下一轮100%清仓。断言每轮最多1个POST，剩余数量和成本正确。
- [ ] 单独测试envfalse：同样两步模型选择都完成，但POST总数0、账本未变、状态SUPPRESSED。
- [ ] 重现Plus表的60候选＋9额外持仓，以虚拟时间推进10分钟并记录每次发出时间／weight；断言任意区间dispatch weight≤`20+16×秒差`，背景≤其桶容量+10×秒差，P0不被背景长期饿死；100个页面刷新去重。
- [ ] 故障矩阵至少包含：429跨链冷却、签名排队超时、P01.01映射冲突、所有Jev WAIT、Jev非法action、超上下文复选、quote过期、config切版、余额突变、暂停在途、swap响应丢失、DB写失败、重复fill、deposit、掉榜持仓、费用未知、未知成本。
- [ ] 为所有Rxx建立`requirement → task → test → result`矩阵；自动测试只填synthetic，不写实盘通过。
- [ ] 运行完整门禁：

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm test:integration
pnpm test:e2e
pnpm build
```

- [ ] 修复失败后逐项重跑，不通过就不以“后面再修”完成任务；提交`test: verify trading lifecycle failure recovery and Plus budgets`。

**验收：** 能证明工程正确性，不将synthetic收益或测试通过宣传为盈利能力。


### 本阶段内联增补：R2专项全部归入综合验收（U01—U06）

- [ ] 在`docs/testing/acceptance-matrix.md`将R01—R12、U01—U06逐一关联Pxx.yy、测试文件、代码commit和实际结果；D01=SSE为DEFERRED。旧T/U只作来源编号，不再派发执行。
- [ ] 故障矩阵新增：真实待发送字节变异、旧quote刷新未重新B、BUY受阻可SELL但不替代、Jev429与GMGN429隔离、分页失败managed保留、历史recordedAt晚到排除、一个订单多fill、同成本估算转实账、重复事件/回执不重复计费。
- [ ] 补`tests/integration/lifecycle-counts.test.ts`：1轮A/B多个调用、1意图、1网络尝试、1订单确认、2个fill且重复返回，结果必须1/1/1/1/2；只有SUBMISSION_UNKNOWN时acceptedOrders=0。统计按运行模式隔离，手工验收不冒充模型实盘。
- [ ] 恢复测试验证数据库event序号、model response hash、成本sourceKey及历史cutoff不丢失；冷却发生时实际网络次数不变。
- [ ] 产品门禁测试不因文档校验已通过就跳过；所有fixture/synthetic结果不作为策略盈利或三链实盘通过证据。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm test:integration
pnpm test:e2e
pnpm build
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P07-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
