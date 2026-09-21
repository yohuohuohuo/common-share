# P01 项目基础与配置 Implementation Plan

> **For agentic workers:** 本次只执行P01。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 建立可启动、可迁移、可测试的独立工程及唯一配置/共享契约。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第1—6节；15.1、15.3—15.5的公共字段。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

金额精度和链身份；配置同轮冻结；schema幂等；事件/成本唯一键；测试库保护。

## 输入、范围与交付边界

**输入：** 无前置阶段。只使用已确认R01—R12，不从旧代码仓库继承工程。

**输出：** workspace脚本与lockfile；domain基础类型/金额/语义；Db及schema；配置CAS；生命周期与调用/成本仓储。

**不做：** 不采集真实行情，不调用Jev，不提交交易，不实现完整UI。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及已确认设计的上述相关章节。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

检查Node/pnpm/PostgreSQL开发环境；仅在明确的新产品目录初始化，不在common-share执行产品代码。

## 初始目录与类型定义归属

```text
apps/
  web/src/app/                  # 管理页面、登录和内部API
  web/src/server/               # 会话、鉴权和只读查询
  worker/src/main.ts            # 生命周期与唯一active实例
  worker/src/scheduler/         # Plus优先级、冷却、轮转
  worker/src/collectors/        # 行情、账户、KOL与钱包画像
  worker/src/decision/          # 快照、两步决策、容量分组
  worker/src/execution/         # 准备、提交、查询、未知订单对账
packages/
  domain/src/                  # 纯类型、金额、动作、状态、账务
  db/src/                      # Drizzle schema及事务仓储
  providers/src/gmgn/          # 官方HTTP、签名和字段归一化
  providers/src/jev/           # Choice构造与结果验证
prompts/decision-v1.md         # 可审计的英文模型指令
scripts/                      # seed、契约检查、只读probe、验收工具
contracts/gmgn/               # route registry、来源版本、synthetic fixtures
contracts/jev/                # 请求／响应schema与synthetic fixtures
tests/integration/            # DB、两进程互斥和故障注入
tests/e2e/                    # 管理页面端到端
docs/                         # 本计划包、接入证据、运行手册
```

```typescript
export type Chain = 'robinhood' | 'bsc' | 'sol';
export type RawAmount = string;
export type UsdCents = string;
export type Side = 'BUY' | 'SELL';
export type Quality = 'ok' | 'partial' | 'stale' | 'unavailable'
  | 'not_applicable' | 'unknown_unit';
export interface Clock { nowMs(): number; sleep(ms: number): Promise<void> }
export interface HttpRequest {
  method: 'GET' | 'POST'; url: string;
  headers: Record<string,string>; body: string | null;
}
export interface HttpReply {
  status: number; headers: Record<string,string>; bodyText: string;
}
export type HttpTransport = (request: HttpRequest) => Promise<HttpReply>;
export type Priority = 'P0' | 'P1' | 'P2' | 'P3';
export interface RouteRule {
  id: string; method: 'GET' | 'POST'; path: string;
  weight: number; signed: boolean; effect: 'READ' | 'TRADE';
}
export interface TradeConfig {
  version: number; schemaVersion: 1;
  buyAmountTiersUsdCents: UsdCents[]; sellBpsTiers: number[];
  enabledChains: Chain[]; decisionIntervalMs: number;
  trendingInterval: '5m'; trendingLimitPerChain: number;
  model: string; gmgnPlan: 'plus';
}
export interface AssetRef {
  id: string; chain: Chain; canonicalAddress: string;
  providerAddress: string; decimals: number; symbol: string;
}
```

各类型后续按设计字段表补齐，禁止把未知的原始外部响应强转为业务类型。所有跨包导出由明确的`index.ts`维护。

## P01.01：项目骨架、类型契约和官方API基线

**来源编号：** T01（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** 无。**覆盖：** R01–R03、Review Focus 1。

