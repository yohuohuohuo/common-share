# P02 供应商接入与运行基础 Implementation Plan

> **For agentic workers:** 本次只执行P02。已获产品实施授权后可用环境可用的superpowers:executing-plans或subagent-driven-development；先测试、再最小实现、验证、提交。本文是计划，步骤未执行。

**Goal:** 让所有供应商请求经过唯一受控出口，并提供可运行的单Worker骨架。

**Architecture:** 独立Next.js Web＋单active Node.js Worker＋PostgreSQL。三链共用GMGN Plus出口；全局两步Jev最多一笔Swap。

**Tech Stack:** 沿用P01锁定的Node.js 24 LTS、pnpm、TypeScript strict、Next.js、Drizzle/PostgreSQL、Zod、精确金额、Vitest/Playwright。本文不另定版本。

**Spec:** [主设计](../specs/2026-09-21-jev-gmgn-trader-design.md)，本阶段仅需第4节、9节、10.1及13节；15.5供应商隔离。

**状态：** [execution-status.json](execution-status.json)为唯一进度入口；本次R3仅拆分文档。

## Global Constraints

必读短文[execution-rules.md](execution-rules.md)。robinhood/bsc/sol；10/20/50/100 USD买入，25/50/75/100%卖出；数据库配置；Plus16/20总预算与背景10；Jev全局单动作；默认TRADING_ENABLED=false；无规则选币/置信度门槛/固定止损/跨链调拨/对照组。

## Review Focus

签名必须排队后生成；weight而非请求数；多进程不重复领取；供应商冷却隔离；缺handler不伪成功。

## 输入、范围与交付边界

**输入：** P01导出的Db/TradeConfig/HttpTransport/Clock/RouteRule、费用/事件仓储；P01已验收migration。

**输出：** GmgnClient；签名序列化；Plus队列；provider冷却和计量；WorkerLease/HandlerRegistry/startWorker；READ_PROBE入口。

**不做：** 不实现策略、不完整组装市场快照、不提交交易；不先造整套UI。

只修改本阶段任务列出的文件。公共schema/domain接口修改必须兼容前序并重跑消费者测试；不为了本阶段方便复制另一套类型或签名客户端。

## 最小阅读与前置检查

只读执行总览的当前阶段行、execution-rules、本文件，以及`docs/execution/P01-handoff.md`和其中指定的已存在接口。旧R2主/专项执行文件不再必读；按本阶段Sxx引用定点查看[API证据](../../references/2026-09-21-api-evidence.md)，不要重读参考项目全仓。

前置复验：

```bash
pnpm typecheck
pnpm exec vitest run tests/integration/db-constraints.test.ts tests/integration/config.test.ts
```
前置P01未通过本地验收时，不开始本阶段；外部账号NOT_RUN不是本地代码阶段的自动阻塞。

## P02.01：GMGN HTTP客户端、签名和错误契约

**来源编号：** T05（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.01、P01.02。**覆盖：** R02、R03、R10，Review Focus 1。

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
- [ ] 注册持仓和query_order为signed；quote的鉴权由P02.03建立的只读probe核验并在P08.02汇总，不因401循环升级权限。敏感headers只存hash/字段名，禁止完整curl日志。
- [ ] 测试实际public-key verify成功、JSON改变1字节失败、UTC秒单位、过期签名、未知状态未被映射为成功；通过后提交`feat: implement audited GMGN transport and signing`。

**验收：** 只发送注册过的官方路由；鉴权查询能力和交易提交开关相互独立。

## P02.02：Plus全局权重调度与冷却

**来源编号：** T06（仅供覆盖追踪，不作为另一套执行入口）。
**依赖：** P01.03、P02.01。**覆盖：** R02，Review Focus 4。

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
- [ ] permit授予后才让P02.01生成时间戳和签名；请求排队60秒不得产生旧签名。429从header/body提取较晚合法reset时间，持久化全Key冷却；cooldown中P0也不请求。
- [ ] 测试Web刷新+三链任务只共享一个桶；额外Key不允许绕过；restart读取cooldown且bucket从0恢复；单调时钟回拨不补充；错误时间戳fallback5–60秒；恢复单读探针。对429的Swap不自动再POST。
- [ ] 跑虚拟时钟负载测试并提交`feat: enforce shared GMGN Plus weighted scheduling`。

**验收：** 时间窗口内发出的权重满足保守桶约束，而非仅平均值；有冷却和每路由计量。


### 本阶段内联增补：供应商隔离与调用计量（U03/U06）

- [ ] GMGN和Jev分别保存provider cooldown。Jev采用请求deadline及预算，不套用GMGN的weight桶；Jev429只影响Jev，529/5xx记可用性错误。有效Retry-After优先，缺失用5—60秒有界退避。GMGN全凭证冷却对三链及全部优先级生效，恢复只发只读探针。
- [ ] `cooldown.test.ts`用虚拟时钟分别注入两种429，在实际HttpTransport上统计call count：冷却内相应provider计数不变；Jev冷却不阻止GMGN订单查询；不能用队列任务数量代替网络次数。
- [ ] 建立`packages/domain/src/stage-metrics.ts`和同名测试，导出`durationMs(start:number,end:number):number|null`及`StageTiming`，字段为`stage/clockDomainId/startedAtMs/endedAtMs/durationMs/outcome`。负值、非有限或跨进程单调时钟不相减；字段缺失保留null。

