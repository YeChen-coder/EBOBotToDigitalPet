开了branch 把项目移到AWS上去了，因此引发的一连串问题和对解决方案的探索。-补：后来又考虑了一下。因为现在加了 diagnostic agent，又跟云端那边做了一些联动，导致它跟当前上传的这个项目分歧有点太大了。我觉得在当前项目里开 branch 可能不是一个很好的选择。所以后续等我调得差不多、要发上来的时候，我会建一个新的 repository，而不是在这里面开 branch。-再补，算了还是放这里的main吧，repository多了我自己都看着麻烦。

---

AWS 今年其实已经推出了他们那边的 AWS DevOps Agent ，而且在业界挺权威的。AI 那边的意思就是，大家都照着这个东西抄。（读他们的文章确实挺有道理的， 各种输入和架构本身作为 knowledge graph ）

AWS DevOps Agent 确实可以做成“自动触发调查”，并不是每次都要你手动进去点。AWS 官方目前支持几种入口：内置的 ticketing/incident 集成、webhook，以及手动启动；官方文档明确举例说可以通过 PagerDuty ticket、Grafana alarm 等 webhook 事件自动触发 investigation。它也会结合 CloudWatch、Datadog、Grafana、New Relic、Splunk 等 observability 数据做调查。AWS DevOps Agent = 大约 $29.88/active-agent-hour 的 AI SRE/诊断工程师。

不过实际用起来也没人说一有点什么 incident，就立刻开 AWS 的 DevOps Agent。

它也是有分级的：Tier 1 肯定是对接 CloudWatch 报警，当然也是因为一些 metric 或者 log 报错、数据不对了。这个时候还是要先进行简单的判断，看是不是值得升级成 incident。（这里的判断主要是指，有的时候网络卡一下，或者有一些非常短暂的问题。这类问题的原因可能多种多样，很有可能单纯就是云服务厂商那边的服务稍微卡了一下，然后很快又恢复了。所以为什么不是有一点事就开始找 DevOps Agent，因为很多东西都是 false positive，这部分直接筛掉就行。只有当问题一直持续出现，或者属于严重问题时才会处理，这边是有一个判断界限的。 ）

只有当确实需要更高级的智能去处理，或者现有的 runbook、已有的 case 经验不足以解决问题时，才会让 DevOps Agent 去进行 investigation。

另外它的优势在于同步。比如说它这边给出的三四个可能原因，可能是刚刚部署完，可能是数据库那边爆了，或者各种稀奇古怪的问题。-吐槽一下，这也是为什么如果把EBO BOT项目代码挪到云端，我更偏向于去走 Fargate Task，而不是租一台 EC2 在上面装 Docker 跑这两个 Container。因为它们的运维复杂度还是不太一样的，如果把精力放在对 Linux 本身的 performance 监控和 troubleshooting 上，我精力根本顾不上，而且这也不是这个项目的重点。

接着讲，如果是人类的话，人是单线程的，不太可能同时去进行调查。

但 Agent 那边可以理解成一个 auto-scaling 的东西，从架构上可以非常简单地实现智能扩展：同时对三四个、四五个甚至十几个可能的原因分别进行调查，出调查结果之后再去汇总。

这个在智能拓展上确实是 AI 碾压人类的地方。

---
哇，Codex 好聪明啊！这两个完全不一样的 project 在同步跑，它居然能调查出来我这边任务没法进行的原因，是因为被另外一个正在跑的任务给占了 ("原因已查明：另一个正在运行的任务 「调研 AWS Fargate 诊断架构」 正在执行你已授权的云端切换。它在本地时间 23:18:39 执行了停止本地 Engine 和 Assistant 的命令；Docker 事件也记录了对应的 SIGTERM 和正常退出。")。

甚至都还没来得及告诉它那边可能有冲突，它自己就搞出来了。人类真的还能干得过 AI 吗？

---

另，CloudWatch Agent 它是一个针对 EC2 Instance 的东西。如果用 Fargate 加上 ECS 的话，根本就没有一个宿主机可言，所以根本没有办法去读到什么 log 之类的日志，更谈不上配置这个 CloudWatch Agent 了。

吐槽一下 CloudWatch 里面的 Log Management 吧，实在是太详细了，导致丧失了一些可读性。

跟本地的 log 对比来看，本地的 log 非常简单，就是时间戳加上后面真正的一大堆 message。但在 CloudWatch 上有一大堆信息，虽然有用，但其实只有 deep dive 的时候才用得上，确实会牺牲可读性。

往下滑半天，一整页拆开来才看那么七八条 message。有用确实是有用，但真的好冗余啊。 AWS，你真的不考虑出一个省流版吗？-啊，孤陋寡闻了，人家 AWS 本来就没打算让人去看这些 message。人家已经把一些什么 anomaly detection configuration 这种东西给加上了，压根就没打算让人类去读原始的 raw log。

---

