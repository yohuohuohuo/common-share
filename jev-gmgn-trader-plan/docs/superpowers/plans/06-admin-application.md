# P06 管理后台 Implementation Plan

> **For agentic workers:** 本次只执行P06。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 交付使用真实DB/内部API的安全管理后台，展示模型、执行、时间线与完整成本覆盖。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第12节与15.3—15.5的展示要求。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

鉴权和CSRF；Web不能越过env；刷新不上游；原决定和实际结果分开；unknown/partial与真实0不同。

## 输入、范围与交付边界

**输入：** P01配置/会话schema；P03市场和历史DTO；P04原始calls；P05订单/成本/事件；P02Worker状态。

**输出：** requireAdmin/verifyMutationOrigin及内部API；所有管理页面；生命周期统计、成本登记、SWR时间线、配置冲突处理。

**不做：** 不复制供应商调用到Web、不增加任意手工买卖入口、不做SSE/公开注册/对照组。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及`docs/execution/P05-handoff.md`和其中指定的已存在接口。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

```bash
pnpm typecheck
pnpm exec vitest run tests/integration/ledger.test.ts tests/integration/config.test.ts tests/integration/lifecycle-storage.test.ts
```
前置P05未通过本地验收时，不开始本阶段；外部账号NOT_RUN不是本地代码阶段的自动阻塞。

## P06.01：管理员鉴权与内部API

**来源编号：** T17（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.03、P01.04、P03.03、P04.03、P05.02、P05.03。**覆盖：** R01、R09、R10。

**文件：** `apps/web/src/server/{auth,csrf,queries}.ts`；`apps/web/src/app/api/`对应设计第12节路由；`packages/db/src/sessions-repository.ts`；`scripts/hash-admin-password.ts`；`tests/integration/admin-api.test.ts`。

**接口：** `requireAdmin(request):Promise<AdminSession>`；`verifyMutationOrigin(request,appOrigin):void`；配置更新API接收`{expectedVersion,patch}`；刷新请求只接受已登记jobType/resourceId，返回202 jobId。

- [ ] 写未登录401、错误Origin403、过期session401、合法配置修改审计和过期version409测试。
- [ ] 运行`pnpm exec vitest run tests/integration/admin-api.test.ts`确认FAIL。
- [ ] 实现单管理员password-hash校验、随机256bit token只存hash、生产Secure+HttpOnly+SameSite cookie、8小时session有效期、登录失败限频和注销撤销。密码初始化脚本从交互stdin读入、不回显，不接受命令行明文密码。
- [ ] 所有GET只读DB；POST写config/job/runtime而非直接调用GMGN。任何响应不包含GMGN/Jev密钥、数据库连接、签名header、服务端环境全量。Web不导入gmgn signing。
- [ ] 只读system返回**worker实际报告的**envEnabled和heartbeat；不能用Web进程的环境变量推断worker实盘状态。暂停与P05.01临界区同步，恢复不能改TRADING_ENABLED。
- [ ] Origin严格匹配APP_ORIGIN；URL/任务参数allowlist、请求大小限制；接口中的decimal保持string。测试通过后提交`feat: add authenticated admin APIs with server-side trade boundaries`。

**验收：** 管理页面能控制配置和暂停，但不能越过env或直接构造任意交易。

### 本阶段内联增补：持久化生命周期时间线与指标

本节先在P06.01完成查询/聚合/API，组件与E2E在P06.02完成；不要求先写页面才通过API子任务。


**文件：** 复用P01生命周期仓储和P04/P05事件生产；本阶段新建`packages/domain/src/lifecycle-summary.ts`及测试；新建`apps/web/src/app/api/decisions/[id]/timeline/route.ts`、`apps/web/src/components/DecisionTimeline.tsx`及`tests/e2e/decision-timeline.spec.ts`。

**接口：** `appendLifecycle(db,event):Promise<{eventId:string;sequence:string}>`；`readTimeline(db,{roundId,afterSequence,limit}):Promise<TimelinePage>`；`summarizeLifecycle(events):LifecycleSummary`。TimelinePage含events、nextSequence，limit1..100。事件字段至少eventId、eventKey、roundId、intentId/orderId可空、type、occurredAtMs、recordedAtMs、sequence、payload；payload用事件类型判别的Zod union验证，不包含secret。

