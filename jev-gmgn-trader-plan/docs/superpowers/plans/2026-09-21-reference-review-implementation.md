# 参考项目评审增补 Implementation Plan（R2）

> **For agentic workers:** 与主计划一并执行；使用环境可用的superpowers:subagent-driven-development或superpowers:executing-plans。以下代码是目标契约和待实现测试，不代表已经实施。真实网络默认阻断。

**Goal:** 在不改变Jev自主选择、三链及GMGN Plus边界的前提下，落实U01—U06的执行准确性、历史上下文和可观察性。

**Architecture:** 仍为Next.js + 单active Worker + PostgreSQL。领域纯函数负责一致性验证，数据库保存不可变事实、生命周期事件和成本记录；不追加规则交易器、向量库、Redis或新的行情供应商。

**Tech Stack:** 沿用主计划；Node.js/依赖版本由T01固定，不从参考项目复制Bun或Effect依赖。

**Spec:** [主设计第15节](../specs/2026-09-21-jev-gmgn-trader-design.md#15-r2参考项目评审的工程增补)。

**Main plan:** [22项主任务](2026-09-21-jev-gmgn-trader-implementation.md)。

**Evidence:** [固定参考源码](../../references/2026-09-21-reference-project-review.md)。

## Global Constraints

- R01—R12不变：robinhood/bsc/sol；10/20/50/100 USD买入；25/50/75/100%卖出；Plus共享预算；每轮最多一笔Swap；数据库配置；env关闭时无真实提交。
- U01—U06都是第一版必做；D01/SSE仅是后续增强。U项并入对应T任务，不在T22结束后才实施。
- 原始模型选择不可修改；执行失败不反向、降档、换币、换链或用规则模型继续交易。
- 历史只从本地已知事实构造，不新拉历史行情、不自动学习权重、不基于亏损加禁买条件。
- 真实提交必须有单独实施及运行授权；本次文档修订不会启用TRADING_ENABLED。

## Review Focus

1. 提示词的金额/执行方式与真正序列化请求不同：U01的字段变异测试直接检查transport捕获的请求，不能只比较两个来源相同的对象。
2. 额度不足或模型失败被转换为其他交易：U02检查原记录hash、POST计数及无fallback调用。
3. 分页/网络失败与重复结果污染持仓和账本：U03检查持仓、预留、订单、fill、生命周期事件的一致性。
4. 后来才获知的成交倒灌进旧快照：U04同时约束事件时间和记录时间，重复查询不读取可变当前状态。
5. 多次模型调用/重复事件和计费估算混为真实收益：U05/U06检查去重、统计口径、计费期、已知覆盖与重复扣费。

## 执行顺序与接口边界

| 主阶段 | 必须同步完成的增补 |
|---|---|
| T01—T03 | U01共享执行语义类型；U04历史索引；U05事件表；U06成本表 |
| T06—T10 | U03独立冷却及持仓回归；U04查询/快照/压缩 |
| T11—T15 | U01/U02模型请求到提交验证；U05事件生产；U06调用计量 |
| T16—T18 | U05统计和页面；U06费用口径和页面；U04历史证据展示 |
| T19—T22 | U01—U06集成门禁、故障恢复、部署与交付状态 |

类型与函数在下列文件明确导出；数据库连接`Db`、`DecisionState`、`QuotedAction`、`TradeIntent`、`ChoiceResult`来自主计划。不要复制参考项目中的可交易mock模型进入生产。测试依赖注入仅用于测试，无对照组界面或收益比较。

---

## U01：提示词、动作、报价和提交的一致性

**归属：** T01、T11、T12、T14、T20。**前置：** T02金额类型和T05序列化契约。

**文件：** 新建`packages/domain/src/execution-semantics.ts`、`execution-contract.ts`及同名测试；修改`prompts/decision-v1.md`、`packages/providers/src/jev/client.ts`、`apps/worker/src/decision/{quotes,sizing}.ts`、`apps/worker/src/execution/submit.ts`；增加`tests/integration/prompt-execution-contract.test.ts`。

**接口：**

```typescript
export interface ExecutionSemantics {
  schemaVersion: 1;
  marketType: 'SPOT';
  orderType: 'EXACT_IN_SWAP';
  buyNotionalBasis: 'INPUT_PRINCIPAL_USD_REFERENCE';
  sellBasis: 'SNAPSHOT_AVAILABLE_RAW';
  allowsShorting: false;
  separateFees: true;
}
export const EXECUTION_SEMANTICS: Readonly<ExecutionSemantics> = Object.freeze({
  schemaVersion: 1, marketType: 'SPOT', orderType: 'EXACT_IN_SWAP',
  buyNotionalBasis: 'INPUT_PRINCIPAL_USD_REFERENCE',
  sellBasis: 'SNAPSHOT_AVAILABLE_RAW', allowsShorting: false, separateFees: true,
});
export interface ExecutionProjection {
  chain: 'robinhood' | 'bsc' | 'sol';
  accountId: string;
  side: 'BUY' | 'SELL';
  inputAssetId: string;
  outputAssetId: string;
  inputAmountRaw: string;
  minOutputAmountRaw: string;
  slippageBps: number;
  orderType: 'EXACT_IN_SWAP';
}
export function assertExecutionAgreement(
  shown: ExecutionProjection,
  frozen: ExecutionProjection,
  sent: ExecutionProjection,
): void;
```

`sent`由T05锁定的真实GMGN请求字段反向归一化而来，不能从shown/frozen直接复制；未传输的accountId从已验证钱包绑定映射，side由输入输出方向验证。API字段与本地字段不要求同名，映射须有契约测试。configVersion、positionVersion、quoteId、roundId、optionId及semantics hash作为intent元数据另行核对，不虚构GMGN支持这些字段。

- [ ] 先编写失败测试，包括传输数量和方向被改变：

```typescript
import { expect, test } from 'vitest';
import { assertExecutionAgreement, type ExecutionProjection } from './execution-contract';
const buy: ExecutionProjection = {
  chain:'bsc', accountId:'account-bsc', side:'BUY',
  inputAssetId:'native:bsc', outputAssetId:'bsc:token-a',
  inputAmountRaw:'20000000000000000', minOutputAmountRaw:'990000',
  slippageBps:100, orderType:'EXACT_IN_SWAP',
};
test.each([
  {...buy,inputAmountRaw:'10000000000000000'},
  {...buy,side:'SELL' as const},
  {...buy,chain:'sol' as const},
  {...buy,minOutputAmountRaw:'900000'},
  {...buy,slippageBps:500},
])('rejects a mutated submission', sent => {
  expect(() => assertExecutionAgreement(buy,buy,sent))
    .toThrow('EXECUTION_CONTRACT_MISMATCH');
});
```

- [ ] 运行`pnpm exec vitest run packages/domain/src/execution-contract.test.ts`，先观察缺失实现的FAIL。
- [ ] 实现固定字段逐项比较；使用显式字段而非JSON属性顺序：

```typescript
const keys: (keyof ExecutionProjection)[] = ['chain','accountId','side',
  'inputAssetId','outputAssetId','inputAmountRaw','minOutputAmountRaw',
  'slippageBps','orderType'];
export function assertExecutionAgreement(shown: ExecutionProjection,
  frozen: ExecutionProjection, sent: ExecutionProjection): void {
  if (keys.some(k => shown[k] !== frozen[k] || frozen[k] !== sent[k]))
    throw new Error('EXECUTION_CONTRACT_MISMATCH');
}
```

- [ ] 将共享ExecutionSemantics和规范化hash放入A/B实际请求及决策记录；提示词明确现货、ExactIn、美元本金参考值、额外费用、无做空。指令中不能出现做市/IOC保证立即成交等不一致执行承诺。
- [ ] 在集成测试捕获模型真实request body及fake transport收到的签名前后交易请求，按官方字段反向解析后比较；至少变异一次请求里的数量/滑点/资产，让测试在序列化错误时失败。
- [ ] 报价若已过期或刷新条件变化，旧action拒绝发送；受deadline约束最多一次刷新并重新交B选择。测试新quote最小输出变化但没有新B记录时POST=0；重新B后仍最多一个最终intent。
- [ ] 运行领域和集成测试，审阅prompt diff，再提交`test: bind Jev descriptions to exact execution contracts`。

**验收：** 模型选择的交易含义、冻结记录和真实提交投影一致；自然语言指令仍需人工审阅，不把字符串搜索当完整语义证明。

## U02：不可变模型选择与明确失败

**归属：** T11—T15、T20。**前置：** U01、T13意图保存。

**文件：** 新建`packages/domain/src/decision-outcome.ts`及测试；修改model_calls仓储、`run-round.ts`、`submit.ts`；增加`tests/integration/decision-preservation.test.ts`。

**接口：**

```typescript
export interface OriginalSelection {
  selectedOptionId: string;
  probabilities: Readonly<Record<string,number>>;
  confidence: number;
  responseHash: string;
}
export type PreparationResult =
  | {status:'READY'; optionId:string}
  | {status:'BLOCKED'; optionId:string; reason:string};
export function prepareExecutionOutcome(
  original: OriginalSelection,
  rejectionReason: string | null,
): PreparationResult;
```

- [ ] 写失败测试，检查未回写原选择：

```typescript
import { expect, test } from 'vitest';
import { prepareExecutionOutcome } from './decision-outcome';
test('insufficient funds never converts BUY into SELL or a smaller tier', () => {
  const original=Object.freeze({selectedOptionId:'BUY_A_USD20',
    probabilities:Object.freeze({BUY_A_USD20:0.6,WAIT:0.4}),
    confidence:0.3,responseHash:'synthetic-response-hash'});
  const before=JSON.stringify(original);
  expect(prepareExecutionOutcome(original,'INSUFFICIENT_FUNDS'))
    .toEqual({status:'BLOCKED',optionId:'BUY_A_USD20',reason:'INSUFFICIENT_FUNDS'});
  expect(JSON.stringify(original)).toBe(before);
});
```

- [ ] 运行`pnpm exec vitest run packages/domain/src/decision-outcome.test.ts`确认FAIL。
- [ ] 实现只返回派生结果、不写入original的纯函数：

```typescript
export function prepareExecutionOutcome(original: OriginalSelection,
  rejectionReason: string | null): PreparationResult {
  return rejectionReason === null
    ? {status:'READY',optionId:original.selectedOptionId}
    : {status:'BLOCKED',optionId:original.selectedOptionId,reason:rejectionReason};
}
```

- [ ] 执行器最终选择必须能反查同round的原始model_call和catalog；仓储不提供update model decision操作，错误修正只能新增注释/关联记录。对同ID不同hash插入拒绝。
- [ ] 集成场景：fake Jev选BUY20，余额不足但SELL可执行；断言无Swap、无第二选择、无概率修改；低confidence且执行条件充分的BUY可正常到PREPARED；非法option、超时、429均DECISION_ERROR且无mock/规则fallback调用。
- [ ] 对WAIT/ABSTAIN保留原结果；env关闭时合法BUY记SUPPRESSED，不改为WAIT。对账任务不受模型错误阻断。运行测试后提交`test: preserve model intent across execution failures`。

**验收：** 页面能同时看到原始决定与未执行原因，不能显示为Jev自行改变主意。

## U03：持仓、冷却及在途故障回归

**归属：** T06、T09、T14、T15、T19、T20。**前置：** 对应T任务的fake transport和测试数据库。

**文件：** 扩展`tests/integration/{order-recovery,worker-lifecycle,failure-matrix}.test.ts`；新建`packages/domain/src/holdings-reconciliation.ts`及测试；扩展`apps/worker/src/scheduler/cooldown.test.ts`。

**接口：** `applyBalanceEvidence(previousRaw:string,evidence:{kind:'verified_balance';raw:string}|{kind:'incomplete';reason:string}):string`。该函数只演示余额覆盖条件；真实同步仍须执行主计划T09完整分页和单币验证，不允许单靠它证明账户完整。

- [ ] 写失败测试：

```typescript
import { expect,test } from 'vitest';
import { applyBalanceEvidence } from './holdings-reconciliation';
test.each(['timeout','page_2_failed','repeated_cursor','partial_empty'])
('does not erase a managed balance on %s', reason => {
  expect(applyBalanceEvidence('1000',{kind:'incomplete',reason})).toBe('1000');
});
test('accepts an independently verified zero balance', () => {
  expect(applyBalanceEvidence('1000',{kind:'verified_balance',raw:'0'})).toBe('0');
});
```

- [ ] 运行同名测试确认FAIL，实现`incomplete`保持旧数量且外层标quality=partial，`verified_balance`校验非负原始整数字符串后才更新。
- [ ] 对真实collector路径分别注入第一页正常/第二页失败、重复cursor、空但partial、资产掉榜、安全/KOL接口不可用；断言旧managed记录存在、下一轮观察集合包含它，缺失标签不影响其SELL动作可见性。
- [ ] 在T14 fake transport“服务已接受”后、客户端收到响应前断开；重启、DB写失败、重复确认各场景断言POST<=1，预留在unknown期间保留，fill/ledger/lifecycle source_key唯一。
- [ ] 分别注入Jev429和GMGN429：前者不得设置GMGN冷却且已有订单可查询；后者所有三链该凭证调用停止。使用虚拟时钟，冷却结束前actual network call count不增加；恢复先读探针，不重试Swap。
- [ ] fake计数检查应挂在实际HTTP transport，而不是仅统计队列任务个数；提交`test: cover incomplete holdings and uncertain trade recovery`。

**验收：** U03不添加投资止损或自动卖出；它只保证持仓事实和提交次数正确。

## U04：按资产检索历史事实

**归属：** T03、T10、T12、T18、T20。**前置：** T03数据库和已有不可变model/ledger/audit记录；事件表在T03同批建立。

**文件：** 新建`packages/domain/src/asset-history.ts`及测试、`packages/db/src/asset-history-repository.ts`、`tests/integration/asset-history.test.ts`；修改snapshot/packing和sizing、数据库migration。

**接口：**

```typescript
export interface AssetHistoryEvent {
  id:string; accountId:string; assetId:string;
  occurredAtMs:number; recordedAtMs:number;
  kind:'MODEL_SELECTION'|'EXECUTION_BLOCKED'|'FILL'|'EXECUTION_ERROR';
  payload:Readonly<Record<string,unknown>>;
}
export interface HistoryQuery {
  accountId:string; assetId:string; cutoffAtMs:number;
  lookbackMs:number; limit:number;
}
export function selectKnownHistory(rows:ReadonlyArray<AssetHistoryEvent>,
  query:HistoryQuery):AssetHistoryEvent[];
```

- [ ] 写防未来泄漏和身份隔离测试：

```typescript
import { expect,test } from 'vitest';
import { selectKnownHistory,type AssetHistoryEvent } from './asset-history';
test('selects only facts known by the snapshot cutoff', () => {
  const base={accountId:'a1',assetId:'bsc:token-a',occurredAtMs:80,
    recordedAtMs:90,kind:'FILL' as const,payload:{amountRaw:'100'}};
  const rows:AssetHistoryEvent[]=[
    {...base,id:'known'},
    {...base,id:'late',recordedAtMs:110},
    {...base,id:'future',occurredAtMs:120},
    {...base,id:'other-chain',assetId:'sol:token-a'},
    {...base,id:'other-account',accountId:'a2'},
  ];
  expect(selectKnownHistory(rows,{accountId:'a1',assetId:'bsc:token-a',
    cutoffAtMs:100,lookbackMs:100,limit:3}).map(x=>x.id)).toEqual(['known']);
});
```

- [ ] 运行测试确认FAIL，纯选择实现如下；参数必须先校验整数非负cutoff/正limit/正lookback：

```typescript
export function selectKnownHistory(rows:ReadonlyArray<AssetHistoryEvent>,
  q:HistoryQuery):AssetHistoryEvent[] {
  return rows.filter(x=>x.accountId===q.accountId && x.assetId===q.assetId &&
    x.occurredAtMs<=q.cutoffAtMs && x.recordedAtMs<=q.cutoffAtMs &&
    x.occurredAtMs>=q.cutoffAtMs-q.lookbackMs)
    .sort((a,b)=>b.occurredAtMs-a.occurredAtMs ||
      b.recordedAtMs-a.recordedAtMs || b.id.localeCompare(a.id))
    .slice(0,q.limit);
}
```

- [ ] 数据库查询同样按两个时间条件和相同排序，采用repeatable-read获取一致读视图；实际asset历史从不可变事实构造，不能用事后可变orders.status覆盖先前事件。保存本轮选择的event IDs、hash、cutoff和coverage。
- [ ] A默认每asset过去30天最多3摘要；B只展开相同截止点同一组记录。加版本化配置`assetHistoryLookbackDays=30`和`assetHistoryLimit=3`，范围1..365天与0..20条。新配置由schema迁移补默认，不覆盖原金额档位。
- [ ] pack将每资产历史3→1→0后仍保留asset ID、持仓和coverage；全局历史与资产历史同eventId使用引用，不能重复计数。缺历史返回空列表、unknown成本保持null，不生成“好/坏钱包”结论。
- [ ] 集成测试晚到确认、前一轮亏损但仍允许本轮BUY、历史读取不产生GMGN/Jev额外调用、B引用A的cutoff、跨链同地址不混记录；页面可查看来源事件。提交`feat: add bounded asset-scoped decision history`。

**验收：** 只增强Jev可见事实；不建立向量库、收益筛选、历史回测对照组或自主训练机制。

## U05：持久化生命周期时间线与指标

**归属：** T03、T13—T18、T20。**前置：** T03迁移、T13意图、T15状态和T16账本。

**文件：** 新建`packages/db/src/lifecycle-repository.ts`、`packages/domain/src/lifecycle-summary.ts`及测试；修改round/submit/poll/settle；新建`apps/web/src/app/api/decisions/[id]/timeline/route.ts`、`apps/web/src/components/DecisionTimeline.tsx`及`tests/e2e/decision-timeline.spec.ts`。

**接口：** `appendLifecycle(db,event):Promise<{eventId:string;sequence:string}>`；`readTimeline(db,{roundId,afterSequence,limit}):Promise<TimelinePage>`；`summarizeLifecycle(events):LifecycleSummary`。TimelinePage含events、nextSequence，limit1..100。事件字段至少eventId、eventKey、roundId、intentId/orderId可空、type、occurredAtMs、recordedAtMs、sequence、payload；payload用事件类型判别的Zod union验证，不包含secret。

生命周期类型至少包含SNAPSHOT_SAVED、MODEL_A_COMPLETED、QUOTES_READY、MODEL_B_COMPLETED、ROUND_COMPLETED、INTENT_CREATED、EXECUTION_BLOCKED、SUBMIT_ATTEMPTED、SUBMISSION_UNKNOWN、ORDER_ACCEPTED、ORDER_CONFIRMED、FILL_RECORDED、LEDGER_POSTED、EXECUTION_FAILED。A/B错误用具体error事件，不能产生有效ROUND_COMPLETED；WAIT/ABSTAIN可正常完成。

- [ ] 先用数据库集成测试验证同event_key两次追加只产生一行和一个sequence；同key不同payload报冲突。序号在同事务按聚合递增；关键状态更新与事件写入要么都提交要么都回滚。
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
- [ ] 通过事务把事件接到全部阶段；unknown恢复只追加已知事实。界面并列展示原始动作与执行结果，A/B/分组数量单列；对账确认晚到时可以重建，不修改原提交事件。
- [ ] GET只读DB且requireAdmin；前端SWR首次加载及刷新使用稳定游标重查/合并eventId，loading/partial/error/unknown有不同文本。100次刷新不产生上游请求或新事件。
- [ ] E2E验证“Jev选择买入20美元，但执行被阻止”显示两种信息，WAIT不显示成交，unknown不显示失败；重启/重连后能恢复时间线；运行测试后提交`feat: expose durable decision-to-fill timelines`。

**验收：** 时间线是数据库事实视图，不是只存在浏览器内存里的实时演示；D01/SSE不参与本任务验收。

## U06：阶段耗时和完整成本口径

**归属：** T03、T06、T11、T13、T16—T18、T20、T21。

**文件：** 新建`packages/domain/src/{runtime-costs,stage-metrics}.ts`及测试、`packages/db/src/operating-costs-repository.ts`；修改model_calls/schema、provider调度/调用、overview/system查询；新建`apps/web/src/app/api/operating-costs/route.ts`；扩展费用与页面测试。

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

- [ ] T03建立operating_cost_entries及唯一source_key，记录billingPeriod/quality/offWallet/pricingVersion/allocationMethod/sourceEvidence；金额nullable，不以0替代缺失。修正采用冲销关联，不覆盖历史或累加估算与实账。实际账单到达后成本视图选择结算链最终值。
- [ ] 模型每个attempt分别保存真实usage、定价快照和estimated金额；失败没有usage就unknown，既不抹去attempt，也不把未经核对的价格称实际账单。固定模型/费用版本不从另一仓库的常量复制。
- [ ] Plus权重只作为调度资源；套餐费由管理员基于账单录入，不默认猜价格。GET读账单和分摊覆盖；POST仅允许认证管理员登记有计费期/来源/金额的成本条目并审计。默认完整账期展示，跨期查询缺少明确分摊时adjusted result为partial。
- [ ] 指标记录queueWait、providerRequest、A/B、数据age、quoteAtDispatchAge、confirmationLag；本地duration用单调clock，跨进程时钟异常为null。展示关键路径端到端值与并行阶段列表，不简单相加。未发生步骤不能显示0ms成功。
- [ ] fake clock测试排队200ms+请求50ms分别记录；并行100ms和80ms不能显示180ms端到端；重启后的performance时钟不能与旧进程相减。GMGN/Jev冷却独立，已在途交易确认不因模型故障停查。
- [ ] 页面同时展示交易PNL、调整外部资金流的钱包变化、扣明确off-wallet成本后的实验结果及已知小计/缺失项。测试Gas已入钱包变化时只扣一次、估算→实际账单替代、重复usage回执不重复记费、月费不被默认全扣一天。
- [ ] 运行费用、阶段计量、API和E2E测试；更新部署及配置手册；提交`feat: report stage timing and attributable operating costs`。

**验收：** 不增加预期收益模型或对照组；成本完整度不足不显示成已确认净利润。

## D01：后续SSE，不作为本轮实施前提

仅记录接口演进方向：仍先持久化event，再按eventId/sequence通知；鉴权、Last-Event-ID补拉、重连、幂等和慢消费者处理必需。不直接复用公开CORS的示例server。当前T18用DB+SWR通过完整功能验收即可。

## 联合验收与交付

- [ ] T20的requirement/task/test/result矩阵同时覆盖R01—R12、U01—U06；D01标DEFERRED。
- [ ] 运行主计划的lint/typecheck/test/test:integration/test:e2e/build门禁，保存实际结果；模型fixture和fake transport不是盈利对照组。
- [ ] 校验提示词语义hash、原始模型记录hash、按资产历史cutoff和事件/成本唯一键均出现在测试及页面证据中。
- [ ] T22只读/实盘验收单独标NOT_RUN/BLOCKED/PASS，不用参考项目的测试数或模拟收益代替本项目证据。

本文件仅增加工程计划，不创建产品实现、不安装参考项目、不执行交易。正式实施仍需项目所有者的独立指令。