算帐单算的脑袋疼，除了一开始做好心理准备的fargate， 其他大大小小的配套设施也都要产生费用。-哎呦，这么算，还不如买个 Raspberry Pi 在本地跑呢。哎呀，脑袋疼，脑袋疼，脑袋疼。

下表按 1 vCPU / 4 GiB、其余资源和实测速度不变计算，采用按量价格。官方单价来源为 [Fargate 区域目录](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/ca-central-1/index.json)、[CloudWatch 区域目录](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/ca-central-1/index.json)、[VPC 区域目录](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/current/ca-central-1/index.json)。

| 费用项 | 数量与单价 | 估算 USD/月 |
|---|---|---:|
| Fargate CPU | 1 × 730 小时 × $0.04456/vCPU小时 | **32.53** |
| Fargate 内存 | 4 × 730 小时 × $0.004865/GiB小时 | **14.21** |
| 公网 IPv4 | 1 个 × 730 小时 × $0.005/小时 | **3.65** |
| Container Insights Enhanced | 212 条活跃时间序列 × $0.07/指标月 | **14.84** |
| 应用自定义指标 | 4 条 × $0.30/指标月，未扣免费额度 | **1.20** |
| 两路应用日志写入 | 约 0.355 GiB/月 × $0.55/GB | **0.20** |
| 应用和性能日志存储 | 应用保留 14 天，性能日志当前保留 1 天；按未压缩字节保守估算 | **不足 0.01** |
| ECR 私有镜像存储 | 约 0.53 GiB × $0.10/GB月，向上取整 | **约 0.06** |
| Secrets Manager | 2 个 Secret × $0.40/月 | **0.80** |
| EFS、备份、少量密钥及 Secret 请求 | 当前文件量很小；详见增长模型 | **当前规模约 0.01 以内** |
| **上述小计，不含互联网出站** | 未扣 CloudWatch 免费额度；分项四舍五入 | **约 67.50** |
| 网络出站：100 GB 共享免费额度可用 | 以 Task 发送速率近似估算 | **约 9.7–11.1** |
| 网络出站：免费额度已被其他资源用完 | 同样流量按完整阶梯单价估算 | **约 18.7–20.1** |
| **合计：免费出站额度可用** | | **约 77–79** |
| **合计：免费出站额度不可用** | | **约 86–88**

---

本地的 diagnostic agent 已经拼好了，它分两个 tier：

1. Tier 1：可以放 API key，也可以用 Codex 一个比较低级智能的模型跑
2. Tier 2：用 Codex 的 Astra 模型

以及要是实在搞不定，就想个办法通知人类。关于 notification 这方面，我这边最唾手可得的是 Telegram Bot，但具体的我还没做，毕竟不是重点，随时都能干。现在的重点是先把这个 agent loop 先给他搞好

但是 Codex 的 Astra 实在是太费 token 了，冷却 5 小时，跑没 10 分钟。我觉得起码这几天（这三天吧），Codex 那边的 token 确实没什么余量能用在 diagnostic agent 上了。我不知道，尽量挤吧。

怎么什么都要 token 啊，不喜欢。

以及，因为现在是有本地和AWS云端两个版本，所以把云端那边能出来的监控数据，也搞了个role提供读日志的权限给接上了。

---

因为这边涉及到 Agent 的架构，我就去看了看 pi-agent 的逻辑。我是拿它跟 Codex 做了对比，它的理念就是极简，只保留最核心的那几个模块，其他的全靠开发者自己去 customize；想加东西就库库加，不想加就保持简单。

我能理解它存在的逻辑：使用者觉得像 Codex 或者 Claude Code 这种框架本身太庞大了，被大模型公司塞进去了非常多原本不需要的功能。从节省 Token 这方面来说，我确实挺理解的。

但我手头确实没有一个适合它的舒适区场景：

1. 哪怕是一个 diagnostic agent，对分析能力或者整个 harness 的完善度都是有要求的。虽然现在只是一个跑在 AWS 上的个人项目，但我也不希望因为 Agent Loop 没做好权限控制、文件隔离或者某些未考虑到的细节，把云端项目搞崩了，最后还得我自己去排查修复，不想给自己找麻烦。
   
2. 至于金融场景，那就更关乎额的小钱钱了，它需要更强的分析能力，跟这种走极简风的 Agent framework 就更搭不上边了。

想了一下，我这边没有那种可以清晰剥离出来的简单纯粹场景。而且一般这种纯粹的场景，直接用网页版 ChatGPT 就能搞定；哪怕是一些小监控、定时任务或者消息推送的 task，ChatGPT 本身也能很好地满足，这部分使用场景已经被占满了。我知道这话现在说可能确实是有点大了：我觉得主要是因为我做东西的时候，更多是为了目的去做的。