生命周期类型至少包含SNAPSHOT_SAVED、MODEL_A_COMPLETED、QUOTES_READY、MODEL_B_COMPLETED、ROUND_COMPLETED、INTENT_CREATED、EXECUTION_BLOCKED、SUBMIT_ATTEMPTED、SUBMISSION_UNKNOWN、ORDER_ACCEPTED、ORDER_CONFIRMED、FILL_RECORDED、LEDGER_POSTED、EXECUTION_FAILED。A/B错误用具体error事件，不能产生有效ROUND_COMPLETED；WAIT/ABSTAIN可正常完成。

- [ ] 复跑P01数据库集成测试并验证同event_key两次追加只产生一行和一个sequence；同key不同payload报冲突。序号在同事务按聚合递增；关键状态更新与事件写入要么都提交要么都回滚。
- [ ] 统计核心测试：创建1轮、A/B各一次、1意图、1发送尝试、1已接受订单、同订单2个真实fill，并重复输入相同事件；预期completedRounds=1、tradeIntents=1、submitAttempts=1、acceptedOrders=1、confirmedOrders=1、fills=2。
- [ ] `summarizeLifecycle`按稳定ID去重，而不是按数组长度：

```typescript
export interface SummaryEvent {
  eventId:string; roundId:string; intentId:string|null;
  orderId:string|null; fillId:string|null;
  type:'ROUND_COMPLETED'|'INTENT_CREATED'|'SUBMIT_ATTEMPTED'|
    'ORDER_ACCEPTED'|'ORDER_CONFIRMED'|'FILL_RECORDED';
}
export function summarizeLifecycle(rows:ReadonlyArray<SummaryEvent>) {
  const events=[...new Map(rows.map(e=>[e.eventId,e])).values()];
  const count=(type:SummaryEvent['type'],key:keyof SummaryEvent)=>
    new Set(events.filter(e=>e.type===type && e[key]!==null).map(e=>e[key])).size;
  return {completedRounds:count('ROUND_COMPLETED','roundId'),
    tradeIntents:count('INTENT_CREATED','intentId'),
    submitAttempts:count('SUBMIT_ATTEMPTED','eventId'),
    acceptedOrders:count('ORDER_ACCEPTED','orderId'),
    confirmedOrders:count('ORDER_CONFIRMED','orderId'),
    fills:count('FILL_RECORDED','fillId')};
}
```

- [ ] 在测试中对上述函数用明确fixtures断言结果，另测只有SUBMISSION_UNKNOWN时acceptedOrders=0；服务确认补回后为1。输入冲突由仓储拒绝；时间/运行模式过滤在查询层先做，不混合paper/manual验收和自动实盘。
- [ ] 复核P04/P05已把事件事务接到全部阶段；发现缺失退回对应owner修复；unknown恢复只追加已知事实。界面并列展示原始动作与执行结果，A/B/分组数量单列；对账确认晚到时可以重建，不修改原提交事件。
- [ ] GET只读DB且requireAdmin；前端SWR首次加载及刷新使用稳定游标重查/合并eventId，loading/partial/error/unknown有不同文本。100次刷新不产生上游请求或新事件。
- [ ] E2E验证“Jev选择买入20美元，但执行被阻止”显示两种信息，WAIT不显示成交，unknown不显示失败；重启/重连后能恢复时间线；运行测试后提交`feat: expose durable decision-to-fill timelines`。

**验收：** 时间线是数据库事实视图，不是只存在浏览器内存里的实时演示；D01/SSE不参与本任务验收。
### 运行成本 API 的唯一归属（U06）

- [ ] `apps/web/src/app/api/operating-costs/route.ts`提供鉴权GET/POST：查询同期间成本覆盖、登记有来源/计费期/金额的账单与冲销关联；CAS/幂等键防重复。记录actor，不回显凭证；不能按Plus weight虚构美元价格。
- [ ] `tests/integration/operating-costs-api.test.ts`覆盖未登录401、错误Origin403、重复sourceKey同payload幂等/不同payload409、账单替代估算不重复扣、月账单查询一天无明确分摊时partial。
- [ ] 导出三类DTO：交易PNL、扣净现金流的钱包变化、扣off-wallet成本后结果；unknown与0分开，页面不重新自行算一套金额。