**文件：** 新建根`package.json`、`pnpm-workspace.yaml`、`tsconfig.base.json`、`vitest.config.ts`、`tests/setup-network.ts`；创建五个workspace的package与index；创建`packages/domain/src/contracts.ts`、`contracts/gmgn/routes.json`、`scripts/validate-api-register.ts`、`scripts/validate-api-register.test.ts`、`docs/references/upstream-lock.json`。

**接口：** `validateApiRegister(routes: RouteRule[]): string[]`，返回具体错误；根脚本`typecheck`、`lint`、`test`、`test:integration`、`test:e2e`、`build`、`dev:web`、`dev:worker`、`db:migrate`、`db:seed`。

- [ ] 记录本计划及设计到新工作目录；只在用户指定或明确新建的仓库内初始化Git。记录Node/pnpm版本，选兼容的稳定安全补丁，以exact版本安装并提交lockfile；不使用浮动latest作为部署契约。
- [ ] 编写失败测试，验证路线权重和写接口不可被标READ：

```typescript
import { expect, test } from 'vitest';
import { validateApiRegister } from './validate-api-register';
test('swap cannot be marked as a read', () => {
  const errors = validateApiRegister([{
    id:'swap', method:'POST', path:'/v1/trade/swap',
    weight:10, signed:true, effect:'READ'
  }]);
  expect(errors).toContain('swap.effect must be TRADE');
});
```

- [ ] 执行`pnpm exec vitest run scripts/validate-api-register.test.ts`，确认FAIL源于缺失校验，不是网络／环境错误。
- [ ] 从API核验记录建立路由注册表；固定官方GMGN公开仓库实际commit和文件哈希，不伪造SHA。`upstream-lock.json`保存url、commit、retrievedAt、sha256、conflicts数组。Plus权重、签名方式、quote冲突、状态映射冲突均入表。实现逐条校验：id唯一，weight为1..20整数，swap必须TRADE且signed，普通K线不启用1s。
- [ ] 建立测试外连禁用器，真实域名请求直接抛`LIVE_NETWORK_DISABLED_IN_TEST`；定义上面的基础契约、Web/Worker空入口、语法检查和包构建。
- [ ] 运行单测、typecheck和各包build；提交`chore: establish workspace and provider contract baseline`。

**验收：** 可运行最小测试；source lock有真实来源版本或明确`fetch_failed`并阻断账号验收，不会因未能联网而假定接口验证完成。


### 本阶段内联增补：共享执行语义（U01）

归属本任务；`packages/domain/src/execution-semantics.ts`是唯一类型/常量定义位置，`execution-contract.ts`定义投影与纯比较，后续阶段只能导入。采用现货 ExactIn、美元本金参考值、快照可用持仓、额外费用、无做空；提示词不规定哪个市场信号最强。

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
  chain: 'robinhood' | 'bsc' | 'sol'; accountId: string; side: 'BUY' | 'SELL';
  inputAssetId: string; outputAssetId: string;
  inputAmountRaw: string; minOutputAmountRaw: string;
  slippageBps: number; orderType: 'EXACT_IN_SWAP';
}
```

- [ ] 在`execution-contract.test.ts`先写以下失败测试。fixtures为synthetic，不是合法生产地址。

```typescript
import { expect, test } from 'vitest';
import { assertExecutionAgreement, type ExecutionProjection } from './execution-contract';
const buy: ExecutionProjection = {
  chain:'bsc',accountId:'account-bsc',side:'BUY',inputAssetId:'native:bsc',
  outputAssetId:'bsc:token-a',inputAmountRaw:'20000000000000000',
  minOutputAmountRaw:'990000',slippageBps:100,orderType:'EXACT_IN_SWAP',
};
test.each([
  {...buy,inputAmountRaw:'10000000000000000'}, {...buy,side:'SELL' as const},
  {...buy,chain:'sol' as const}, {...buy,minOutputAmountRaw:'900000'},
  {...buy,slippageBps:500},
])('rejects a mutated submission', sent => {
  expect(()=>assertExecutionAgreement(buy,buy,sent))
    .toThrow('EXECUTION_CONTRACT_MISMATCH');
});
```

- [ ] 运行`pnpm exec vitest run packages/domain/src/execution-contract.test.ts`确认失败，再实现明确字段比较：

```typescript
const keys: (keyof ExecutionProjection)[] = ['chain','accountId','side',
  'inputAssetId','outputAssetId','inputAmountRaw','minOutputAmountRaw',
  'slippageBps','orderType'];