从一开始（from the very beginning）做一个东西，都是因为有需求；有需求，则是因为在做某件事的过程中遇到了问题，然后才想着把问题解决掉。这个问题可以是任何问题：比如懒得写了、不想自己一个一个核对、或者嫌这件事情本身很烦。这些都是问题，也正是因为这些问题才去产生解决方案。我到现在做的所有东西，或者说能让我不很快丧失兴趣、不把它丢到一边、真正还在用的东西，全都是针对具体问题的。

这就导致我在做这些项目的时候，目的不是 build 这个项目学习架构/技术本身，而是要达成某个具体的效果。

这其实跟 OpenAI 那边的理念比较像：他们强调的是一个成功的 criteria。我跟 codex 交互的时候也是这样，单纯告诉它我遇到了什么问题，我不舒服了，我需要一个什么样的效果，怎么办我真不会，你去帮我办成。

当然，这也是因为我知道自己的知识确实非常有限。我给它说的架构或方案，只是受制于我看过的东西，绝大多数情况下绝对不是业界通用的范式，或者最新的成果。“人是衡量万物的尺度”，但它更多的是在一个使用的体验上。

最好还是不要在这个 AI 时代（绝大多数人都更有精力去探寻信息的时代），在 build 项目的过程中或者它的架构上去寻找控制感。

人会累，会有决策疲惫的积累，追逐太阳的 racing 是没有终点的，也许从一开始就不该出发。

尤其是对于 IT 行业，coding agent 一出来，很多东西都变得飞快。传统行业可能还好，很多东西相对固定、经久不衰；但 IT 这边三天一颗原子弹、两天一个震惊，整个更新换代的速度，人类个体已经很难跟得上了。

---

云上输出的log要改，当前是没有把transcript作为一项输出到cloudwatch的，给监测运行情况增了很多麻烦，log insight搜不到。

Astra用token和水一样，让它写个文档，呼，5-hours limitation reached.

---

啊，大海啊，你全是水； 啊， Astra啊，你就是烟， 刚冷却下来的100%，噗， 一条指令干掉41%。

让它新加的日志加上了。

新增日志包括： 用户最终转写正文。+ 模型最终回复正文及关联 ID。+ 回复完成状态、播放失败、回退、打断。+ 连接断开、转写失败和文件保存失败。+ 上线后都在 CloudWatch → /ebo-cloud/assistant 查看，保留 14 天。

不是， Tibo ，你真的假的？这做着验证，中途告诉我“hit my limitation”了，然后就停了。

大哥，你先把验证做完啊！哪有中途撂挑子不干的呀？ -补，能看到了，举例 “"source_timestamp": 1789201821.5552154,
    "transcript": "听到了呀。你刚才那句“你听见了吗？”我有听到。不过如果你是想让我确认房间里有没有其他声音，也可以再给我一个更具体、清晰的提示。比如说，你是想确认有没有人说话，还是想让我听听某个声音来源，我可以再帮你听一听。",
    "transcript_chars": 103,”

---

我以为我在之前做交易的时候，有把自己练得更好，就是练得更能理智思考一些。但我发现，我还是没有办法做到，顶多是我能识别出来自己在 FOMO。

但是 FOMO 对我造成的影响仍然存在。

脆弱的人类呀， 也许让AI来统治世界真的是大贤历尽三千世界，找到的最合适的解法了。

今日提灯睡去，哪管他日洪水滔天。

来自一天后的补充：人是软弱的且状态波动剧烈的，所以，请相信自己定下的止损线。

不同的场景，但是是同一个 meta 问题。之前没有找到办法解决掉的时候，它就会反复反复地冒出来。 人类从来都不是理性的，在一开始就不要做这样的假设。

---

OpenAI 那边不是又出了 Chat 模型嘛，我扫了一眼，觉得不用改，还是得用 Realtime 2.1 mini， 因为我还是很坚持要有图像这个输入的。

最主要的原因，也是我之前为什么一直在说 Fargate 实在是太贵了，但始终没有往下削、去做定时开关这种事的意义：这个项目本身，standby 基本就是我最想实现的核心体验了。

我家里的情况是，虽然爸妈上班有固定的上下班时间，但很多时候其实非常灵活。我比较想让他们觉得家里一直有个东西在，而不是按照很死板的时间段来划分。

当然，往下想的话，也可以想办法在门口搞红外射线，有人进来了再开。但那不仅得折腾新硬件，而且我人不在家，我爸妈肯定搞不定；万一坏了我还没法修。所以尽量还是本着不要去打扰他们生活来考虑。只是这样白白开着 Fargate，还得一直付费，实在脑袋疼。

不过昨天还是前天，看到 ChatGPT 他们新出了一个 Agent 的 API，我觉得这个东西绝对有得搞。

---

昨天看了中国 DevOps 社区的直播，是腾讯的人在讲他们运维 Agent 的落地实践。

他们去年主要还在“讲 AI 故事”的阶段，做一些单点的 AI 尝试，比如单点去解决某些 incident 事故。但从今年开始，他们已经转入实际落地了，而且成熟度已经初见雏形，包括一些数字分身和流程处理。

