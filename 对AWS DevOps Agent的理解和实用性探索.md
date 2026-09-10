AWS DevOps Agent 确实可以做成“自动触发调查”，并不是每次都要你手动进去点。AWS 官方目前支持几种入口：内置的 ticketing/incident 集成、webhook，以及手动启动；官方文档明确举例说可以通过 PagerDuty ticket、Grafana alarm 等 webhook 事件自动触发 investigation。它也会结合 CloudWatch、Datadog、Grafana、New Relic、Splunk 等 observability 数据做调查。AWS DevOps Agent = 大约 $29.88/active-agent-hour 的 AI SRE/诊断工程师。

不过实际用起来也没人说一有点什么 incident，就立刻开 AWS 的 DevOps Agent。

它也是有分级的：Tier 1 肯定是对接 CloudWatch 报警，当然也是因为一些 metric 或者 log 报错、数据不对了。这个时候还是要先进行简单的判断，看是不是值得升级成 incident。（这里的判断主要是指，有的时候网络卡一下，或者有一些非常短暂的问题。这类问题的原因可能多种多样，很有可能单纯就是云服务厂商那边的服务稍微卡了一下，然后很快又恢复了。所以为什么不是有一点事就开始找 DevOps Agent，因为很多东西都是 false positive，这部分直接筛掉就行。只有当问题一直持续出现，或者属于严重问题时才会处理，这边是有一个判断界限的。 ）

只有当确实需要更高级的智能去处理，或者现有的 runbook、已有的 case 经验不足以解决问题时，才会让 DevOps Agent 去进行 investigation。

另外它的优势在于同步。比如说它这边给出的三四个可能原因，可能是刚刚部署完，可能是数据库那边爆了，或者各种稀奇古怪的问题。-吐槽一下，这也是为什么如果把EBO BOT项目代码挪到云端，我更偏向于去走 Fargate Task，而不是租一台 EC2 在上面装 Docker 跑这两个 Container。因为它们的运维复杂度还是不太一样的，如果把精力放在对 Linux 本身的 performance 监控和 troubleshooting 上，我精力根本顾不上，而且这也不是这个项目的重点。

接着讲，如果是人类的话，人是单线程的，不太可能同时去进行调查。

但 Agent 那边可以理解成一个 auto-scaling 的东西，从架构上可以非常简单地实现智能扩展：同时对三四个、四五个甚至十几个可能的原因分别进行调查，出调查结果之后再去汇总。

这个在智能拓展上确实是 AI 碾压人类的地方。
