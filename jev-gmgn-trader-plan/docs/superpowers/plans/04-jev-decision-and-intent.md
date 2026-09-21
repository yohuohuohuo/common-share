# P04 Jev 决策与交易意图 Implementation Plan

> **For agentic workers:** 本次只执行P04。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 从快照经两步Jev Choice产生唯一、可追溯、金额冻结的交易意图。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第8节、10.2；15.1—15.5的决策侧要求。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

合法低置信度不拒单；错误不是WAIT；全局/分组仍一个intent；刷新报价必须重新B；A/B同配置/cutoff。

## 输入、范围与交付边界

**输入：** P03 DecisionState/历史cutoff/报价必要证据，P01配置/语义/事件仓储，P02带限额的客户端及attempt计量。

**输出：** JevClient/ChoiceResult、OriginalSelection；DirectionSelection、QuotedAction/SizedSelection；TradeIntent/runRound；不变的call/事件/usage记录。

**不做：** 本阶段不接真实提交handler，不改变策略、不将假模型作为实盘fallback、不完成账本。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及`docs/execution/P03-handoff.md`和其中指定的已存在接口。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

```bash
pnpm typecheck
pnpm exec vitest run apps/worker/src/decision/snapshot.test.ts apps/worker/src/decision/packing.test.ts tests/integration/asset-history.test.ts
```
前置P03未通过本地验收时，不开始本阶段；外部账号NOT_RUN不是本地代码阶段的自动阻塞。

## P04.01：Jev Choice客户端、结果验证和容量复选

**来源编号：** T11（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.01、P03.04。**覆盖：** R05、R11。

**文件：** `packages/providers/src/jev/{client,schemas}.ts`；`apps/worker/src/decision/{selection,hierarchical}.ts`；`prompts/decision-v1.md`及测试。

**接口：** `JevClient.choose({model,state,instructions,criteria}):Promise<ChoiceResult>`；`validateChoice(raw:unknown,allowed:string[]):ChoiceResult`；`selectDirection(state):Promise<DirectionSelection>`。ChoiceResult含selected、probabilities、confidence、actualModel、usage；DirectionSelection是BUY／SELL（具体ID）或WAIT／ABSTAIN。

- [ ] 写未知option绝不执行测试：

```typescript
import { expect, test } from 'vitest';
import { validateChoice } from './schemas';
test('model cannot invent executable options', () => {
  expect(() => validateChoice({choice:'SEND_ALL',confidence:1,
    probabilities:{SEND_ALL:1}},['WAIT','ABSTAIN','BUY_A']))
    .toThrow('UNKNOWN_OPTION');
});
```

- [ ] 跑schema测试确认FAIL；另外验证NaN、缺字段、probabilities键不一致、非有限值和概率和的容差，语法错误记协议错误而非confidence不够。
- [ ] 按官方`POST /v1/systemone`构造`state/model/questions`，单个question为choice/instructions/criteria；Bearer只在服务端。保存原始返回、model和usage；读请求最多一次受deadline约束的重试，429遵循header；不能无限重问直到BUY。[S12、S13]
- [ ] 一级按chain+assetId稳定排序生成方向选项，WAIT/ABSTAIN始终存在。选项≤255且预算内直接choose；超限按最多40资产一组调用同一模型选方向，再以入选项做全局复选，必要时递归。记录所有组、输入、丢弃原因和selectionMode；不是代码按分数选赢家。
- [ ] 测试低confidence的合法BUY仍被返回、所有组WAIT最终WAIT、某组ABSTAIN被记录、超限后不丢managed持仓；实际命中分组路径不伪称单次全局判断。
- [ ] 跑所有Jev fake transport测试后提交`feat: implement constrained Jev direction selection`。

**验收：** Jev输入输出完全结构化；无自由地址执行，无confidence交易门槛。

### 本阶段内联增补：不可变模型选择与明确失败


**文件：** 本阶段新建`packages/domain/src/decision-outcome.ts`及测试；本阶段修改model_calls仓储与`run-round.ts`，测试使用准备阶段的fake executor；`submit.ts`的真实接线及`tests/integration/decision-preservation.test.ts`由P05.01负责。

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