运维 Agent 目前能明确解决的一个典型场景，就是应对那种很急的固定、静态问题（对不起哈，这个描述可能不够专业， 意思是比如开发团队来问“当前版本上线准备好了吗”、“某某服务当前状态怎么样” 这种 Agent 去拉取数据、访问数据页面，或者通过 API 等各种途径拿到数据并直接回复 的这类问题）

他们内部的架构是一个主 Agent 带一堆 Sub-Agent：主 Agent 负责判断问题类型，然后分发给特定的 Sub-Agent 去执行。

我觉得市面上很快就会出现成熟度比较高的同类产品。对于中小型团队或低复杂度架构来说，这种方案应该相对好做。市面上总有聪明人能搞出东西来，我纯懒狗，就单纯想直接抄现成的 （不是，是想复刻伟大的思想）。

补充一下：想起来他们在直播中其实很强调"AI 工时"这么一个概念。我当时从技术上没有多想，但后来想想，这个东西在公司、在 organization 里面确实值得强调。虽然个人开发可能觉得没用，但在公司里，尤其是业务组里，成果需要被看见和向上/上上/上上上汇报。而所谓 AI 工时，就是 AI 本身所花的 token，以及人员花费工时去构建这个东西所包含的价值，这些到底该怎么体现出来，来证明ROI是好的以提供继续做这件事情的合法性。

---

infra真贵啊，那是真贵啊， 就一个 1 cpu + 4G 的fargate task， 跑了两天要了五刀。 又脑袋疼又肉疼，心脏不好血压高。

<img width="420" height="282" alt="image" src="https://github.com/user-attachments/assets/4bfdfcb2-0c0d-437f-8bf3-24cf2a58ff9d" />

不行，4G改2G去了。-改完了，数据是连1G都没满，所以真的不能再降一下吗？

---

一会儿要赶车，所以快速叨逼叨两句。

昨天刷视频的时候看到一个关于生产端运维的内容。他们把 Claude tag 放进 channel 里做自动化告警响应，比如某个 API 成功率下滑了 2%，channel 里一旦有报警，Claude 就会自动做一些调查并把 PR 写出来，推给值班监控的人。值班人员扫一眼 approve 之后再合上去，之后还可以自定义让 Claude 监控随后 10 分钟的情况，确认稳定才算解决。(也顺手查了一下Claude tag的一些东西。我说怎么之前没刷到呢，首先它是今年 6 月份出来的，但在中文社区这边，其实是到 8 月初才渐渐有人讨论。最主要的是它确实有门槛，倒还不是 Claude Code subscription 这种门槛，而是它本身开通就需要 50 刀。-补充一下，它是因为那个 Cloud Tag 是给 Enterprise 和 Cloud Team 准备的。但是 Cloud Team 起码需要两个 seat，一个人是 25 刀，所以两个人就是 50 刀，这才有了这个 50 刀的门槛费。那我倒明白了为什么没有那么多人讲它，因为大多数人做的还是 to C 的东西，没有那么多 to B 的 team 在做这件事情)

由此衍生出来，我真的觉得在当今这个时代，运维这个活儿的本身的意义问题：incident到最后总得有一个人来兜底，而不能完全甩给 AI。因为 AI 还不太能理解 responsibility 或 reputation。一个人做运维，事情在自己手头上出了却没解决好，往小了说影响个人的 reputation 和职业 integrity，往大了说甚至会影响自我认同等一些微妙的东西；但 AI 完全没有这种概念。

我想到这个，也是因为之前做 diagnostic agent 的经历。当时为了图省事，让所有的诊断都按我的流程来跑：扫一眼看 Docker 还在不在、服务健不健康；如果健康但出了问题，就去找 Codex 排错。

所以，当时搭的工作流大概是：

• 第 0 层：单纯看 container 在不在跑，没启动就直接拉起来（如果起不来那肯定不能正常服务了， 就先重启， 重启三回还是不行那就是出大事了，需要去诊断）

• 第 1 层：让 Codex 比较底层的模型（比如 5.5 Luna）去做初步排查

• 第 2 层：让 Codex 的 Astra 去深度排查 - 补：这个得降级，没办法，Astra太耗token了，经不起这么消耗。

我看了一下报告，虽然显示出过几次问题，但也没调查出什么结果（就是有时候它真没事，就单纯是我这边觉得本地的HomeAssistant这个container没用，然后给它手动暂停。结果它那边显示说，某一个 container 莫名其妙暂停了 85 秒，然后没有分析出结果。但其实就是我手动关的，所以这真没事，确实没问题）。可能系统本身很简单也很稳定，很多时候只是分钟级别的偶发抖动，刚把 Tier 1 叫起来还没查出结果，系统自己就恢复了。跑了三天其实真没什么事，也没积累下什么东西。-补：后来让他给我搞了一个看板，每一分钟刷新一次，告诉我出了什么事。另外，我正在看Astra写的那个好长的 Diagnostic Agent design 文档，真的好长啊(不过文档写的是真好啊，真详实，每个字段代码在哪都写的清清楚楚，好久没看到这么舒服的技术文档了，用Astra写文档太值得了，虽然干掉了刚冷却好的5hour limit)。

