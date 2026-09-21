# Jev × GMGN 多链交易实验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（环境可用时）或 superpowers:executing-plans，逐项实施；以下使用 `- [ ]` 跟踪。尚未获用户实施授权前，只审阅文档，不执行产品代码或交易。

**Goal:** 交付支持 Robinhood、BSC、Solana 的 Jev 自主决策交易应用，包含 GMGN Plus 采集、10／20／50／100 USD 买入档位、25／50／75／100% 卖出、管理页面、真实成交与账本闭环。

**Architecture:** Next.js 管理页面与服务端 API，单 active Node.js Worker，PostgreSQL 持久化。所有 GMGN 调用共用按凭证归集的权重调度，两个顺序 Jev Choice 产生一个最终动作，独立执行器只执行已经冻结的交易意图。

**Tech Stack:** Node.js 24 LTS、pnpm workspace、TypeScript strict、Next.js App Router、React、Tailwind CSS、SWR、Drizzle、PostgreSQL、Zod、decimal.js、lossless-json、Vitest、Playwright、Docker Compose。具体兼容补丁版本在 T01 核验并以 exact versions 和 lockfile 固定，不将本文视为未经验证的依赖清单。

**Spec:** `docs/superpowers/specs/2026-09-21-jev-gmgn-trader-design.md`。

**Evidence:** `docs/references/2026-09-21-api-evidence.md`。文中的 Sxx 均引用该记录。

**Status:** R2文档修订；按用户同意纳入参考项目评审，所有产品实施步骤仍未执行。本计划既不是测试报告，也不授权调用真实Swap。计划存放于common-share，产品仍在独立新项目实施。

**Mandatory supplement:** [参考项目评审专项实施清单](2026-09-21-reference-review-implementation.md)。U01—U06是T01—T22的必做扩展，不是可选建议；按该清单的任务映射同步完成。D01/SSE仅列后续增强。

**Reference evidence:** [固定提交源码及采用边界](../../references/2026-09-21-reference-project-review.md)。

## Global Constraints

- 首批链 `robinhood`、`bsc`、`sol`；各链预存资金，不自动跨链调拨。
- GMGN 官方 API，按 Plus `rate=20, capacity=20` 的权重限制设计；本地总预算16 weight/s、背景预算10 weight/s、突发容量20。
- 一轮全局最多一个最终 Swap；允许 WAIT／ABSTAIN，两个模型步骤不等于两笔交易。
- `buyAmountTiersUsdCents=["1000","2000","5000","10000"]`；`sellBpsTiers=[2500,5000,7500,10000]`，数据库是唯一业务配置来源。
- 同一轮使用同一配置版本；金额与比例都冻结为原始输入数量；不擅自降档。共享ExecutionSemantics贯穿提示词、报价、动作与提交，语义不一致拒单。
- 默认 `TRADING_ENABLED=false`，管理页面不能越权启用；调用侧必须再次检查，不只在UI隐藏按钮。
- 不添加选币指标阈值、置信度门槛、固定止盈止损、自动跟单、对照组或其他LLM。
- 量价时间字段精确归一化；未知≠0；数据单位冲突不得猜；上游标签不当作真理。
- 不把wallet追踪／备注数当X粉丝数，不把转入当买入，不把多个wallet计成独立人数。
- 所有managed持仓持续监控，不因掉榜或上游分页而消失；按代币历史仅取同账户/资产且在本轮cutoff前已知的不可变事实。
- 提交≠成交；未知结果不自动重发；鉴权client_id不是已确认的订单幂等键。
- 用户文档和页面中文，代码注释可英文；新建独立项目，不覆盖现有Robinhood仓库。
- 不新增Redis、微服务、桥接、公开注册或任意交易控制台；所有测试默认阻断真实供应商写入。

## Review Focus

