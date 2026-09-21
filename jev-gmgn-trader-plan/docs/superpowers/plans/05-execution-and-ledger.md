# P05 交易执行与账本 Implementation Plan

> **For agentic workers:** 本次只执行P05。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 实现明确授权的一次提交、未知订单恢复和实际成交账本闭环。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第10—11节；15.1—15.2、15.4—15.6的执行/账务部分。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

提交前不一致请求次数0；结果未知不重发；pause与发送临界区；账本/费用幂等；估值缺口不显示完整利润。

## 输入、范围与交付边界

**输入：** P04持久化TradeIntent与原始选择；P01执行语义/数据库约束；P02WorkerLease/provider调度；P03账户/余额版本。

**输出：** submitIntent/pollOrder/reconcileUnknown/recordFill；执行handler；成本分摊/三种收益DTO；持久化订单与ledger/lifecycle事实。

**不做：** 不自动开启实盘、不伪造真实成交、不反转或降档、不加入投资止损策略。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及`docs/execution/P04-handoff.md`和其中指定的已存在接口。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

```bash
pnpm typecheck
pnpm exec vitest run tests/integration/decision-round.test.ts tests/integration/quote-decision-contract.test.ts
```
前置P04未通过本地验收时，不开始本阶段；外部账号NOT_RUN不是本地代码阶段的自动阻塞。

## P05.01：实盘闸门、持久化提交与资金预留

**来源编号：** T14（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.03、P01.04、P02.01、P02.02、P04.03。**覆盖：** R10–R12，Review Focus 2/3。

**文件：** `packages/domain/src/execution-gate.ts`；`apps/worker/src/execution/{prepare,submit}.ts`；`packages/db/src/orders-repository.ts`；`tests/integration/execution-gate.test.ts`。

**接口：** `parseTradingEnabled(raw:string|undefined):boolean`；`checkExecutionGate(input:GateInput):GateResult`；`submitIntent(intentId:string):Promise<SubmitResult>`。GateInput包含envEnabled、paused、pauseRevision、workerEpoch、readiness、expiresAtMs、positionVersion、currentPositionVersion、fundsOk、unresolvedGlobalIntentId。

- [ ] 写环境开关测试，字符串false不能被truthy转换：

```typescript
import { expect, test } from 'vitest';
import { parseTradingEnabled } from './execution-gate';
test('live submit is fail-closed', () => {
  expect(parseTradingEnabled(undefined)).toBe(false);
  expect(parseTradingEnabled('false')).toBe(false);
  expect(parseTradingEnabled('true')).toBe(true);
  expect(() => parseTradingEnabled('yes')).toThrow('INVALID_TRADING_FLAG');
});
```

- [ ] 用计数fake transport测试：env关闭即使DB运行状态true、存在合法BUY，Swap调用次数仍为0；签名持仓/query_order读取不受禁写误伤。SUPPRESSED／BLOCKED／EXPIRED只在确认未发送时事务释放预留；重复处理不得重复释放；进入DISPATCHING后不能用该规则释放。
- [ ] prepare用DB事务锁定round/account、检查唯一intent、预留raw+费用，落PREPARED；发送前记录DISPATCHING和完整请求hash，commit后才网络提交。submitGate再次读取runtime pause和余额版本，并验证freshness／wallet／chain／authorization；不接受UI传来的未经catalog映射参数。
- [ ] 在共享提交临界区里完成pause revision核查和网络dispatch启动；pause API等待该临界区退出后报告已暂停，已有in-flight单独显示。失去DB／active锁立刻停止新发送。
- [ ] POST只发送一次；timeout、连接中断、发送后DB失败统归SUBMISSION_UNKNOWN，不释放预留、不再次POST。服务明确拒绝才FAILED，429也不自动重发。无client order id幂等支持就不宣称exactly-once。
- [ ] 测试金额被冻结、position变更BLOCKED、在途暂停、并发两个worker只有一个发送、密钥不进日志；提交`feat: gate and persist single-attempt trade submission`。

**验收：** 真实调用能力具备代码路径，但默认永不发送，且故障不增加第二次交易风险。


### 本阶段内联增补：实际传输契约及原决定保护（U01/U02/U03）

本任务只导入P01的ExecutionProjection/assertExecutionAgreement及P04的OriginalSelection，不再定义另一套语义或改写model_calls。

- [ ] `tests/integration/prompt-execution-contract.test.ts`使用P04产生的模型request/catalog/intent及实际GMGN序列化fake transport。`sent`必须从真正待发送字节按已核验route mapping反向归一化；accountId由受验证钱包映射、side由输入输出资产验证，不能复制shown/frozen假装检测。
- [ ] 分别篡改input amount、chain、资产、最低输出、slippage和交易模式，执行前全部报EXECUTION_CONTRACT_MISMATCH且POST=0。不要求不存在的roundId等字段也被GMGN接收。
- [ ] `tests/integration/decision-preservation.test.ts`注入BUY20但资金不足且SELL可执行，断言原selected/probabilities/hash不变、无SELL、无降档、无换币/换链、实际POST=0；低confidence合法决定不被阻止。
- [ ] 对unknown option、Jev timeout/429无规则/mock fallback；已有订单仍由独立poll查询。env关闭BUY显示SUPPRESSED，WAIT/ABSTAIN不生成交易。
- [ ] fake服务接受Swap后断开、或提交后DB写失败，均只记录未知；重启恢复不得再POST、预留不释放，后续确认追加事实。计数挂实际transport。
- [ ] appendLifecycle在准备/阻止/尝试/未知/已接受节点写入；原始模型记录只读。自然语言prompt改动仍需人工核对，不能只凭hash证明语义正确。

