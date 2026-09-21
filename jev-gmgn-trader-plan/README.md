# Jev × GMGN 多链交易实验：V0.1 / 执行计划 R3

日期：2026-09-21。**当前仅有计划文档，产品代码未实施。**

## 开始阅读

从[八阶段执行总览](docs/superpowers/plans/00-execution-index.md)进入。每次Agent会话只读[执行规则](docs/superpowers/plans/execution-rules.md)、当前阶段计划和前一阶段交接；设计只查本阶段相关章节，不再全量读取旧主/专项计划。

- [P01 项目基础与配置](docs/superpowers/plans/01-foundation-and-config.md)
- [P02 供应商接入与运行基础](docs/superpowers/plans/02-provider-and-runtime.md)
- [P03 数据采集与决策快照](docs/superpowers/plans/03-data-and-snapshots.md)
- [P04 Jev 决策与交易意图](docs/superpowers/plans/04-jev-decision-and-intent.md)
- [P05 交易执行与账本](docs/superpowers/plans/05-execution-and-ledger.md)
- [P06 管理后台](docs/superpowers/plans/06-admin-application.md)
- [P07 全流程集成与故障验收](docs/superpowers/plans/07-integration-and-failure-tests.md)
- [P08 部署与外部验收](docs/superpowers/plans/08-deployment-and-external-acceptance.md)

## 本次拆分

原22项主任务保留覆盖；Worker的运行骨架前移，形成23个阶段内任务。U01—U06已内联到对应阶段，旧执行文件仅保留导航和Git历史链接。SSE仍后续增强，未增加规则策略、对照组或依赖服务。

[阶段状态](docs/superpowers/plans/execution-status.json)初始全部NOT_STARTED；[覆盖映射](docs/superpowers/plans/coverage-map.json)连接R01—R12、旧T01—T22和U01—U06，映射不代表代码已经通过测试。

## 固定需求

Robinhood/BSC/Solana；各链预存资金不自动桥接；GMGN官方Plus；Jev全局最多一笔最终交易。买入10/20/50/100 USD本金参考值，卖出当前可用持仓25/50/75/100%；数据库配置版本化，TRADING_ENABLED服务端环境变量默认false且页面不能绕过。独立项目、管理页面、真实成交/账本/恢复闭环均为V0.1交付范围。

程序提供行情、安全、KOL参与、钱包被追踪/被备注等事实与历史，不设置选币/置信度门槛或固定止盈止损。

## 设计与来源（按需查阅）

- [需求与技术设计](docs/superpowers/specs/2026-09-21-jev-gmgn-trader-design.md)：包含R3阶段职责，第1—15节业务和工程不变量继续有效。
- [API核验记录](docs/references/2026-09-21-api-evidence.md)：既有公开契约和待账号核实项；本次未重新执行供应商请求。
- [参考项目评审](docs/references/2026-09-21-reference-project-review.md)：固定源码版本与采用边界，不是Agent每阶段必读的另一份计划。

## 实施与验证边界

common-share/jev-gmgn-trader-plan仅存资料。只有用户明确要求产品实施并指定独立目标后，才进入P01；本次拆分不创建产品代码、不安装依赖、不提交真实交易。

每阶段结束按执行规则写产品仓库`docs/execution/Pxx-handoff.md`，状态/实际测试/接口/commit均可复查。缺凭证可完成本地模拟传输测试，账号只读和逐链实盘验证单独标NOT_RUN，不能虚构通过。

`document-validation.json`仅为本次文档检查，`SHA256SUMS.txt`覆盖除自身外全部文件。校验脚本见[scripts/validate-plan.py](scripts/validate-plan.py)，不运行产品代码或外部网络。