1. GMGN文档与实际响应不一致（K线单位、quote鉴权、成功状态）：T05/T07/T15/T22必须验证原始响应并保留未知状态。
2. 两步骤之间配置、余额或暂停状态改变：T04/T12/T14必须固定原始数量并在提交前重新授权，不能按新档位解释旧选择。
3. Swap已被接受但响应丢失、进程重启或DB写入失败：T14/T15/T19验证不重发，未知订单阻塞新的可执行意图。
4. Plus请求被三链、画像、页面刷新一起用满：T06/T08/T19/T20验证共享预算、429全局冷却和P0优先，签名在排队后生成。
5. 掉榜持仓、分页遗漏、外部入金、未知成本和重复fill：T09/T16/T18/T20验证资产不被遗漏且账本不虚增利润。

## 0. 实施方式和统一约定

按 T01→T22 顺序推进；表中的依赖通过后才能开始对应任务。每个任务先写失败测试，记录失败原因，再做最小实现，运行测试并独立提交。纯文档更新也通过链接／配置检查，不用“看起来正确”代替证据。完成每项任务前，同时核对专项清单中归属该任务的U项；T20汇总U01—U06全部回归。下文代码为计划中的目标测试和算法契约，不代表本轮已经创建或运行产品代码。

单元测试统一在仓库根执行：`pnpm exec vitest run <文件>`。数据库测试使用 `DATABASE_URL_TEST` 指向独立测试库，不接受生产数据库。UI测试执行 `pnpm exec playwright test <文件>`。一切fixture标记为synthetic，不能充当真实API回包。

测试网络策略：Vitest设置中阻断所有非loopback外连；供应商使用依赖注入transport或本地假服务。Playwright本地端到端不能通过浏览器或Node后台访问生产GMGN。`TRADING_ENABLED=true`只可在本地fake transport的隔离进程测试；真实验收另见T22。

### 0.1 目录和文件责任

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

### 0.2 基础类型（T01负责定义）

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

---

## T01：项目骨架、类型契约和官方API基线

**R2必做扩展：** 定义共享ExecutionSemantics及规范化hash；登记参考源码固定提交和许可；采用边界见专项U01，不能复制其他项目的执行假设。

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

## T02：金额、原始数量与多链资产身份

**依赖：** T01。**覆盖：** R03、R04、R06、R07。

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

## T03：数据库schema、迁移与唯一约束

**R2必做扩展：** 同批迁移新增lifecycle_events、operating_cost_entries及按资产历史索引；加入事件幂等与成本source_key约束，字段定义见专项U04—U06。

**依赖：** T01、T02。**覆盖：** R09、R12。

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

## T04：数据库配置、版本快照和暂停控制

**依赖：** T03。**覆盖：** R06、R07、R09、R10，Review Focus 2。

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

## T05：GMGN HTTP客户端、签名和错误契约

**依赖：** T01、T02。**覆盖：** R02、R03、R10，Review Focus 1。

**文件：** `packages/providers/src/gmgn/{client,signing,errors,schemas}.ts`及测试；`contracts/gmgn/fixtures/`。

**接口：** `prepareGmgnRequest(route,query,body,credentials,authContext): HttpRequest`；`GmgnClient.call<T>(request: GmgnRequest, decoder: (raw:unknown)=>T): Promise<T>`；`GmgnRequest`明确routeId、query、body、priority、resourceKey，除原始网络层以外不接受任意URL。

- [ ] 用本地临时测试密钥写签名验证测试，key只在测试内生成，不打印。构造数组query、含空格/中文值、空GET body及JSON体，保证签名串和实际发送字节相同：

```typescript
import { expect, test } from 'vitest';
import { canonicalQuery } from './signing';
test('repeated array values are encoded and sorted', () => {
  expect(canonicalQuery({z:'a b', wallet_address:['B','A'], timestamp:1}))
    .toBe('timestamp=1&wallet_address=A&wallet_address=B&z=a%20b');
});
```