- [ ] 交接约束：P05执行器最终选择必须能反查同round的原始model_call和catalog；仓储不提供update model decision操作，错误修正只能新增注释/关联记录。对同ID不同hash插入拒绝。
- [ ] 本阶段准备路径场景：fake Jev选BUY20，余额不足但SELL可执行；断言无Swap、无第二选择、无概率修改；低confidence且执行条件充分的BUY可正常到PREPARED；非法option、超时、429均DECISION_ERROR且无mock/规则fallback调用。
- [ ] 对WAIT/ABSTAIN保留原结果；env关闭时合法BUY记SUPPRESSED，不改为WAIT。对账任务不受模型错误阻断。运行测试后提交`test: preserve model intent across execution failures`。

**验收：** 页面能同时看到原始决定与未执行原因，不能显示为Jev自行改变主意。

## P04.02：四档报价、第二步金额选择和动作冻结

**来源编号：** T12（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.02、P02.02、P03.03、P04.01。**覆盖：** R05–R07，Review Focus 2。

**文件：** `packages/domain/src/actions.ts`；`apps/worker/src/decision/{quotes,sizing}.ts`；`packages/db/src/action-catalog-repository.ts`及测试。

**接口：** `buildBuyTiers(config,paymentAsset,price,balance):TierCandidate[]`；`buildSellTiers(config,position):TierCandidate[]`；`quoteTiers(direction,state):Promise<QuotedAction[]>`；`selectSizedAction(state,direction,actions):Promise<SizedSelection>`。QuotedAction包含design第8节所有绑定字段，SizedSelection为具体动作或WAIT／ABSTAIN。

- [ ] 写档位绑定与余额不足测试，美元档位不降低：

```typescript
import { expect, test } from 'vitest';
import { buildSellTiers } from './actions';
test('sell fractions bind current available raw amount', () => {
  const tiers=buildSellTiers({sellBpsTiers:[2500,5000,7500,10000]},
    {id:'p1',version:3,availableRaw:'1000'});
  expect(tiers.map(t=>t.inputAmountRaw)).toEqual(['250','500','750','1000']);
  expect(tiers.every(t=>t.positionVersion===3)).toBe(true);
});
```

- [ ] 测试20USD余额且需要预留费用时20USD档不可执行，10USD档可选；没有任何档则NO_EXECUTABLE_TIER，不选其他token。
- [ ] 只有一级选中的asset请求四档quote，每次权重10通过P02.02；记录报价时间、输入/输出/最小输出、实际费用证据和unsupported原因；不做60×4全候选报价。原生价格source/precision来自能力验证，不能USD默认1。
- [ ] 四档quote共享同一个账户/config版本；超过TTL只允许一次fresh quote补齐，仍过期本轮明确结束，不循环报价直至成功。第二步把direction和原快照、更新事实一起提供，最多四档+WAIT+ABSTAIN。
- [ ] 使用ExactIn raw冻结action，100%卖出无动态percent；选项ID与catalog关联不可篡改；重复raw档合并但留原档别名。模型选择unknown ID抛错，不生成金额。
- [ ] 测试配置从20改30但旧action仍20、stageB可WAIT、模型耗时超过TTL不提交；提交`feat: let Jev select quoted USD and sell-percentage tiers`。

**验收：** 全局单动作与两次模型调用一致，费用单独预留，执行器不会改Jev金额。


### 本阶段内联增补：模型实际见到的报价（U01/U04）