export function assertExecutionAgreement(shown:ExecutionProjection,
  frozen:ExecutionProjection,sent:ExecutionProjection):void {
  if(keys.some(k=>shown[k]!==frozen[k] || frozen[k]!==sent[k]))
    throw new Error('EXECUTION_CONTRACT_MISMATCH');
}
```

- [ ] 增加规范化JSON hash测试，属性顺序改变不改变hash，语义字段改变必须改变hash。登记两份固定参考源码及MIT许可，不复制Bun/Effect或策略fallback。运行测试、typecheck并随本任务提交。

此处只实现供应商无关的纯契约；真实GMGN请求反向解码比较由P05.01负责，不能现在假称已验证传输一致性。

## P01.02：金额、原始数量与多链资产身份

**来源编号：** T02（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.01。**覆盖：** R03、R04、R06、R07。

**文件：** `packages/domain/src/money.ts`、`asset-id.ts`及对应`.test.ts`。

**接口：** `usdCentsToRaw(cents: UsdCents, priceUsd: string, decimals: number): RawAmount`；`sellRaw(balanceRaw: RawAmount, bps: number): RawAmount`；`assetId(chain: Chain, address: string): string`。

- [ ] 写失败测试，包含精度、100%和非法输入：

```typescript
import { expect, test } from 'vitest';
import { usdCentsToRaw, sellRaw } from './money';
test('USD notional converts using payment-asset price', () => {
  expect(usdCentsToRaw('5000','200',9)).toBe('250000000');
  expect(sellRaw('7',2500)).toBe('1');
  expect(sellRaw('7',10000)).toBe('7');
  expect(() => usdCentsToRaw('1000','0',9)).toThrow('INVALID_PRICE');
});
```

- [ ] 运行`pnpm exec vitest run packages/domain/src/money.test.ts packages/domain/src/asset-id.test.ts`确认FAIL。
- [ ] 用decimal.js或整数有理数算法实现换算，明确向下取整、price>0、decimals整数0..255、cents为正整数字符串。百分比只接受配置的合法bps，禁止Number参与资金乘除。原始地址EVM按20字节校验，Solana解码32字节且不lowercase；原生asset单独标识不混成Wrapped资产。
- [ ] 增加超大raw（大于2^53）、极小金额为0、相同EVM地址跨链不相同、Solana大小写不变、25/50/75/100四档测试；不凭正则长度接受无效base58。
- [ ] 跑测试及typecheck；提交`feat: add exact amounts and chain-qualified asset identities`。

**验收：** 10/20/50/100美元只由支付资产价格换算；未执行任何网络请求。

## P01.03：数据库schema、迁移与唯一约束

**来源编号：** T03（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.01、P01.02。**覆盖：** R09、R12。

**文件：** `packages/db/src/schema.ts`、`connection.ts`、`migrations/`；`tests/integration/db-constraints.test.ts`；`compose.dev.yml`。

**接口：** `openDb(url: string): Db`、`migrate(db: Db): Promise<void>`；Db为本项目Drizzle连接封装。测试库必须与`DATABASE_URL`不同且库名含`test`。

- [ ] 写集成失败测试，用独立测试库插入相同round的两个intent，预期数据库唯一约束拒绝；重复asset的chain+address也拒绝：

```typescript
import { expect, test } from 'vitest';
import { assertTestDatabaseUrl } from '../../packages/db/src/connection';
test('production DB is rejected by test harness', () => {
  expect(() => assertTestDatabaseUrl(
    'postgresql://local@localhost/trader',
    'postgresql://local@localhost/trader'
  )).toThrow('UNSAFE_TEST_DATABASE');
});
```

- [ ] 启动测试PostgreSQL后运行`pnpm exec vitest run tests/integration/db-constraints.test.ts`，确认约束尚未实现而失败。
- [ ] 按设计第6节建表：immutable config_versions、head、runtime、capabilities、assets、observations、walletprofiles、kol_events、jobs、workercontrol、rounds、calls、catalogs、intents、orders、fills、positions、cashflows、ledger、equity、audits、sessions。实际migration包含外键、主键和check，而不是只写TypeScript类型。
- [ ] 核心DDL逻辑如下，按Drizzle生成真实迁移：

```sql
CREATE UNIQUE INDEX one_intent_per_round ON trade_intents(round_id);
CREATE UNIQUE INDEX one_order_per_intent ON orders(intent_id);
CREATE UNIQUE INDEX unique_provider_fill ON fills(source_key);
CREATE UNIQUE INDEX unique_asset_identity ON assets(chain, canonical_address);
ALTER TABLE positions ADD CONSTRAINT nonnegative_amounts
  CHECK (quantity_raw >= 0 AND reserved_raw >= 0
    AND reserved_raw <= quantity_raw);