- [ ] 运行`pnpm exec vitest run packages/providers/src/gmgn/signing.test.ts`确认FAIL。
- [ ] 根据锁定官方signer重写小范围兼容实现：排序编码query，签名正文为path／query／原样body／timestamp以冒号连接；Ed25519签名、Base64响应头。timestamp秒、独立请求ID，排队后生成；不称其订单幂等ID。[S07、S08]
- [ ] 默认API host固定allowlist；所有网络和body长度有上限；先保存脱敏原始响应，再用lossless解析及Zod验证。错误区分HTTP、鉴权、429、业务失败、解析错误和网络结果未知。禁止默认retry整个`call`，尤其POST Swap。
- [ ] 注册持仓和query_order为signed；quote的鉴权由T22只读probe配置，不因401循环升级权限。敏感headers只存hash/字段名，禁止完整curl日志。
- [ ] 测试实际public-key verify成功、JSON改变1字节失败、UTC秒单位、过期签名、未知状态未被映射为成功；通过后提交`feat: implement audited GMGN transport and signing`。

**验收：** 只发送注册过的官方路由；鉴权查询能力和交易提交开关相互独立。

## T06：Plus全局权重调度与冷却

**R2必做扩展：** 增加GMGN/Jev独立冷却回归和阶段排队计量，冷却期间network call count不变；见专项U03/U06。

**依赖：** T03、T05。**覆盖：** R02，Review Focus 4。

**文件：** `apps/worker/src/scheduler/{weighted-budget,priority-queue,cooldown}.ts`、`packages/db/src/provider-state-repository.ts`及测试。

**接口：** `WeightedBudget({rate,capacity,clock})`，方法`tryTake(weight):boolean`和`delayMs(weight):number`；`schedule(call:GmgnRequest):Promise<unknown>`；`recordCooldown(untilMs,reason):Promise<void>`。

- [ ] 使用虚拟时钟测试cap和权重，不用真实sleep：

```typescript
import { expect, test } from 'vitest';
import { WeightedBudget } from './weighted-budget';
test('weight ten is not a weight-one request', () => {
  let now=0;
  const clock={nowMs:()=>now,sleep:async(ms:number)=>{now+=ms;}};
  const bucket=new WeightedBudget({rate:16,capacity:20,clock});
  expect(bucket.tryTake(10)).toBe(true);
  expect(bucket.tryTake(10)).toBe(true);
  expect(bucket.tryTake(1)).toBe(false);
  now=625;
  expect(bucket.tryTake(10)).toBe(true);
});
```

- [ ] 跑`pnpm exec vitest run apps/worker/src/scheduler`确认FAIL。
- [ ] 实现按elapsed补充、上限capacity、拒绝weight>capacity；所有读写共享total桶，P2/P3另受background桶10/s。并发4仅是第二道资源限制，不取代weight。P0先于背景，链内与同级轮转，过期作业取消并合并同resourceKey。类本身允许初始tokens参数以便测试；生产启动／接管必须initialTokens=0，避免重启刷新突发额度，clock回拨不能补充tokens。
- [ ] permit授予后才让T05生成时间戳和签名；请求排队60秒不得产生旧签名。429从header/body提取较晚合法reset时间，持久化全Key冷却；cooldown中P0也不请求。
- [ ] 测试Web刷新+三链任务只共享一个桶；额外Key不允许绕过；restart读取cooldown且bucket从0恢复；单调时钟回拨不补充；错误时间戳fallback5–60秒；恢复单读探针。对429的Swap不自动再POST。
- [ ] 跑虚拟时钟负载测试并提交`feat: enforce shared GMGN Plus weighted scheduling`。

**验收：** 时间窗口内发出的权重满足保守桶约束，而非仅平均值；有冷却和每路由计量。

## T07：行情适配、采集缓存和数据质量

**依赖：** T05、T06。**覆盖：** R02、R03、R08，Review Focus 1。

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

## T08：KOL行为、钱包关注度与采集覆盖

**依赖：** T06、T07。**覆盖：** R08，Review Focus 4。

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

## T09：真实账户同步、完整持仓与就绪检查

**R2必做扩展：** 执行专项U03的timeout、第二页失败、重复cursor及掉榜/无KOL参数化回归；不能以缺失数据清零或跳过managed持仓。

**依赖：** T03、T05、T06、T07。**覆盖：** R03、R04、R12，Review Focus 5。

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

