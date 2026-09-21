# 执行规则与短交接模板（R3）

本文件是每阶段必读的短约束；阶段顺序以[执行总览](00-execution-index.md)为准。只读当前阶段和前序交接，不默认载入八份计划或参考仓库全量内容。

## 固定边界

1. 独立产品仓库；common-share只是资料仓库。本次R3只修改文档，不授权产品代码实施或真实交易。
2. robinhood、bsc、sol；各链预存资金，不跨链调拨。资产与账户身份必须带链，Solana地址不lowercase。
3. GMGN官方API，按既有Plus契约rate=20/capacity=20；本地total=16 weight/s、background=10、burst=20。所有调用包括页面刷新经单Worker统一出口，实际接口证据按阶段核验，不以文档数字代替账号验证。
4. Jev自主选择；全局每轮最多一个最终Swap。买入10/20/50/100 USD本金参考值，卖出当前可用持仓25/50/75/100%。所有金额用精确值，raw与USD cents为整数字符串。
5. 数据库是业务配置唯一来源；CAS版本化、同轮冻结；金额/比例冻结为raw。暂停是独立即时授权，不靠改档位撤销在途订单。
6. TRADING_ENABLED默认false；Web不能绕开。只读/CI测试禁止真实Swap，密钥只在Worker服务端；不在聊天/Git/日志中记录secret。
7. 不增加程序选币评分、置信度门槛、固定止盈止损、自动跟单、对照组、其他LLM或规则fallback。BUY受阻不得改SELL、降档、换币或换链。
8. 原始模型选择/hash/probabilities不可变，执行结果追加记录。WAIT/ABSTAIN是决定，超时/协议错误不是决定。
9. 缺失≠0，转账≠买卖，钱包数≠人数；关注度不是信誉评分。managed持仓不因掉榜/分页失败/无标签消失。历史同时满足occurredAt/recordedAt不晚于本轮cutoff。
10. 提交≠成交；unknown不重发、不释放已可能花掉的预留。实际fill事务入账，重复响应幂等；费用未知不当免费，充值不算利润。
11. 结构维持Next.js＋单active Node Worker＋PostgreSQL。无Redis/向量库/微服务/桥接/公开注册/任意交易面板。SSE为DEFERRED，不阻塞V0.1。
12. 页面/文档中文，代码注释可英文。来源/测试模式/软件实现/账号验证/实盘结果必须分别标注。

## 阅读与接口约定

首次执行只看总览当前行、此文件、当前P计划及前一阶段handoff。任务确实需要外部契约时，只读计划列出的API证据Sxx；设计仅读指定章节。不能把“少读”变成猜测接口。

P01定义基础domain、schema和仓储；P02定义Provider/Worker接口；P03定义DecisionState/历史契约；P04定义Choice/QuotedAction/TradeIntent；P05定义执行与账务；P06提供内部API/页面。实际类型和Zod schema只在代码中维护，计划引用对应文件。新增字段由owner更新契约与消费者测试，不各自复制类型。

每任务先写可失败测试→运行确认失败原因→最小实现→复验→提交。网络统一注入HttpTransport，测试只允许loopback；DATABASE_URL_TEST必须独立于生产且库名含test。不得把断言删除/skip后标通过。缺凭证可以完成合成测试，外部验收保持NOT_RUN。

资料复制到独立产品仓库后，文档中的`apps/`、`packages/`、`scripts/`均相对产品仓库根；共享规则、阶段文件、主设计与证据一起保留。P01前需已经明确产品目录/仓库，未给目标不得自动在common-share落产品代码。

## 阶段状态与结束条件

[execution-status.json](execution-status.json)是阶段进度唯一入口：NOT_STARTED→IN_PROGRESS→IMPLEMENTED→VERIFIED；确实不能继续为BLOCKED。IMPLEMENTED不代表测试通过，VERIFIED仅代表本阶段已规定的本地验收有证据。

独立字段externalValidation记录providerReadOnly和liveAcceptance（NOT_RUN/BLOCKED/PASS/FAIL）。P08软件可以VERIFIED而实盘NOT_RUN，不把两者合并成一个绿勾。D01永远不计为本版缺口。

默认顺序P01→P08。一阶段一个主要会话，内部按任务提交；完成后停止，不自动进入下一阶段，除非用户另行授权连续执行。公共契约/迁移/lockfile不并行抢写；前置代码不满足合同应标阻塞并指明owner，不在后续阶段自造替代层。

## 交接记录

每阶段在产品仓库写`docs/execution/Pxx-handoff.md`（Pxx为当前阶段编号），并更新execution-status。交接是短证据表，不复制聊天全文，不虚构commit/日志。

```text
阶段与状态：当前P编号，IMPLEMENTED/VERIFIED/BLOCKED及理由
代码依据：产品仓库分支、实际commit、工作区是否干净、R3计划版本
交付接口：新增/变化的导出签名及文件路径；DB迁移版本；保留的不变量
验证结果：逐条实际命令、退出码、断言摘要、失败/跳过项与日志路径
外部状态：只读/逐链实盘的NOT_RUN/BLOCKED/PASS/FAIL及证据
下一阶段：唯一下一P编号；必读代码文件；未解决接口/运行限制
```

交接结束后不要提前写后续阶段的实现。下一Agent先校验commit与前置接口，再运行当前计划的前置检查；不得仅凭上一Agent自述认为通过。
