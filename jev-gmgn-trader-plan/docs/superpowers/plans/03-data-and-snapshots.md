# P03 数据采集与决策快照 Implementation Plan

> **For agentic workers:** 本次只执行P03。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 通过同一运行骨架持续采集三链事实，生成固定配置和双时间截止的可回放快照。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第3节、7节、9.2及15.3；持仓相关第5节。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

unknown与0；交易事件不按hash误去重；持仓分页失败不清零；历史不泄漏后来数据；大快照不丢managed持仓。

## 输入、范围与交付边界

**输入：** P02 GmgnClient/schedule/HandlerRegistry，P01 Db及不可变事实表，配置和资产ID/金额函数。

**输出：** collectMarket/refreshWalletProfiles/syncAccount；normalizeCandle/normalizeAttention；DecisionState/PackedState；按资产历史查询与event IDs。

**不做：** 不做模型决策、不提交交易、不以缺标签/低指标过滤候选、不创建向量库。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及`docs/execution/P02-handoff.md`和其中指定的已存在接口。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

```bash
pnpm typecheck
pnpm exec vitest run apps/worker/src/scheduler tests/integration/worker-bootstrap.test.ts
```
前置P02未通过本地验收时，不开始本阶段；外部账号NOT_RUN不是本地代码阶段的自动阻塞。

## P03.01：行情适配、采集缓存和数据质量

**来源编号：** T07（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P02.01、P02.02。**覆盖：** R02、R03、R08，Review Focus 1。

**文件：** `packages/providers/src/gmgn/{market,token,normalization}.ts`；`apps/worker/src/collectors/market.ts`；`packages/db/src/observations-repository.ts`及测试。

**接口：** `normalizeCandle(raw:unknown,mapping:CandleUnitMapping): NormalizedCandle`；`normalizeToken(raw:unknown): TokenObservation`；`collectMarket(chain:Chain,config:TradeConfig):Promise<void>`。`CandleUnitMapping`取`unknown`或明确tokenVolumeField/usdVolumeField和sourceVersion；NormalizedCandle包含USD OHLC、timeMs、两种volume Evidence及原始字段。

- [ ] 写未知单位和null／0区分测试：

```typescript
import { expect, test } from 'vitest';
import { normalizeCandle } from './normalization';
test('conflicting volume definitions remain unknown', () => {
  const c=normalizeCandle({time:1,open:'1',high:'2',low:'1',close:'2',
    volume:'5000',amount:'10'}, {mode:'unknown'});
  expect(c.timeMs).toBe(1000);
  expect(c.volumeUsd.value).toBeNull();
  expect(c.volumeUsd.quality).toBe('unknown_unit');
  expect(c.rawVolume).toBe('5000');
});
```

- [ ] 跑normalization测试确认FAIL；测试fixture明确synthetic。
- [ ] 依路由字段映射整理Token info、安全、池、热榜、K线，来源时间与采集时间分开；UI百分比和ratio不同单位，不按数值范围猜。价格异常及缺失精度为不可计算事实，不给默认1美元。
- [ ] collectors按设计预算错峰调度，数据库resource缓存／观测不可变记录；市场入池不使用not_risk等主动过滤，记录实际传参和providerFilterStatus。历史K线排序、去重、标记未闭合，缺少区间记录gap。
- [ ] 测试三链相同字段缺失、接口空列表与401不同、429不掩盖、partial数据不被当成安全；观察集合不能因没K线或没KOL被剔除。
- [ ] 测试通过提交`feat: normalize market evidence without hidden strategy filters`。

**验收：** 核验记录中的K线歧义没有变成静默错误的USD成交量。

## P03.02：KOL行为、钱包关注度与采集覆盖

**来源编号：** T08（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P02.02、P03.01。**覆盖：** R08，Review Focus 4。

**文件：** `packages/providers/src/gmgn/{wallet-stats,kol}.ts`；`apps/worker/src/collectors/{wallet-profiles,kol-events}.ts`；`packages/domain/src/wallet-attention.ts`及测试。

**接口：** `normalizeAttention(raw:unknown): WalletAttention`；`eventKey(event:NormalizedTradeEvent):string`；`refreshWalletProfiles(keys:WalletKey[]):Promise<void>`。WalletAttention三个nullable计数与source／observedAt，WalletKey含chain/address；NormalizedTradeEvent含chain、transactionHash、logIndex或providerEventId、wallet、assetId、side、rawAmount、timeMs。

- [ ] 写计数区分与缺失测试：