## T10：可回放快照、摘要压缩和覆盖字段

**R2必做扩展：** 实现专项U04的本地按资产历史查询、cutoff防未来泄漏和3→1→0压缩；不新增GMGN请求。DecisionState加入assetHistory及executionSemantics。assetHistoryLimit=0表示关闭历史查询，由上层直接返回空entries及coverage，不向要求正limit的选择函数传0。

**依赖：** T04、T07、T08、T09。**覆盖：** R08、R09。

**文件：** `apps/worker/src/decision/{snapshot,packing}.ts`；`packages/domain/src/decision-state.ts`；`packages/db/src/rounds-repository.ts`及测试。

**接口：** `buildSnapshot(input:SnapshotInputs):DecisionState`；`packSnapshot(state:DecisionState,budget:InputBudget):PackedState`；`saveRoundSnapshot(db,state):Promise<{id:string;hash:string}>`。

- [ ] 写快照不可变、保留缺失和钱包去重引用测试。InputBudget含maxEstimatedTokens、estimatorVersion、maxAssetsPerGroup；PackedState含state、estimatedTokens、estimationMethod、compressionLog、groupsNeeded。
- [ ] 运行`pnpm exec vitest run apps/worker/src/decision/snapshot.test.ts apps/worker/src/decision/packing.test.ts`确认FAIL。
- [ ] 实现配置和账户一致性快照，所有量价带时间来源；input includes all managed positions。共享wallet dictionary只存一份画像，token记录ref；全局历史最多10轮，另加专项U04按资产30天/3条摘要及覆盖；K线最多12根。保留unit dictionary、missing理由和估算token方法。
- [ ] 具体压缩顺序写成数据算法，不按收益筛选：

```text
1. 共享重复wallet画像和单位字典；删除重复展示文本。
2. 历史快照10→5→2，K线12→6；保留覆盖信息。
3. 第一层只保留每币核心摘要，完整详情存数据库并对选中币补入B。
4. 仍超容量则groupsNeeded=true，交T11分组复选，不自行删除候选。
```

- [ ] 对synthetic state做JSON序列化→反序列化→hash相同测试；配置更新不改变已保存快照；压缩后每个managed position仍有ID和必要摘要。不存在官方tokenizer时不声称精确token数，provider超限返回明确错误。
- [ ] 提交`feat: build immutable bounded decision snapshots`。

**验收：** 每个模型结果能追溯其实际输入，不仅能看到“用了哪些接口”。

## T11：Jev Choice客户端、结果验证和容量复选

**R2必做扩展：** 执行专项U01/U02：模型请求携带共享语义，原始选择不可变，失败为DECISION_ERROR而非WAIT/规则fallback；记录各次调用usage及成本质量。

**依赖：** T01、T10。**覆盖：** R05、R11。

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

## T12：四档报价、第二步金额选择和动作冻结

**R2必做扩展：** 执行专项U01：四档展示/冻结/提交一致；报价刷新改变条件必须重新经B确认，受本轮deadline约束；B历史沿用A的cutoff。

**依赖：** T02、T06、T09、T11。**覆盖：** R05–R07，Review Focus 2。

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
- [ ] 只有一级选中的asset请求四档quote，每次权重10通过T06；记录报价时间、输入/输出/最小输出、实际费用证据和unsupported原因；不做60×4全候选报价。原生价格source/precision来自能力验证，不能USD默认1。
- [ ] 四档quote共享同一个账户/config版本；超过TTL只允许一次fresh quote补齐，仍过期本轮明确结束，不循环报价直至成功。第二步把direction和原快照、更新事实一起提供，最多四档+WAIT+ABSTAIN。
- [ ] 使用ExactIn raw冻结action，100%卖出无动态percent；选项ID与catalog关联不可篡改；重复raw档合并但留原档别名。模型选择unknown ID抛错，不生成金额。
- [ ] 测试配置从20改30但旧action仍20、stageB可WAIT、模型耗时超过TTL不提交；提交`feat: let Jev select quoted USD and sell-percentage tiers`。