```

- [ ] 迁移新库、再次执行迁移、事务回滚、序列化decimal为string；重复fill唯一约束不吞掉业务差异，冲突内容不同需报错。
- [ ] 跑DB集成测试并提交`feat: persist configuration trading state and ledger`。

**验收：** 表和约束可从空库创建；迁移不自动写入真实密钥或启用交易。


### 本阶段内联增补：一次建齐跨阶段持久化基础（U04/U05/U06）

P01拥有数据库schema、迁移和下列公共仓储。P03负责查询历史，P04/P05负责生产事件，P06负责展示；后续不再重建这些表。读取主设计第6节及15.3—15.5的字段定义即可，不读旧专项执行文档。

- [ ] 增加`lifecycle_events`：`event_id`主键、`event_key`唯一、`round_id`、`intent_id/order_id/fill_id`可空、`type`、`occurred_at`、`recorded_at`、每round递增`sequence`、判别联合校验的JSON payload、`run_mode`。每事件至少关联round/intent/order之一；round内序号与业务变更同事务提交。
- [ ] 增加按资产不可变事实索引`(account_id,asset_id,recorded_at,event_id)`；保留两个时间，不能靠后来可变的`orders.status`重建过去。采用已有model/fill/audit事实，不额外发供应商请求。
- [ ] 增加`provider_attempts`及`operating_cost_entries`：attempt_id/source_key唯一；保存provider、roundId/step、attempt、排队/请求耗时nullable、usage、pricingVersion、billingPeriodStart/End、amountUsd nullable、quality(actual/estimated/unknown)、offWallet、allocationMethod、sourceEvidence、supersedes/correction关联。新数据不覆盖估算或原账单。
- [ ] 建立`packages/db/src/lifecycle-repository.ts`：`appendLifecycle(tx,event):Promise<{eventId:string;sequence:string}>`、`readTimeline(db,{roundId,afterSequence,limit}):Promise<TimelinePage>`；limit=1..100，游标只适用于该round。`TimelinePage={events:LifecycleEvent[],nextSequence:string|null}`。`LifecycleEvent`含上述字段并用显式类型验证payload；数据库事务类型与`Db`在connection模块导出。
- [ ] 建立`packages/db/src/operating-costs-repository.ts`，导出`recordProviderAttempt(db,attempt):Promise<void>`及`recordOperatingCost(db,entry):Promise<void>`；完整`ProviderAttempt/OperatingCostEntry`由该模块按以上字段导出，不引入未定义业务类型。
- [ ] `tests/integration/lifecycle-storage.test.ts`验证同event_key重复同payload只返回已有序号，不同payload抛冲突；业务回滚不留下事件。`tests/integration/cost-storage.test.ts`验证同source_key不同金额拒绝、unknown金额保持null、估算和结算关联可追踪。
- [ ] 生命周期类型覆盖`SNAPSHOT_SAVED/MODEL_A_COMPLETED/QUOTES_READY/MODEL_B_COMPLETED/ROUND_COMPLETED/INTENT_CREATED/EXECUTION_BLOCKED/SUBMIT_ATTEMPTED/SUBMISSION_UNKNOWN/ORDER_ACCEPTED/ORDER_CONFIRMED/FILL_RECORDED/LEDGER_POSTED/EXECUTION_FAILED/MODEL_A_ERROR/MODEL_B_ERROR`，分组调用作为模型调用明细而不是额外轮数。

```sql
CREATE UNIQUE INDEX one_event_key ON lifecycle_events(event_key);
CREATE UNIQUE INDEX one_round_sequence ON lifecycle_events(round_id, sequence);
CREATE UNIQUE INDEX one_cost_source ON operating_cost_entries(source_key);
CREATE UNIQUE INDEX one_provider_attempt ON provider_attempts(attempt_id);
```

这些增补随同本任务迁移、测试和提交完成；不等待后续实现再补关键存储约束。

## P01.04：数据库配置、版本快照和暂停控制

**来源编号：** T04（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.03。**覆盖：** R06、R07、R09、R10，Review Focus 2。

**文件：** `packages/domain/src/config.ts`、`packages/domain/src/config.test.ts`、`packages/db/src/config-repository.ts`、`runtime-repository.ts`、`scripts/seed.ts`；`tests/integration/config.test.ts`。

**接口：** `validateConfig(input: unknown): TradeConfig`；`seedConfig(db): Promise<void>`；`updateConfig(db,{expectedVersion,patch,actor}): Promise<TradeConfig>`；`setPaused(db,paused,actor): Promise<{revision:number}>`。

- [ ] 写测试覆盖初始化幂等、两个管理员同时更新导致一个409和金额正值：

```typescript
import { expect, test } from 'vitest';
import { normalizeBuyTiers } from './config';
test('USD tiers are positive unique cents', () => {
  expect(normalizeBuyTiers(['1000','2000','5000','10000']))
    .toEqual(['1000','2000','5000','10000']);
  expect(() => normalizeBuyTiers(['1000','1000'])).toThrow('DUPLICATE_TIER');
  expect(() => normalizeBuyTiers(['0'])).toThrow('INVALID_TIER');
});
```

- [ ] 运行相应domain测试和`tests/integration/config.test.ts`确认FAIL。
- [ ] `normalizeBuyTiers`校验整数美分字符串、正值、去重前拒绝重复、稳定递增；sell档位合法bps且非空，选项容量和参数schema受校验。不可变新版本在同一事务插入，再CAS更新head，失败整体回滚。保存before/after hash及actor。
- [ ] seed仅`ON CONFLICT DO NOTHING`，不每启动重置；业务配置没有env覆盖层。runtime pause单独表，revision用于提交前撤销检查，页面保存金额不等同紧急暂停。
- [ ] 测试“V1第二档20美元，更新V2第二档30美元，V1轮仍保留20美元”；DB读取失败明确抛错，不fallback环境默认值。
- [ ] 测试通过后提交`feat: version database-backed trading configuration`。

**验收：** 业务配置在数据库有唯一来源，默认paused且各链未就绪。


### 历史配置归属（U04）

- [ ] 本任务新增版本化配置`assetHistoryLookbackDays=30`（1..365）和`assetHistoryLimit=3`（0..20）。配置升级只补缺省字段，不覆盖用户金额档位。historyLimit=0合法且表示关闭查询；不向要求正limit的纯选择函数传0。
- [ ] 配置测试补充historyLimit 0合法、负数/21非法、配置迁移后原买入档位不变；在交接中记录完整TradeConfig导出路径及schema版本。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm exec vitest run packages/domain scripts/validate-api-register.test.ts
pnpm exec vitest run tests/integration/db-constraints.test.ts tests/integration/config.test.ts tests/integration/lifecycle-storage.test.ts tests/integration/cost-storage.test.ts
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P01-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