```typescript
import { expect, test } from 'vitest';
import { normalizeAttention } from './wallet-stats';
test('GMGN attention is distinct from X followers', () => {
  const a=normalizeAttention({common:{follow_count:123,
    remark_count:45,followers_count:678}});
  expect(a.gmgnFollowCount).toBe(123);
  expect(a.gmgnRemarkCount).toBe(45);
  expect(a.xFollowerCount).toBe(678);
  expect(normalizeAttention({}).gmgnFollowCount).toBeNull();
});
```

- [ ] 跑wallet-stats和事件键测试确认FAIL。
- [ ] 将普通holders/traders、renowned标签和KOL流中的wallet纳入按链去重队列；每个用户钱包Stats只用官方字段，不自动把Twitter handle当已验证真实身份。10分钟cache TTL不保证10分钟刷新完；按轮转队列、10次stats请求/分钟节流并记录最旧age。
- [ ] 一个tx中的不同event不得合并；若无event index，用provider ID，仍没有则用完整事实hash并标低确定性。重复KOL流轮询采用时间窗口重叠和事件唯一键；看到窗口边界超过历史覆盖则标gap，不捏造完整5分钟净流。
- [ ] 提供wallet样本计数、返回条数／limit、观察窗口、truncated和source；从未见卖出仅显示not_observed。转账事件不算买卖；不把follow_count之和称独立受众，不算车头综合分。
- [ ] 测试多币共享wallet缓存、相同EVM地址不同链不合并余额、无common不转0、冷却时缓存stale可见；提交`feat: add attributable KOL and wallet-attention evidence`。

**验收：** 模型能看到关注度与真实参与行为及其覆盖限制，不会获得未来源化的“车头定论”。

## P03.03：真实账户同步、完整持仓与就绪检查

**来源编号：** T09（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.03、P02.01、P02.02、P03.01。**覆盖：** R03、R04、R12，Review Focus 5。

**文件：** `apps/worker/src/collectors/accounts.ts`；`packages/providers/src/gmgn/portfolio.ts`；`packages/db/src/{accounts,positions}-repository.ts`；`packages/domain/src/universe.ts`及测试。

**接口：** `syncAccount(accountId:string):Promise<AccountSnapshot>`；`mergeUniverse(candidateIds:string[],managedIds:string[]):string[]`；`checkReadiness(account:ChainAccount,evidence:CapabilityEvidence[]):ReadinessResult`。

- [ ] 写掉榜仍保留测试：

```typescript
import { expect, test } from 'vitest';
import { mergeUniverse } from './universe';
test('all managed holdings survive removal from trending', () => {
  expect(mergeUniverse(['sol:A','bsc:B'],['sol:OLD','sol:A']))
    .toEqual(['bsc:B','sol:A','sol:OLD']);
});
```

- [ ] 测试签名持仓请求与全部分页；第一页20条、第21条是managed持仓，必须保留，原始`next`缺失与页面空列表不同；失败分页不得清零未见持仓。
- [ ] 实现按cursor连续读取、循环cursor检测、page失败标partial；同步支付资产和gas余额；对本地managed未见资产再查token-balance确认，不仅靠上游列表认定清仓。
- [ ] 首次导入已存在资产cost=null、managed=false，UI显示待归属；本项目成交资产managed=true。外部余额变动登记待对账事件，不自动归为盈利或自动卖空投。
- [ ] 三链readiness包含钱包绑定、网络、原生/支付资产API表示与decimals、签名、关键余额及quote权限。支持声明与verified分开；链disabled也不遗忘其未解决订单和managed持仓的读取。
- [ ] 跑集成测试后提交`feat: reconcile multichain accounts without dropping holdings`。

**验收：** 缺失分页和接口失败不使资产消失；未就绪网络不能创建可执行意图。


### 本阶段内联增补：不完整持仓证据（U03）

新建`packages/domain/src/holdings-reconciliation.ts`及同名测试；`applyBalanceEvidence(previousRaw,evidence):string`只有在独立验证余额时覆盖旧值。

```typescript
import {expect,test} from 'vitest';
import {applyBalanceEvidence} from './holdings-reconciliation';
test.each(['timeout','page_2_failed','repeated_cursor','partial_empty'])
('keeps a managed holding on %s',reason=>{
  expect(applyBalanceEvidence('1000',{kind:'incomplete',reason})).toBe('1000');
});
test('accepts independently verified zero',()=>{
  expect(applyBalanceEvidence('1000',{kind:'verified_balance',raw:'0'})).toBe('0');
});
```