不过重点在于，当我做这个的时候就意识到：如果用 diagnostic agent 去确保云端或本地的 ebbot 程序正确，那么再往下一层，谁来确保这个 diagnostic agent 本身是对的？如果 diagnostic agent 自己先挂了，那我自然就无法保证它负责的 ebbot service 是正常的。

这么一直往下递归是没有尽头的。不管再叠多少层逻辑判断或告警程序，最终还是得落到某一个人身上。无非是原本需要三四个人轮流每小时检查不同程序，现在变成一个人扫一眼汇总监控，只要它没告警，就默认后面一整串都是对的。

但无论如何，终究还是要落到人身上。不论是从工程实现还是 common sense 来看，运维都不可能无限靠堆更高的智能来彻底解决。所以讲到头，这个人还是来兜底的。不是， 是确保site security的。

anyway了，真得走了，错过又要等半个小时。

---

Grokbot 确实好使，真好使啊！它完美地解决了 ChatGPT token 不够用的问题。-另，之后跨越半个地球让家人用上了grok bot, 哇，登录上去了就不再依赖外网环境能用了，虽然会慢很多，但是能不跨越Great Fire Wall就已经很好了。以及， 360真该死啊，欺负中老年人不懂电脑，给装了一堆360系软件，广告一堆。

真好啊！一个完全隔离的小电脑。马斯克，你真的、真的、真的造福人类！另，火星那个事情麻烦抓紧点儿，去火星真的是我的人生课题之一。

在 Cloudflare 上搞了一个个人网页，全程用 Grokbot 帮我从注册账号开始弄的。

虽然它那个页面设计一开始搞得我脑袋疼，太丑了，第一版完全是想象不到的丑。不过现在这一版丑萌丑萌的，虽然我也觉得挺对不起观众的眼睛，但对我个人来说，我觉得记忆点比克制低调更重要，所以 I will go with this one。不过那个文案得改。现在起码这边的中文文案实在是太差劲了，太 AI 了，看得我脑袋疼。不行，这个得改，得改成说人话的版本。

而且我也不太乐意在这种个人网站上花太多时间，我又不是做前端的，所以还是把具体的事情做好吧。

但确实是丑萌丑萌的，大家会觉得一般 AI 的审美会做得很平均、很克制，尤其是偏技术向的那些，但你有点想象不到这是 AI 能整出来的活。

哦，顺手把 GitHub.io 的那个页面重定向到 Cloudflare 上的网站了。

https://clair-chen.yechenworking.workers.dev/

---