**验收：** 全局单动作与两次模型调用一致，费用单独预留，执行器不会改Jev金额。

## T13：决策轮编排与唯一交易意图

**R2必做扩展：** 按专项U05写持久化生命周期事件；两步/分组调用不多计决策轮；按U06记录阶段耗时，不把并行耗时相加冒充端到端。

**依赖：** T10–T12、T03、T04。**覆盖：** R05、R09、R12。

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

## T14：实盘闸门、持久化提交与资金预留

**R2必做扩展：** 执行专项U01/U02/U03的请求解码比较、BUY不得改SELL/降档及提交后DB失败测试；执行器不得回写model_calls。

**依赖：** T03、T04、T05、T06、T13。**覆盖：** R10–R12，Review Focus 2/3。

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

## T15：订单状态映射、未知提交和重启对账

**R2必做扩展：** 恢复与poll遵循专项U03/U05：unknown不可重复POST，事件幂等，确认追加不覆盖原提交时间；Jev故障不停止已有订单核对。

**依赖：** T14、T09。**覆盖：** R12，Review Focus 1/3。

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

## T16：成交落账、成本、费用和账户净值

**R2必做扩展：** 实现专项U06三种结果口径与成本覆盖；未知成本保留null，模型实际usage计费估算和GMGN实际账单分别管理，不按weight造美元价格。

**依赖：** T03、T09、T15。**覆盖：** R12，Review Focus 5。

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

## T17：管理员鉴权与内部API

**R2必做扩展：** 增加鉴权的生命周期分页查询、阶段统计和运行成本查询/人工账单登记API，见专项U05/U06；GET不调用上游，录入有审计。

**依赖：** T03、T04、T09、T13、T15、T16。**覆盖：** R01、R09、R10。

**文件：** `apps/web/src/server/{auth,csrf,queries}.ts`；`apps/web/src/app/api/`对应设计第12节路由；`packages/db/src/sessions-repository.ts`；`scripts/hash-admin-password.ts`；`tests/integration/admin-api.test.ts`。

**接口：** `requireAdmin(request):Promise<AdminSession>`；`verifyMutationOrigin(request,appOrigin):void`；配置更新API接收`{expectedVersion,patch}`；刷新请求只接受已登记jobType/resourceId，返回202 jobId。

- [ ] 写未登录401、错误Origin403、过期session401、合法配置修改审计和过期version409测试。
- [ ] 运行`pnpm exec vitest run tests/integration/admin-api.test.ts`确认FAIL。
- [ ] 实现单管理员password-hash校验、随机256bit token只存hash、生产Secure+HttpOnly+SameSite cookie、8小时session有效期、登录失败限频和注销撤销。密码初始化脚本从交互stdin读入、不回显，不接受命令行明文密码。
- [ ] 所有GET只读DB；POST写config/job/runtime而非直接调用GMGN。任何响应不包含GMGN/Jev密钥、数据库连接、签名header、服务端环境全量。Web不导入gmgn signing。
- [ ] 只读system返回**worker实际报告的**envEnabled和heartbeat；不能用Web进程的环境变量推断worker实盘状态。暂停与T14临界区同步，恢复不能改TRADING_ENABLED。
- [ ] Origin严格匹配APP_ORIGIN；URL/任务参数allowlist、请求大小限制；接口中的decimal保持string。测试通过后提交`feat: add authenticated admin APIs with server-side trade boundaries`。

**验收：** 管理页面能控制配置和暂停，但不能越过env或直接构造任意交易。

## T18：完整管理页面

**R2必做扩展：** 完成专项U04—U06历史来源、不可变模型动作/执行结果并列、事件时间线、耗时和成本页面测试；第一版DB+SWR，SSE非必做。

**依赖：** T17。**覆盖：** R01、R08–R10、R12。

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

## T19：Worker生命周期、任务恢复和统一调度接线

**R2必做扩展：** 重启恢复同时恢复独立供应商冷却、事件顺序和未决订单；执行专项U03的无重复发送与U05的可重建时间线测试。