## P06.02：完整管理页面

**来源编号：** T18（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P06.01。**覆盖：** R01、R08–R10、R12。

**文件：** `apps/web/src/app/login/page.tsx`、`page.tsx`、`market/page.tsx`、`market/[assetId]/page.tsx`、`positions/page.tsx`、`decisions/page.tsx`、`decisions/[id]/page.tsx`、`orders/page.tsx`、`orders/[id]/page.tsx`、`settings/page.tsx`、`system/page.tsx`；`apps/web/src/components/`；`tests/e2e/admin.spec.ts`。

**接口：** SWR读取内部API；所有页统一AppShell、ChainBadge、MoneyValue、EvidenceAge、UnknownValue、StatusBadge，组件props使用领域DTO不直接吃原始GMGN回包。

- [ ] 写Playwright失败测试：关闭实盘状态明显可见、四档买入显示、配置更新下一轮生效、订单unknown能打开详情。

```typescript
import { test, expect } from '@playwright/test';
test('settings show USD tiers without enabling live trading', async ({ page }) => {
  await page.goto('/settings'); // storageState来自本地测试登录
  await expect(page.getByLabel('买入金额档位（USD）')).toHaveValue('10,20,50,100');
  await expect(page.getByText('实盘提交已禁用', {exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'强制开启实盘'})).toHaveCount(0);
});
```

- [ ] 运行`pnpm exec playwright test tests/e2e/admin.spec.ts`确认FAIL。
- [ ] 实现设计中的七类页面；只有用户需要的管理功能，不做套利看板／排行推荐。概览清楚区分env总闸、paused、链readiness；持仓显示掉榜资产；关注度显示follow/remark/X三个独立列及时间。
- [ ] 表单以USD字符串编辑，在服务端转换美分；sell百分数转bps。保存返回版本号，冲突提示刷新合并，不覆盖。系统页显示Plus额度、排队、429冷却截止和每路由累计weight。
- [ ] 决策页能展开A/B输入和实际选项、configuration hash、概率和action；不虚构长理由。订单页区分submitted、pending、unknown、confirmed和实际fee；暂停不会显示“已撤单”。
- [ ] 处理empty/loading/error/partial/stale状态，长合约地址可复制且链接chain正确。token名字只作为文本、外链只https、CSP限制，避免不可信logo代理；键盘可访问和移动端可读。
- [ ] 跑E2E、build、敏感词构建产物扫描后提交`feat: deliver the trading administration interface`。

**验收：** 非静态mock展示，页面从实际数据库及API读取、配置可真实保存。


### 本阶段内联增补：历史、时间线与成本的可见性（U02/U04/U05/U06）

- [ ] 决策详情显示P04原始动作＋P05执行结果两列；“Jev买20美元，执行被阻止”不能改文案成“模型决定不买”。历史入口显示本轮event IDs、cutoff及coverage，不查询后来状态冒充旧输入。
- [ ] 时间线首次加载与分页合并按eventId/sequence，SWR刷新仅查询DB；100次刷新上游调用数为0，不新增事件。WAIT不显示成交，unknown不显示明确失败。
- [ ] `tests/e2e/costs-and-timing.spec.ts`测试显示quote/data age、队列/请求/A/B耗时，缺失步骤显示未知/未发生，不显示0ms成功；运行成本未知时结果partial，Gas不扣两次，估算与实账状态不同。
- [ ] P01/P02/P04/P05产物作为实际输入，禁止临时硬编码演示金额。SSE不做，不复制公开CORS示例server。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm exec vitest run tests/integration/admin-api.test.ts tests/integration/operating-costs-api.test.ts packages/domain/src/lifecycle-summary.test.ts
pnpm exec playwright test tests/e2e/admin.spec.ts tests/e2e/decision-timeline.spec.ts tests/e2e/costs-and-timing.spec.ts
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P06-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