## P05.02：订单状态映射、未知提交和重启对账

**来源编号：** T15（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P05.01、P03.03。**覆盖：** R12，Review Focus 1/3。

**文件：** `packages/providers/src/gmgn/order-status.ts`；`apps/worker/src/execution/{poll,reconcile}.ts`；`tests/integration/order-recovery.test.ts`。

**接口：** `normalizeOrderStatus(raw:unknown,mapping:VerifiedOrderMapping):OrderObservation`；`pollOrder(orderId:string):Promise<OrderObservation>`；`reconcileUnknown(intentId:string):Promise<ReconciliationResult>`。OrderObservation包含normalizedState、rawState、report、evidenceQuality；未知string默认RECONCILING，不猜成功。

- [ ] 写未识别状态保守映射测试：

```typescript
import { expect, test } from 'vitest';
import { normalizeOrderStatus } from './order-status';
test('unrecognized status never becomes a fill', () => {
  const x=normalizeOrderStatus({status:'brand_new_state',order_id:'o1'},
    {version:1,successStatuses:['confirmed'],failureStatuses:['failed']});
  expect(x.normalizedState).toBe('RECONCILING');
  expect(x.report).toBeNull();
});
```

- [ ] 故障注入：fake服务器已记录订单后模拟超时，重启worker；断言POST计数仍1、预留未释放、全局新intent阻塞。
- [ ] 有order_id按2→4→8→15→30秒再30秒的间隔查询，受Plus额度和cooldown影响；没有ID查询活动证据，不凭金额近似唯一匹配。任何状态超时不能自动标失败，长未决变人工对账告警而非释放资金。
- [ ] `confirmed`且实际report字段不足则保留待账务核对；`successful/state=30`是否成功由锁定版本的真实证据映射，文档矛盾记录不删除。显式failed但已扣Gas也需要账务事件。
- [ ] 管理员可补充provider order_id／tx hash并由服务端验证对应账户资产；每次异常处理审计。不能提供无证据“忽略并重试”。相同余额变化有多个候选交易时保持未知。
- [ ] 跑恢复、未知enum、429时禁止跨链绕过、重复poll测试；提交`feat: reconcile uncertain orders without duplicate swaps`。

**验收：** 订单提交后的全部状态都可见，重启不会按本地未成功标记重新下单。


### 在途恢复与事件去重（U03/U05）

- [ ] 补`order-recovery.test.ts`的请求已接受响应丢失、重复poll、确认后写库失败再恢复、订单ID未知且余额变化有多个解释；POST<=1，unknown保留预留和全局占用。
- [ ] ORDER_ACCEPTED需服务接收证据，ORDER_CONFIRMED需成功映射及足够report；FILL_RECORDED与LEDGER_POSTED由P05.03事务产生。晚到确认只追加，不覆盖SUBMIT_ATTEMPTED时间和模型选择。
- [ ] Jev429不阻止订单核对；GMGN429期间所有该凭证的三链请求（含poll）停止，等待冷却只读恢复。超时不是自动失败，禁止人工无证据一键忽略再花同一资金。

## P05.03：成交落账、成本、费用和账户净值

**来源编号：** T16（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.03、P03.03、P05.02。**覆盖：** R12，Review Focus 5。

**文件：** `packages/domain/src/{cost-basis,equity}.ts`；`packages/db/src/ledger-repository.ts`；`apps/worker/src/execution/settle.ts`；`tests/integration/ledger.test.ts`。

**接口：** `allocateCost({quantityRaw,costUsd,sellRaw}):{releasedCostUsd:string;remainingCostUsd:string}`；`recordFill(db,fill:VerifiedFill):Promise<void>`；`calculateEquity(input:EquityInput):EquityResult`。

- [ ] 写部分卖出分摊和未知成本测试：

```typescript
import { expect, test } from 'vitest';
import { allocateCost } from './cost-basis';
test('partial exit releases proportional remaining cost', () => {
  expect(allocateCost({quantityRaw:'1000',costUsd:'100',sellRaw:'250'}))
    .toEqual({releasedCostUsd:'25',remainingCostUsd:'75'});
});
```

- [ ] 写DB测试重复同fill不重算数量／费用；同source_key但不同金额报`FILL_CONFLICT`而非吞并。转入10美元现金只增加资金，不增加realizedPNL。
- [ ] 用事务写fill、资金变动、ledger、position版本和reservation释放。买入成本为可证实支付USD＋归属费用；卖出净收入已经包含的tax不重扣，Gas独立一项；未知cost/fee保持null和coverage标记。
- [ ] failed扣Gas记expense不创建买入仓位；外部提现/充值写cashflow；base coin本身价格变化反映账户NAV，与MEME已实现PNL分开。未完成分页／估值的NAV标partial。
- [ ] 余额对账差异触发reconciliation，不覆盖账本抹平差异；修复以冲销或调整分录附原因；仓位清零时保留历史记录。
- [ ] 通过测试后提交`feat: account for actual fills costs and external cash flows`。