**依赖：** T06–T18。**覆盖：** R01、R02、R12，Review Focus 3/4。

**文件：** `apps/worker/src/{main,bootstrap,health}.ts`、`scheduler/dispatch.ts`；`packages/db/src/{jobs,worker}-repository.ts`；`tests/integration/worker-lifecycle.test.ts`。

**接口：** `startWorker({db,transport,clock,env}):Promise<WorkerHandle>`；`WorkerHandle.stop():Promise<void>`；`acquireActiveWorker(db):Promise<WorkerLease|null>`；lease含epoch与assertActive方法。

- [ ] 写双worker竞争测试：只有一个获得active advisory锁，另一个standby；Web刷新的jobs不会自己执行网络请求。
- [ ] 故障测试：持有DISPATCHING意图时kill active worker，接管实例恢复unknown且不再POST；持久化cooldown重启后仍有效。
- [ ] 实现启动顺序：读取env→DB连接→迁移状态检查→active锁→读取cooldown和未决单→恢复对账→开始采集调度→按配置触发决策。退出停止新任务，等待可界定的在途请求，未知保持unknown。
- [ ] 任务原子claim、租约、resource去重和not_before；真实submit job不可通用retry。工作heartbeat与有效env标志写worker_control，页面只读；DB断开不继续新发送。
- [ ] 用户修改decisionInterval后由新config调整下次轮；旧轮仍旧快照，计时器不叠加。managed持仓和未决订单优先，不随enabledChains关闭而停止必要查询。
- [ ] 测试全部collector进入同一Plus队列，后台预算和snapshot覆盖可见；提交`feat: run durable single-executor trading workers`。

**验收：** 关闭浏览器交易循环仍运行；热重启不会多开循环或重复下单。

## T20：综合故障测试、Plus负载回放与需求追踪

**R2必做扩展：** 将专项U01—U06的全部测试纳入门禁及requirement/task/test/result矩阵；D01标DEFERRED，不伪称已实现。

**依赖：** T19。**覆盖：** R01–R12，所有Review Focus。

**文件：** `tests/integration/full-cycle.test.ts`、`plus-load.test.ts`、`failure-matrix.test.ts`；`tests/helpers/fake-gmgn-server.ts`、`fake-jev-server.ts`；`docs/testing/acceptance-matrix.md`。

**接口：** 本地fake服务接受与生产同样的route schema，但只绑定127.0.0.1，fake场景由测试控制：成功、429、超时已成交、未知状态、部分字段缺失、分页遗漏、余额突变。

- [ ] 先建可失败的完整流程测试：三链synthetic行情→A选asset→B选USD20→fake成交→持仓更新→下一轮SELL50%→fake成交→下一轮100%清仓。断言每轮最多1个POST，剩余数量和成本正确。
- [ ] 单独测试envfalse：同样两步模型选择都完成，但POST总数0、账本未变、状态SUPPRESSED。
- [ ] 重现Plus表的60候选＋9额外持仓，以虚拟时间推进10分钟并记录每次发出时间／weight；断言任意区间dispatch weight≤`20+16×秒差`，背景≤其桶容量+10×秒差，P0不被背景长期饿死；100个页面刷新去重。
- [ ] 故障矩阵至少包含：429跨链冷却、签名排队超时、T01映射冲突、所有Jev WAIT、Jev非法action、超上下文复选、quote过期、config切版、余额突变、暂停在途、swap响应丢失、DB写失败、重复fill、deposit、掉榜持仓、费用未知、未知成本。
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

## T21：部署、操作手册和安全交接

**R2必做扩展：** 运维手册补运行成本口径、报价/提示词同步变更和历史cutoff说明；库备份包括新事件/成本表，模型测试替身不会在实盘fallback。

**依赖：** T20。**覆盖：** R01、R10、R12。

**文件：** `Dockerfile.web`、`Dockerfile.worker`、`compose.yml`、`.env.example`、`.gitignore`；`docs/operations/{deployment,configuration,incident-response,backup-restore}.md`；`scripts/check-deployment.ts`及测试。