- [ ] A/B的真实request body均包含P01的ExecutionSemantics及规范化hash；提示词说明现货ExactIn、美元本金、额外费用、无做空。保存prompt hash，不写死“主动成交最强”等策略偏好。
- [ ] `tests/integration/quote-decision-contract.test.ts`捕获B实际request body、catalog和freeze后的ExecutionProjection，逐字段相同；不只检测提示词关键词。
- [ ] 报价刷新如果最低输出/费用/授权条件改变，旧B选项作废；同一轮deadline内最多一次刷新，再给B一次明确重新选择并保存新call，仍只产一个最终intent。未重新B时输出EXPIRED/BLOCKED而不是自动换quote。
- [ ] B资产历史直接使用A快照中保存的event IDs/hash/cutoff，不重新读取后来确认的数据；只允许行情和执行核验明确更新并标来源时间。
- [ ] 自然语言承诺由人工审阅；实际供应商请求反向解码测试留给P05.01。本阶段验证模型请求与冻结意图，不声称已经提交成交。

## P04.03：决策轮编排与唯一交易意图

**来源编号：** T13（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P03.04–P04.02、P01.03、P01.04。**覆盖：** R05、R09、R12。

**文件：** `apps/worker/src/decision/run-round.ts`；`packages/db/src/intents-repository.ts`；`tests/integration/decision-round.test.ts`。

**接口：** `runRound(deps:RoundDependencies):Promise<RoundResult>`；`persistIntent(db,roundId,action):Promise<TradeIntent>`；RoundDependencies包含repo、Jev选择器、quote服务、clock，无全局fetch。

- [ ] 编写集成测试：同一round由两个调用尝试persistIntent，只能成功一条，其他明确冲突。WAIT／ABSTAIN不创建交易意图但保存model_call。
- [ ] 运行`pnpm exec vitest run tests/integration/decision-round.test.ts`确认FAIL。
- [ ] 编排严格顺序：

```text
read config + runtime → create round & snapshot
→ check unresolved-global-slot
→ selectDirection(A)
→ if WAIT/ABSTAIN finish with that status
→ get up-to-date selected facts + quote four tiers
→ selectSizedAction(B)
→ if WAIT/ABSTAIN finish
→ persist frozen intent + amount reservation atomically
→ hand intent ID to executor queue
```

- [ ] 所有步骤引用同一configVersion；warmup／错误／无可执行档分别记录，不转译为WAIT。轮间不并发重叠；全局unknown订单使本轮只完成读取和记录`BLOCKED_UNRESOLVED_ORDER`。
- [ ] 记录A/B latency、token usage、quote weight、过期和阶段失败；分组调用保存完整路径。一次轮最多创建一个intent，即便部分步骤自动重试也不重复。
- [ ] 通过并发与错误测试后提交`feat: orchestrate globally serialized decision rounds`。

**验收：** 可以完整运行到已持久化交易意图，尚不要求真实发送；同一事务的生命周期记录可从数据库重建。


### 本阶段内联增补：事件生产与调用成本（U05/U06）

- [ ] 调用P01的appendLifecycle：快照保存、A完成、四档报价、B完成、有效轮结束、intent创建各自写稳定eventKey；状态变更与相应事件同事务。分组多次调用保留call ID，不多算轮数。
- [ ] WAIT/ABSTAIN正常ROUND_COMPLETED；非法选择、网络/解析/超时错误追加MODEL_A_ERROR/MODEL_B_ERROR及错误结果，不冒充有效决定。
- [ ] 每次Jev attempt保存provider/step/attemptId、排队/请求耗时、actualModel、真实usage、pricingVersion、estimated/unknown成本；失败无usage不填0。price缺失时成本null，禁止从参考仓库复制价格常量。
- [ ] `tests/integration/decision-events.test.ts`验证一轮多调用仍一轮、重复追加同事件幂等、意图写入回滚则事件/预留也回滚、env关闭保留模型决定。此阶段禁用自动提交handler，交接PREPARED意图和事件给P05。

本阶段新增只读`scripts/probe-jev.ts`及测试，验证合法Choice/版本/usage；无凭证时CREDENTIALS_REQUIRED且网络次数0。P08复用同工具，不增加第二个Jev客户端。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm exec vitest run packages/providers/src/jev packages/domain/src/actions.test.ts packages/domain/src/decision-outcome.test.ts apps/worker/src/decision
pnpm exec vitest run tests/integration/decision-round.test.ts tests/integration/quote-decision-contract.test.ts tests/integration/decision-events.test.ts
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P04-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