**验收：** 报价不被当成交，重复响应不重复收费，未知成本不伪装盈利。

### 本阶段内联增补：阶段耗时和完整成本口径


**文件：** 本任务新建`packages/domain/src/runtime-costs.ts`及测试和账单结算逻辑；复用P01成本仓储、P02阶段计量及P04 usage记录。运行成本API与页面由P06负责，不在本任务创建UI。

**接口：** `netAfterOperatingCosts({walletAdjustedChangeUsd,offWalletCostUsd,coverageComplete}):{valueUsd:string|null;quality:'complete'|'partial'}`；`recordProviderAttempt(db,attempt):Promise<void>`；`recordOperatingCost(db,entry):Promise<void>`。金额为DecimalString；attempt含provider/roundId/step/attemptId、queueWaitMs、requestMs、实际usage、pricingVersion、计费质量，不直接保存密钥headers。

- [ ] 写精确金额和缺失成本测试：

```typescript
import {expect,test} from 'vitest';
import {netAfterOperatingCosts} from './runtime-costs';
test('does not deduct gas twice',()=>{
  // 8 USD is already the wallet change after 2 USD of on-chain expenses.
  expect(netAfterOperatingCosts({walletAdjustedChangeUsd:'8',
    offWalletCostUsd:'3',coverageComplete:true}))
    .toEqual({valueUsd:'5',quality:'complete'});
});
test('unknown operating cost is not free',()=>{
  expect(netAfterOperatingCosts({walletAdjustedChangeUsd:'8',
    offWalletCostUsd:null,coverageComplete:false}))
    .toEqual({valueUsd:null,quality:'partial'});
});
```

- [ ] 运行对应测试确认FAIL，以decimal.js实现减法，不把结果舍入为整数或提前截断：

```typescript
import Decimal from 'decimal.js';
export function netAfterOperatingCosts(x:{walletAdjustedChangeUsd:string;
  offWalletCostUsd:string|null;coverageComplete:boolean}) {
  if (!x.coverageComplete || x.offWalletCostUsd===null)
    return {valueUsd:null,quality:'partial' as const};
  return {valueUsd:new Decimal(x.walletAdjustedChangeUsd)
    .minus(x.offWalletCostUsd).toString(),quality:'complete' as const};
}
```

- [ ] 复核并复用P01建立的operating_cost_entries及唯一source_key，记录billingPeriod/quality/offWallet/pricingVersion/allocationMethod/sourceEvidence；金额nullable，不以0替代缺失。修正采用冲销关联，不覆盖历史或累加估算与实账。实际账单到达后成本视图选择结算链最终值。
- [ ] 验证P04的模型每个attempt已分别保存真实usage、定价快照和estimated金额；失败没有usage就unknown，既不抹去attempt，也不把未经核对的价格称实际账单。固定模型/费用版本不从另一仓库的常量复制。
- [ ] Plus权重只作为调度资源；套餐费由管理员基于账单录入，不默认猜价格。GET读账单和分摊覆盖；POST仅允许认证管理员登记有计费期/来源/金额的成本条目并审计。默认完整账期展示，跨期查询缺少明确分摊时adjusted result为partial。
- [ ] 消费P02/P04的指标记录queueWait、providerRequest、A/B、数据age、quoteAtDispatchAge、confirmationLag；本地duration用单调clock，跨进程时钟异常为null。展示关键路径端到端值与并行阶段列表，不简单相加。未发生步骤不能显示0ms成功。
- [ ] fake clock测试排队200ms+请求50ms分别记录；并行100ms和80ms不能显示180ms端到端；重启后的performance时钟不能与旧进程相减。GMGN/Jev冷却独立，已在途交易确认不因模型故障停查。
- [ ] 向P06导出三种结果DTO，要求页面同时展示交易PNL、调整外部资金流的钱包变化、扣明确off-wallet成本后的实验结果及已知小计/缺失项。测试Gas已入钱包变化时只扣一次、估算→实际账单替代、重复usage回执不重复记费、月费不被默认全扣一天。
- [ ] 本阶段运行费用、阶段计量和ledger测试；API/E2E归P06，部署文档归P08；提交`feat: report stage timing and attributable operating costs`。

**验收：** 不增加预期收益模型或对照组；成本完整度不足不显示成已确认净利润。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm exec vitest run packages/domain/src/execution-gate.test.ts packages/domain/src/execution-contract.test.ts packages/domain/src/runtime-costs.test.ts packages/providers/src/gmgn/order-status.test.ts
pnpm exec vitest run tests/integration/execution-gate.test.ts tests/integration/prompt-execution-contract.test.ts tests/integration/decision-preservation.test.ts tests/integration/order-recovery.test.ts tests/integration/ledger.test.ts
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P05-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