**接口：** `checkDeployment():Promise<ReadinessReport>`只读；输出缺失字段名、网络能力、db连通、worker状态，不回显secret value。

- [ ] 写部署配置安全检查：env示例false、无真实key、Web service不注入GMGN/Jev密钥、数据库不公开暴露；compose只允许worker网络出口使用凭证。
- [ ] 生成可运行容器构建，非root进程、持久化数据库、健康检查、单worker replicas；应用启动不自动run生产迁移，提供显式迁移步骤和可回滚发布说明。
- [ ] `.env.example`只填写非敏感默认值，密钥空值是部署输入而非可运行占位凭证；实盘配置未就绪通过UI列出，不用假私钥自动替代。Node/pnpm版本和依赖patch均来自T01已验证lock。
- [ ] 运维说明包括IPv4出口和白名单、时钟、DB迁移/seed、登录初始化、API只读check、数据库业务配置、env重启生效、即时暂停、unknown订单处理、密钥轮换、日志轮转、DB备份及恢复。
- [ ] 在临时目录执行备份恢复演练，确认恢复后旧pending/unknown订单仍先对账，禁重复POST；环境开关恢复默认false，不将备份里的paused=false当实盘授权。
- [ ] 完成容器构建与smoke tests，提交`ops: package safe deployment and recovery runbooks`。

**验收：** 有凭证的所有者能按手册部署，不必自己补交易引擎和页面；没有凭证时明确哪些功能未就绪。

## T22：真实账号只读验收、实盘验收入口与交付报告

**R2必做扩展：** 交付报告区分文档检查、自动测试、账号只读与实盘证据；补U01—U06结果，不把参考项目测试或收益当本项目验收。

**依赖：** T21。**覆盖：** R01–R12的外部验证。

**文件：** `scripts/probe-gmgn.ts`、`scripts/probe-jev.ts`、`scripts/live-acceptance.ts`；`docs/testing/provider-verification.md`、`live-acceptance.md`、`delivery-report.md`。

**接口：** `probe-gmgn --chain <允许链>`只读并经Plus调度；`live-acceptance`仅允许明确参数、显式交互确认、envtrue、绑定账户、预定义档位及所有正常gate，不能自由POST任意路由。

- [ ] 未提供凭证时脚本退出`CREDENTIALS_REQUIRED`且不发送请求；probe不可能调用Swap。先为这两个约束写测试并确认FAIL，再实现。
- [ ] 对实际Plus账号逐链验证网络绑定、账户、各价格／金额字段、持仓分页、quote鉴权、费用单位、KOL、common关注计数和限频header；脱敏样例保存source_version、timestamp和test_result，不保存完整鉴权query或headers。
- [ ] 单独验证Jev版本、合法Choice schema和真实usage，记录上下文打包估算误差；不将实际模型一直WAIT误判为集成失败。
- [ ] 只有所有者显式开启实盘并确认验收动作后执行最小档位流程。自动交易保持Jev选择；确定性执行验收可使用manual_acceptance标记，但不得伪造成模型决策，且所有权重、金额、gate、账本规则一致。
- [ ] 每链记录买入、部分卖出、清仓的实际订单ID／hash、输入输出、费用、成本、重启后查询和余额核对。四档组合在T20已覆盖，不要求把每档在实盘各买一次。未知或不能卖出如实记录，不为了验收自动放宽滑点。
- [ ] 更新交付报告：实现状态、自动测试实际命令与结果、只读账号证据、每链实盘状态、已知外部限制、配置说明、部署步骤；凭证未给或某链路由不可用时标`NOT_RUN`或`BLOCKED`，不能全绿。
- [ ] 提交`docs: record provider verification and delivery evidence`；最终只交付脱敏报告，真实密钥永不提交Git。

**验收：** 第一版完整交易能力有明确证据链；是否全部实盘通过与代码是否完成分别报告。

---

## 1. 阶段里程碑