```typescript
import {expect,test} from 'vitest';
import {durationMs} from './stage-metrics';
test('invalid duration remains unknown',()=>{
  expect(durationMs(200,250)).toBe(50);
  expect(durationMs(250,200)).toBeNull();
});
```

- [ ] 先运行测试观察FAIL，再实现有限非负差值；调度接线测试排队200ms与请求50ms分别记录，不能只存合计250ms。调用P01仓储为每attempt写记录，GMGN weight不换算成美元。并行100ms/80ms的端到端按真实时钟记录，不求和180ms。
- [ ] 自动化fixture验证取消deadline后不发新请求、Jev半开失败不污染GMGN状态、重启读回两个provider的持久化冷却。测试不访问真实服务。


## P02.03：前置 Worker 骨架与按需接入（原 T19 的运行基础）

**依赖：** P01、P02.01—P02.02。**不依赖：** 决策引擎、执行器或管理页面。

**文件：** `apps/worker/src/{main,bootstrap,health,handlers}.ts`、`scheduler/dispatch.ts`；`packages/db/src/{jobs,worker}-repository.ts`；`tests/integration/worker-bootstrap.test.ts`；`apps/worker/src/handlers.test.ts`；`scripts/probe-gmgn.ts`及测试。

**接口：** `startWorker({db,transport,clock,env,handlers}):Promise<WorkerHandle>`；`WorkerHandle.stop():Promise<void>`；`acquireActiveWorker(db):Promise<WorkerLease|null>`，lease导出epoch与assertActive。`WorkerJob`是jobs持久化记录的只读投影，`JobContext`持有受限客户端、db和lease，不允许handler绕开统一transport。各完整类型在对应模块导出，由P03—P05复用。

```typescript
export type JobKind='READ_PROBE'|'COLLECT_MARKET'|'COLLECT_KOL'|
  'SYNC_ACCOUNT'|'DECIDE'|'SUBMIT'|'RECONCILE';
export type HandlerRegistry=Partial<Record<JobKind,
  (job:WorkerJob,ctx:JobContext)=>Promise<void>>>;
export function canDispatch(kind:JobKind,registered:ReadonlySet<JobKind>,
  envEnabled:boolean):boolean {
  return registered.has(kind) && (kind!=='SUBMIT' || envEnabled);
}
```

- [ ] 先在handlers.test.ts写失败测试，确认导出未实现再实现上面纯判断。提交前P05仍会再次检查env，不能只依赖这里。

```typescript
import {expect,test} from 'vitest';
import {canDispatch,type JobKind} from './handlers';
test('missing submit handler is blocked, not fake success',()=>{
  const registered=new Set<JobKind>(['READ_PROBE']);
  expect(canDispatch('SUBMIT',registered,true)).toBe(false);
  expect(canDispatch('READ_PROBE',registered,false)).toBe(true);
  expect(canDispatch('SUBMIT',new Set<JobKind>(['SUBMIT']),false)).toBe(false);
});
```

- [ ] 运行`pnpm exec vitest run apps/worker/src/handlers.test.ts`观察FAIL后实现，未注册handler保存`BLOCKED_HANDLER_NOT_REGISTERED`，不标成功、不忙循环、不默认空实现。
- [ ] 单active锁、epoch/fencing和心跳、atomic claim、not_before、resource去重、租约和stop/drain在本阶段完成。真实SUBMIT不走通用retry；租约过期不能重放提交。DB/锁失效停止新dispatch。cooldown从DB加载，预算从0恢复。
- [ ] `worker-bootstrap.test.ts`用隔离DB与假transport验证两进程仅一个active、standby不发请求、停止释放读任务租约、重启不重放SUBMIT。已有DISPATCHING但未注册RECONCILE时保存未决阻塞原因，不清理/忽略该订单。
- [ ] P03添加collector handler，P04添加只读决策handler，P05添加提交/对账handler。P07是实际全套注册和故障验收，不重新写基础生命周期。
- [ ] 首个READ_PROBE只允许注册表中READ路由；有凭证可显式运行只读check，无凭证返回CREDENTIALS_REQUIRED且网络次数0；所有自动测试仅loopback。P03补数据字段核验，P08汇总外部证据，不能等最终部署才检查已知契约冲突。
- [ ] 运行`pnpm exec vitest run tests/integration/worker-bootstrap.test.ts apps/worker/src/handlers.test.ts`、typecheck、build并提交`feat: establish durable worker foundation without trading handlers`。

**验收：** 不依赖UI或Jev即可证明安全调度/启动；完成的是可扩展运行基础，不假称交易闭环已可用。

## 本阶段验收与交接

以下为待执行命令，必须保存实际退出码和摘要；命令存在但测试未写、无断言或被跳过不算通过。

```bash
pnpm exec vitest run packages/providers/src/gmgn apps/worker/src/scheduler apps/worker/src/handlers.test.ts packages/domain/src/stage-metrics.test.ts
pnpm exec vitest run tests/integration/worker-bootstrap.test.ts
pnpm typecheck
```

完成本阶段指定任务与内联U要求后，更新`execution-status.json`及产品仓库`docs/execution/P02-handoff.md`。交接内容使用execution-rules中的短模板：代码提交、当前契约路径、迁移版本、实际测试结果、明确外部阻塞。不得用聊天里的“已完成”代替记录。

**停止边界：** 完成本阶段后停止，不自动进入下一阶段、不自动启用真实交易。无凭证仍可实现及测试本地路径；外部验证独立标NOT_RUN/BLOCKED，不能虚构通过。