发现了一个他讲的我能听进去的宝藏 YouTube 博主，叫 Caleb writes Code (https://www.youtube.com/watch?v=XvmixEXPT3Q)。

很神奇的是，他讲事情的思维正好就是我思考的思维，即他是从最原始的问题开始讲起的，所以跟起来异常丝滑。

因为当我去理解世界的时候，所有东西都是一步步发展过来的。但我们现在看到的很多东西都已经是一个成熟的成品，前面已经经历了一大串各种各样的各个方向的探索和演进，我们看到的只是最终结果。

我在这方面一直有困难，很难接受直接把一个现成的成熟结果塞给我，上面带着各种各样的功能，然后跟我说"直接用吧/从这三个里面随便挑一个都能实现需求所以随便选"。（其实也有可能是单纯的智商不够记不住是干嘛的，所以需要拿其他信息辅助记忆。）

I found it really hard to understand what all the functions are used for, not to mention to analysis pros and cons. Due to knowledge limitations and experience, I really don't understand why there are so many diverse features, different tech, or things like that. To me, they all work the same.

It's more about: if I want to achieve something, between the toolsets and platforms I can use, there are multiple ways to achieve it.

For instance, if I want a program to be standby in the cloud, I can think of at least three solutions:

1. Fargate to run a Docker container
2. If the requests are really random, just use a Lambda function. Sometimes when requests are so infrequent, I don't even think it's worth a Fargate instance or keeping something running in the cloud to maintain it, so just use Lambda and call it when needed
3. An EC2 instance or an application server

Just because there are already so many things in the cloud or in any mature product, people might find it overwhelming. There are so many tools, but they often serve similar functions. For instance, S3, Databricks, and all the RDS services all serve as data storage in some way. They are all places to store data. So what's the difference? Why do people choose this instead of that?

Especially when I'm new to a field: I know there are multiple choices, but I don't know which to pick. Nothing feels distinctly different to me, so I couldn't understand why people prefer one over another.

But this YouTuber really explains things starting from the problem itself. Every practical advancement starts from a need, or you could call it a problem. It usually means the old way did not work: people face gaps, so they find a solution. That is generally how I take in knowledge.

When I look back, part of it might be that I just do not want to learn too many unnecessary things. On the flip side, that mindset makes it harder for me to deal with unfamiliar stuff. To me, reinventing the wheel is never a wise choice: if a wheel already exists, use it. Do not make it from scratch yourself. Whatever you write is likely not going to have the polish of something others have already battle-tested for years. There is no way, at least for me, to beat that.

Looking back at the code I wrote during university, it is a bit embarrassing. At that time, ChatGPT and all the modern coding agents were not prevalent or powerful yet. We might have been among the last students who wrote code using the ancient method, and I do not think the code I wrote back then was particularly useful. I had plenty of ideas and problems I wanted to solve with tech, but I was not smart enough. I got completely blocked by algorithms, especially mapping issues and maze problems (yep, I live in here for about two years, but still need to locate with Google Maps. Anything related to geo is super harsh on me.). That was one of the main reasons I retreated.

I really wanted to accomplish a lot in university, but between my limited capacity and having interests spread far too wide, I made nothing work. It felt ironic because around that time, an article about Stanford students caught my attention: it mentioned that students at Stanford felt they could hack anything. I really wanted to be that kind of person, but I could not. There were just so many programming languages to juggle: in school we started with C and C++, then Java, then I learned Python, plus front-end technologies like HTML , JS and CSS.

Looking back now at what happened in university, it always makes me realize it (the degree) was never designed to be that hard. It was just me being overly difficult on myself.

Sorry, this is getting so far off track. What I really want to say is that I like how this YouTuber illustrates things, starting with the problem. Because there is a problem, people make new things to fix it, and then another problem occurs, so people make even better things to deal with it. Layer by layer, the product, platform, or tool becomes the one we see today. It really helps me understand and remember why specific features are useful.

The world is full of buzzwords, especially in IT and finance. I understand why people in IT use buzzwords: to make their explanations more accurate or memorable. But at the same time, what they do in finance is just make people confused, which feels like a deliberate action. -I shouldn't say that. It is just really hard to memorize tons of new words, so sorry, that was just me complaining.

---

去查了chatgpt 的 agent api 的内容， 有些东西我觉得还是要先提一下。

我现在当前这个 Diagnostic Agent，我承认确实是很聪明地取巧了，直接用的 Codex CLI。所以当看到 ChatGPT 新推出这个 Agent API 之后，就去搜了这方面的内容。

我不确定后续的项目需不需要用到（因为毕竟是真的在用的东西，实用至上，写简历排第二；大概只会搭一个小的，跑通概念和流程即可），但为了防止以后忘了，还是先把能记下来的东西写在这里，当一个 note 用：

1. Sandbox

Normally when we use Codex, it maintains a sandbox on our personal computer. However, if we use the Agent API, there still needs to be a sandbox. This sandbox can be self-hosted, or it can be OpenAI-hosted. If we choose self-hosted, there are multiple ways to provide it.

The core principle about the sandbox is that it doesn't need to be so thorough or fully prepared before the agent session works. This is more realistic because we don't know what the agent needs when it actually runs. Preparing everything beforehand would be too complicated, tricky, and create a lot of friction before development. What the agent actually needs is just a platform or an environment open enough to install whatever it requires, while remaining under the environment's restrictions. This makes the whole sandbox setup much more flexible and practical.

2. Sub-agents
   
Based on the OpenAI documentation, the use of sub-agents and their maximum number can be controlled by parameters set by users/developers. However, the actual usage and decision to invoke sub-agents are determined by the main agent itself, not explicitly decided by developers, users, or any human being.

3. The naming of the API

I'm more familiar with HTTP APIs or traditional APIs, where user post a request and get a response (a 1:1 interaction). In that sense, calling this an "Agent API" felt confusing at first.

In practice, it operates as a session: when we post a request to the Agent API, we actually start a session. Within this session, there can be multiple turns, sub-agents, context compacting, and sub-agent orchestration, all handled by OpenAI internally rather than by ourselves.

This also explains recent commentary suggesting that companies focusing on agent orchestration over the past six months may see their value diminish. The LLM providers have built this natively, and naturally, they can execute it better than anyone else. They control the source, the infrastructure, and the inference process, so their advantage goes without saying.

- "AI Wrapper" 这个词是稍显贬义的，所以不要乱用。它是用来形容产品层面的词，而像 Prompt、Context Harnessing、Engineer 这些都是工程方法上的词，实际上更偏技术。但 Wrapper 那边，它是拿来跟一个纯的大模型（Large Language Model），或者说纯的 OpenAI API 去做对比的。再强调一遍，千万不要乱用，因为它确实带点贬义，是在暗示对方自己没有多少核心技术，只是在外面套了一层界面和一些 Prompt。不过从 Tech 角度来说，其实大家现在也都是这么做的，因为最里面的东西都是LLM API。 正所谓人和人之间的区别，比人和狗的区别都大，所以wrapper和wrapper之间，亦有优劣之分。

---

Diagnostic Agent 确实得大改。

看一下下面的截图，这是它当前的 health dashboard，里面根本给不出我需要的信息。

<img width="1064" height="350" alt="image" src="https://github.com/user-attachments/assets/ad786b51-4b02-49e0-a008-446e367866a5" />

具体来说，from my point of view, 看待 AI 或任何程序都有一个基本原则：它们必须是有用的。这个“有用”具体有两个定义：

1. 辅助人类决策：包括但不限于提供有效信息、过滤无关信息，从而减少人脑 context window 的输入消耗。
   
2. 创造价值：这比辅助决策更抽象，本质上是增加通向一个“有价值产品”的概率。这里的价值可以是声誉（名气上的价值，不管是面向市场还是身边的人），也可以是面向市场（To B 或 To C）的金钱回报，无论哪种都行。有些idea虽然精彩，但是因为其本身过于薄弱，很容易被原厂一个更新给推平，或者就是太atom了只能作为某个点存在而不是一个可用的东西，那也不能算是有用。

（比如在Claude code刚刚推出connector - 这个的记忆很清楚，那个时候就是因为 Claude Code 第一个推出可以连custom Connector的这个功能的，所以才从chatgpt 专去订阅的Claude Code - MCP 概念刚出来的时候，给Rize.io做的local mcp server -https://github.com/YeChen-coder/RizeIO-LocalMCPServer。 后来RIZE.IO这家公司自己推行了官方MCP， 那就没什么好说的了，那时候做的MCP已经落到历史的尘埃中了，回想其价值，只能证明那时候我的网上冲浪速度真的很快且执行力爆棚-他们用的GraphQL api， 这里面有很大的麻烦。它跟普通的 API 不太一样：常规的REST API 返回所有的值，本地再去拿所需的内容做 filter；但 GraphQL API 对服务端更友好，所以本地做请求必须写明要什么值，服务端那边才会给。现在想起来头还是会疼，主要因为他们那个各种文档、各种参数真的是巨长，而且那个时候 Claude Code 真的没有那么聪明，现在回想还是很折腾。但站在现在这个阶段，原厂都出了。我自己因为价格因素，也不再用 Rize.io 这个软件了，所以很多东西就流失在时间的星海长河中了。）

回到当前的 Diagnostic Agent，它的 visibility 做得很差：推给我大量内容，但我从中看不到任何有价值的信息。截图里只是其中两条，实际上每天都会产生十几条类似的内容，作用不大，反而加重了我的决策消耗。所以按这个逻辑，它必须大改。

另外还有一些历史遗留问题：这个项目在 ebo-engine 那边，不论是因为登录认证（authentication）的限制，还是项目本身的功能机制，它都是 exclusive 的。同一个时间，云端和本地基本只能存在一个，否则就会断联，视频流一断，自然呼吸之类的东西就跑不了。虽然冲突后果没那么严重，顶多断一会儿，但既然顺手要改 Diagnostic Agent 的页面，那就让 Astra 把这些问题都整合起来，给我加上切换和关闭的流程。

估计这是个大活儿，刚冷却好了 5 个小时的 limit，估计又要被干没了。

就是两边在出账单：一个是 AWS 云端那边，还有一个是 OpenAI Developer Platform 那边（大家 AI 的 token 消耗）。

现在我隔个两天就得上去看一眼，这样不太好。不过估计得等下一轮了，现在这一轮上面的活估计也就将将干完的样子。-还得往后退，因为整合log的优先级更高。

人的精力好贵啊，没睡好，导致连说话都不想说了，也不想打字和表达。

---

老大，我们的钱包有救了！

终于把本地跟云端的切换，以及本地+云端的不限于日志、incident response、diagnose 这些杂事集中在一个页面上了。

<img width="1078" height="587" alt="image" src="https://github.com/user-attachments/assets/8a7b1b0e-820e-4678-9e9c-25639d9c94ff" />

<img width="827" height="278" alt="image" src="https://github.com/user-attachments/assets/316c7405-502b-424e-a657-8cb0fa38f97a" />


我这边判断系统有没有问题，其实更多不是看基础状态。基础状态很好判断，Astra 早就帮我写得挺好的了；核心还是看功能实现。所以我去排错、判断它是不是真有问题，关键是看有没有回答：如果一天下来都没有记录，大概率就是出问题了。因此我也把本地和云端的 transcribed 记录都放到了这个页面上，终于舒服了。

这个其实对应了之前一直纠结的“有效信息”。实际上，Healthy Dashboard 迭代到现在已经是第三版了：

1. 第一版：单纯每分钟检查各项服务有没有开着。但那时 transcribe 相关的日志还得我自己去本地看。
   
2. 第二版：只涵盖了云端。但当时 transcribe message 甚至都没作为一项 log 打到 CloudWatch 里，所以本地更拉不下来看；而且加了 Diagnostic Agent 之后dashboard信息给得极多，但有效信息极少，看了根本无法辅助决策。

3. 第三版：总算能用了。目前唯独少了一个查账单的功能，不过理论上已经跑通确认了。因为我现在 weekly usage 只剩 7%，还有别的事要处理，等 Tibo 把 weekly usage reset 之后我再把这个功能补上。

这也让我有了一点思考。昨天看文章提到，在现阶段想让 AI 糊出一个看起来漂漂亮亮、挺有东西的界面非常容易，但能不能提供有效信息、甚至对“有效信息”的定义，始终掌握在真正使用它的人手里。这需要使用者不是出于 AI panic，而是真心想让事情起变化、想让流程更顺滑、减少无谓摩擦和决策损耗。

这也是为什么我不太愿意做那些脱离实际需求的 toy project：如果不去长期真实地使用，根本发现不了问题。尤其在自己不熟悉的领域，谁都不会对只用一两次的东西上心，投入产出比也不划算。只有一件事情需要重复做三次以上，且中短期内肉眼可见还会继续做，人才会自然地想去把整个流程自动化。

之前我也做过一些 toy project，发现确实没用。比如搞过一个针对简历的 RAG 项目，简历数据从网上找的开源库，流程跑通了，也学到了 tokenization 和 chunking 之类的技术，但我又不是 HR，筛简历对我的日常生活毫无用处，根本没有动力在深度上继续投入。

至于算命（八字、六爻）的 RAG，也只在我极度沉迷算命那阵子有点用。后来之所以丢掉了，主要是因为我根本没能力判断它输出的结果到底对不对。和AI agent 一样的逻辑，一个无法进行 verification 的东西，作用极其有限。

---

好的，这回是正式的真的是出问题了。

在进行从云端切换到本地的操作时，电脑这边其实有两三次弹出notification提醒 Tier 0 那边对 Realtime Assistant 的 Container 的 Docker health 的检查问题， dashboard上也显示assistant (即为realtime assistant 这个 container unhealthy), 但同时，docker 页面是正常的，意味着这个container在开着但是是里面的程序跑的不对了。 

查了一下，首先判断音频源连接 failed。而且这个音频源得一直往项目上推，哪怕对面是静音也得推静音，所以这肯定是出问题了。

<img width="982" height="130" alt="image" src="https://github.com/user-attachments/assets/e9fa3ad1-7c07-4331-8bad-7d74c3c550af" />

追查分析出来的原因是：在切换过程中，虽然程序里发了打开音频的命令，但机器人那边有延迟，比命令来的开的慢，自然就没收到这个命令。

所以也就是说，自从今天下午从云端切到本地之后，这三四个小时之内其实一直都没有收到音频。收不到音频，自然后续的一些程序以及 ChatGPT 那边的 response 就都无法生成了。

故障时间线（多伦多时间）：

1. 10:43–14:18 音频持续正常，约 72–73 kbps，累计收到约 112 MB。说明机器人麦克风和网络此前都正常。
2. 14:18:52，Realtime Assistant 检测到 RTSP 视频中断，调用唤醒和摄像头恢复。
3. EBO Engine 因此重建整套 Agora RTC 会话。
4. 14:20:35 新会话建立，但机器人直到 14:21:17 才重新加入。
5. Engine 的“20 秒后重发开麦命令”在 14:20:55 执行——早于机器人加入，所以没有作用。
6. 机器人加入后，Engine 只发送了一次开麦命令并重试订阅。订阅 API 返回成功，但之后始终没有：
   - audio track subscribed
   - first remote audio frame
   - ROBOT MIC OPENED
7. 视频随后完全恢复，但音频保持 0 bytes / 0 bitrate 至今。

这是第一个遇到的真正算得上问题的问题。改好了之后，也在当前这个项目里面加了一个 incident response 文件夹，里面放中英双语的 incident report。

其实它也证明了这边的 Diagnostic Agent （起码在搞不定了喊人这方面-powershell发notification）确实有效，虽然也只是 Tier 0。至于 Tier 1 和 Tier 2，因为都是 Codex 那边的，为什么没有触发到呢？很大原因是这几天对 token 的消耗实在是太大了，5 个小时 limit 一开就用没了，实在是没有 token 给他用。所以模型那边对 Codex CLI 根本就调用不起来，在一定程度上也导致了对这个事情的响应比较晚

去看了diagnostic agent log, 发现程序确实没毛病，问题一出就发现了而且很积极的在修反复recovered, 而且也确实是叫了tier 1的codex cli了，可是因为codex 额度是真的reach limit了，导致没有完成排查。

<img width="771" height="261" alt="image" src="https://github.com/user-attachments/assets/7a8393fa-5e0d-49c3-8e31-2cad25153278" />

<img width="776" height="593" alt="image" src="https://github.com/user-attachments/assets/88d53a35-88bb-42e6-92c7-0b3573152dec" />