| 阶段 | 任务 | 可审阅产物 |
|---|---|---|
| M1：基础与契约 | T01–T06 | 多链精确金额、DB配置、GMGN鉴权、Plus调度 |
| M2：模型输入与决策 | T07–T13 | 真实数据适配、钱包关注度、完整持仓、两步Jev和冻结意图 |
| M3：完整交易后端 | T14–T16 | 环境闸门、单次提交、订单恢复、成交账本 |
| M4：管理应用 | T17–T19 | 页面、后台API、长驻worker和运行控制 |
| M5：验证与交付 | T20–T22 | 故障矩阵、负载回放、部署手册、账号/实盘验证记录 |

M1～M4分别可测试，但不把中间里程碑当作完整第一版交付。没有真实凭证时不阻碍本地实现与mock测试；只读／实盘验收必须明确留在NOT_RUN状态，而不是编造结果。

## 2. 需求覆盖表

| 需求 | 主要任务 |
|---|---|
| R01 独立完整应用 | T01、T17–T22 |
| R02 官方API和Plus | T01、T05–T08、T19、T20、T22 |
| R03 三链 | T02、T05、T07、T09、T22 |
| R04 独立资金不跨链 | T02、T09、T12、T14、T16 |
| R05 全局单动作 | T11–T15、T19、T20 |
| R06 USD四档 | T02、T04、T12、T14、T18 |
| R07 卖出四档 | T02、T04、T12、T16 |
| R08 行情/KOL/关注度 | T07–T11、T18、T22 |
| R09 DB配置版本 | T03、T04、T10、T13、T18 |
| R10 env实盘开关 | T04、T14、T17–T22 |
| R11 无规则策略/对照组 | T07、T08、T11–T14、T20 |
| R12 成交账本/恢复 | T03、T09、T13–T16、T19–T22 |

## 3. 实施代理的停止条件

以下情况必须停止相应真实写操作并记录，不为“完成目标”自行补猜：签名或网络绑定不明、支付资产美元价格／精度未验证、报价鉴权未确定、持仓不完整、订单结果未知、env关闭、管理员暂停、数据库不可用、Plus被禁、费用参数尚未授权。

可缺失的行情／画像字段明确标unknown，不因为缺标签而自动改变策略；可继续开发和运行只读路径。禁止自建非官方GMGN抓取来掩盖官方API权限不足。

## 4. 本轮文档自查范围

发布计划包前检查：需求R01–R12覆盖、初始金额和比例一致、所有源引用存在、两步决策仍然一笔交易、Plus权重算术、配置版本与pause语义、公开API冲突未被隐去、链接可定位、代码块闭合、计划未声称代码测试或实盘已通过。

本轮文档自查不是代码评审，也不能代替T20～T22的执行证据。计划确认之后才进入代码实施；不要因文档内出现命令就自动运行真实交易。


## 5. R2专项要求覆盖与完成条件

| 增补编号 | 内容 | 归属任务 |
|---|---|---|
| U01 | 提示词/报价/动作/提交语义一致 | T01、T11、T12、T14、T20 |
| U02 | 模型动作不可变、无反向/降档/规则fallback | T11—T15、T20 |
| U03 | 持仓与在途故障回归、独立冷却 | T06、T09、T14、T15、T19、T20 |
| U04 | 有界assetHistory、同轮cutoff、无未来泄漏 | T03、T10、T12、T18、T20 |
| U05 | 持久化时间线、阶段统计及幂等 | T03、T13—T18、T20 |
| U06 | 阶段耗时、模型/API运行成本与收益口径 | T03、T06、T11、T13、T16—T18、T20、T21 |
| D01 | SSE | DEFERRED；不计第一版验收 |

原22项任务编号不变；专项清单的U项按本表并入相应任务，不是T22之后才做。未完成某个必做U项时，对应主任务不可标完成。测试命令和核心示例见`2026-09-21-reference-review-implementation.md`；最终交付报告同时包含R01—R12与U01—U06。

本次只核对文档引用、任务映射、原始需求和新增约束一致性；不声称计划里的任何产品测试已经运行。