- [ ] 运行同名测试确认失败，再实现`incomplete`保持旧数量、外层标partial；`verified_balance.raw`必须是非负整数字符串。该纯函数不能代替真实collector集成验证。
- [ ] 在`tests/integration/account-sync.test.ts`使用真实collector＋假transport覆盖第二页失败、重复cursor、空但partial、掉榜、无安全/KOL标签。断言managed持仓保留在数据库和下一轮观察集合；SELL资格不因缺少标签消失。
- [ ] P03只记录已确认余额及对账差异，不虚构成交或成本；P05负责交易导致的position/ledger事务。交接必须列出分页完整度、readiness和待核实字段。

## P03.04：可回放快照、摘要压缩和覆盖字段

**来源编号：** T10（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.04、P03.01、P03.02、P03.03。**覆盖：** R08、R09。

**文件：** `apps/worker/src/decision/{snapshot,packing}.ts`；`packages/domain/src/decision-state.ts`；`packages/db/src/rounds-repository.ts`及测试。

**接口：** `buildSnapshot(input:SnapshotInputs):DecisionState`；`packSnapshot(state:DecisionState,budget:InputBudget):PackedState`；`saveRoundSnapshot(db,state):Promise<{id:string;hash:string}>`。

- [ ] 写快照不可变、保留缺失和钱包去重引用测试。InputBudget含maxEstimatedTokens、estimatorVersion、maxAssetsPerGroup；PackedState含state、estimatedTokens、estimationMethod、compressionLog、groupsNeeded。
- [ ] 运行`pnpm exec vitest run apps/worker/src/decision/snapshot.test.ts apps/worker/src/decision/packing.test.ts`确认FAIL。
- [ ] 实现配置和账户一致性快照，所有量价带时间来源；input includes all managed positions。共享wallet dictionary只存一份画像，token记录ref；全局历史最多10轮，另加增补U04按资产30天/3条摘要及覆盖；K线最多12根。保留unit dictionary、missing理由和估算token方法。
- [ ] 具体压缩顺序写成数据算法，不按收益筛选：

```text
1. 共享重复wallet画像和单位字典；删除重复展示文本。
2. 历史快照10→5→2，K线12→6；保留覆盖信息。
3. 第一层只保留每币核心摘要，完整详情存数据库并对选中币补入B。
4. 仍超容量则groupsNeeded=true，交P04.01分组复选，不自行删除候选。
```

- [ ] 对synthetic state做JSON序列化→反序列化→hash相同测试；配置更新不改变已保存快照；压缩后每个managed position仍有ID和必要摘要。不存在官方tokenizer时不声称精确token数，provider超限返回明确错误。
- [ ] 提交`feat: build immutable bounded decision snapshots`。

**验收：** 每个模型结果能追溯其实际输入，不仅能看到“用了哪些接口”。

### 本阶段内联增补：按资产检索历史事实


**文件：** 新建`packages/domain/src/asset-history.ts`及测试、`packages/db/src/asset-history-repository.ts`、`tests/integration/asset-history.test.ts`；本阶段修改snapshot/packing并复用P01索引；P04负责sizing读取同一cutoff，P06负责页面来源展示。

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
- [ ] A默认每asset过去30天最多3摘要；交接给P04的约束：B只展开相同截止点同一组记录。使用P01已建立的版本化配置`assetHistoryLookbackDays=30`和`assetHistoryLimit=3`，范围1..365天与0..20条；本阶段不重建配置schema、不覆盖金额档位。
- [ ] pack将每资产历史3→1→0后仍保留asset ID、持仓和coverage；全局历史与资产历史同eventId使用引用，不能重复计数。缺历史返回空列表、unknown成本保持null，不生成“好/坏钱包”结论。
- [ ] 集成测试晚到确认、前一轮亏损但仍允许本轮BUY、历史读取不产生GMGN/Jev额外调用、跨链同地址不混记录；B引用A的cutoff在P04测试，页面来源在P06测试。提交`feat: add bounded asset-scoped decision history`。

**验收：** 只增强Jev可见事实；不建立向量库、收益筛选、历史回测对照组或自主训练机制。

P03须把collector注册到P02已有Worker测试运行骨架，并扩展`probe-gmgn`字段映射检查。生产自动决策尚未接线，不提前读取P04全计划。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm exec vitest run packages/providers/src/gmgn packages/domain/src/asset-history.test.ts packages/domain/src/holdings-reconciliation.test.ts apps/worker/src/decision/snapshot.test.ts apps/worker/src/decision/packing.test.ts
pnpm exec vitest run tests/integration/account-sync.test.ts tests/integration/asset-history.test.ts
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P03-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
