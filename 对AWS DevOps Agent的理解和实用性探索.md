AWS DevOps Agent 确实可以做成“自动触发调查”，并不是每次都要你手动进去点。AWS 官方目前支持几种入口：内置的 ticketing/incident 集成、webhook，以及手动启动；官方文档明确举例说可以通过 PagerDuty ticket、Grafana alarm 等 webhook 事件自动触发 investigation。它也会结合 CloudWatch、Datadog、Grafana、New Relic、Splunk 等 observability 数据做调查。AWS DevOps Agent = 大约 $29.88/active-agent-hour 的 AI SRE/诊断工程师。

不过实际用起来也没人说一有点什么 incident，就立刻开 AWS 的 DevOps Agent。

它也是有分级的：Tier 1 肯定是对接 CloudWatch 报警，当然也是因为一些 metric 或者 log 报错、数据不对了。这个时候还是要先进行简单的判断，看是不是值得升级成 incident。

只有当确实需要更高级的智能去处理，或者现有的 runbook、已有的 case 经验不足以解决问题时，才会让 DevOps Agent 去进行 investigation。
