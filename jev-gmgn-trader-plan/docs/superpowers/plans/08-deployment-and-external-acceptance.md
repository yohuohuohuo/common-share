# P08 部署与外部验收 Implementation Plan

> **For agentic workers:** 本次只执行P08。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 完成可部署交付、安全恢复手册、早期probe的正式外部证据与单独授权的实盘验收入口。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第13—14节；15.1、15.3—15.5的运维口径。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

Web无供应商secret；env默认false；恢复不重发；只读probe不写；缺凭证的外部状态明确NOT_RUN。

## 输入、范围与交付边界

**输入：** P07通过的全套软件；P02/P03/P04只读probe；版本化配置和schema；所有owner提供的部署输入。

**输出：** Web/Worker容器、操作/备份手册；只读与实盘验收工具；交付报告按软件/账号/链实盘分层。

**不做：** 不代填密钥/资金/滑点，不因文档执行而开启实盘，不将软件完成当三链实盘通过。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及`docs/execution/P07-handoff.md`和其中指定的已存在接口。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

```bash
pnpm lint
pnpm typecheck
pnpm test
pnpm test:integration
pnpm test:e2e
pnpm build
```
前置P07未通过本地验收时，不开始本阶段；外部账号NOT_RUN不是本地代码阶段的自动阻塞。

## P08.01：部署、操作手册和安全交接

**来源编号：** T21（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P07.02。**覆盖：** R01、R10、R12。

**文件：** `Dockerfile.web`、`Dockerfile.worker`、`compose.yml`、`.env.example`、`.gitignore`；`docs/operations/{deployment,configuration,incident-response,backup-restore}.md`；`scripts/check-deployment.ts`及测试。

**接口：** `checkDeployment():Promise<ReadinessReport>`只读；输出缺失字段名、网络能力、db连通、worker状态，不回显secret value。

- [ ] 写部署配置安全检查：env示例false、无真实key、Web service不注入GMGN/Jev密钥、数据库不公开暴露；compose只允许worker网络出口使用凭证。
- [ ] 生成可运行容器构建，非root进程、持久化数据库、健康检查、单worker replicas；应用启动不自动run生产迁移，提供显式迁移步骤和可回滚发布说明。
- [ ] `.env.example`只填写非敏感默认值，密钥空值是部署输入而非可运行占位凭证；实盘配置未就绪通过UI列出，不用假私钥自动替代。Node/pnpm版本和依赖patch均来自P01.01已验证lock。
- [ ] 运维说明包括IPv4出口和白名单、时钟、DB迁移/seed、登录初始化、API只读check、数据库业务配置、env重启生效、即时暂停、unknown订单处理、密钥轮换、日志轮转、DB备份及恢复。
- [ ] 在临时目录执行备份恢复演练，确认恢复后旧pending/unknown订单仍先对账，禁重复POST；环境开关恢复默认false，不将备份里的paused=false当实盘授权。
- [ ] 完成容器构建与smoke tests，提交`ops: package safe deployment and recovery runbooks`。

**验收：** 有凭证的所有者能按手册部署，不必自己补交易引擎和页面；没有凭证时明确哪些功能未就绪。


### 运维说明增补（U01/U04/U05/U06）

- [ ] 手册写明提示词/执行语义同步变更和版本迁移、历史双时间cutoff、生命周期只追加、成本估算/实账与跨期分摊。备份必须包含事件、attempt、成本、配置和未决订单，恢复后交易默认关闭。
- [ ] 将P02/P03/P04已创建的只读probe工具纳入部署检查，继续使用唯一provider出口；不复制出第二个客户端绕Plus。自动更新、自动Gas充值和交易策略fallback均不加入。

## P08.02：真实账号只读验收、实盘验收入口与交付报告

**来源编号：** T22（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P08.01。**覆盖：** R01–R12的外部验证。

**文件：** 复用`scripts/probe-gmgn.ts`、`scripts/probe-jev.ts`；新增`scripts/live-acceptance.ts`；`docs/testing/provider-verification.md`、`live-acceptance.md`、`delivery-report.md`。

**接口：** `probe-gmgn --chain <允许链>`只读并经Plus调度；`live-acceptance`仅允许明确参数、显式交互确认、envtrue、绑定账户、预定义档位及所有正常gate，不能自由POST任意路由。

- [ ] 未提供凭证时脚本退出`CREDENTIALS_REQUIRED`且不发送请求；probe不可能调用Swap。先为这两个约束写测试并确认FAIL，再实现。
- [ ] 对实际Plus账号逐链验证网络绑定、账户、各价格／金额字段、持仓分页、quote鉴权、费用单位、KOL、common关注计数和限频header；脱敏样例保存source_version、timestamp和test_result，不保存完整鉴权query或headers。
- [ ] 单独验证Jev版本、合法Choice schema和真实usage，记录上下文打包估算误差；不将实际模型一直WAIT误判为集成失败。
- [ ] 只有所有者显式开启实盘并确认验收动作后执行最小档位流程。自动交易保持Jev选择；确定性执行验收可使用manual_acceptance标记，但不得伪造成模型决策，且所有权重、金额、gate、账本规则一致。
- [ ] 每链记录买入、部分卖出、清仓的实际订单ID／hash、输入输出、费用、成本、重启后查询和余额核对。四档组合在P07.02已覆盖，不要求把每档在实盘各买一次。未知或不能卖出如实记录，不为了验收自动放宽滑点。
- [ ] 更新交付报告：实现状态、自动测试实际命令与结果、只读账号证据、每链实盘状态、已知外部限制、配置说明、部署步骤；凭证未给或某链路由不可用时标`NOT_RUN`或`BLOCKED`，不能全绿。
- [ ] 提交`docs: record provider verification and delivery evidence`；最终只交付脱敏报告，真实密钥永不提交Git。

**验收：** 第一版完整交易能力有明确证据链；是否全部实盘通过与代码是否完成分别报告。


### 外部验收与软件状态分开（U01—U06）

- [ ] P02—P04已能运行的只读probe不在本阶段重写；更新脱敏证据、来源commit及各链实际结论。凭证缺失标NOT_RUN，权限/路由不足标BLOCKED，不阻塞可完成的本地软件验收。
- [ ] P08的软件部署/恢复工具通过可以标softwareVerified=true；`providerReadOnly`及`liveAcceptance`按每链分别NOT_RUN/BLOCKED/PASS/FAIL。不得用VERIFIED软件状态代称实盘通过。
- [ ] 用户未单独授权运行真实交易时，只交付入口、测试和说明；不询问聊天里的密钥，不为凑验收改变Jev WAIT、金额档位或滑点。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm exec vitest run scripts/check-deployment.test.ts scripts/probe-gmgn.test.ts scripts/probe-jev.test.ts scripts/live-acceptance.test.ts
pnpm build
docker compose -f compose.yml config --quiet
docker compose -f compose.yml build
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P08-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
