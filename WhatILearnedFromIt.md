# EBOAWSCloud Related

稍微吐槽一下。

我现在发现，其实 EBO Bot 去实现这个功能本身，要渡的劫已经在 local 的里理完了。即真正运行的这个程序，它的逻辑，怎么实现交互等等我已经理得差不多了。

但是上云之后，首先云上这套东西本身的权限就是一道事儿；而且又加了一个 diagnostic agent。现在这锅粥挺复杂的，感觉最大的复杂度还是在这个 diagnostic agent 上。因为不管它里面是用哪个 model、用什么 agent 还是别的什么，反正只要它有权限能自己去做一些操作，就得给它配上安全网，不能让它在宿主机上乱搞。由此就引发出了很多很多的限制。哦，然后同样是因为它现在有两大环境嘛，所以你 local 这边得限制一次，然后 AWS 那边也得限制一次。不过，甚至说 AWS 那边是好搞的，因为它一个 platform 本身就已经是给了一些，就是用 RBAC 还是用 least privilege 这些作为一个安全网，它本身就是有一个标准的东西的。但是本地上真的从头搞。

| ID | Bullet 原文 + 中文意思 | tags 在说什么 | 实际上你做的是什么 / 该怎么理解 |
|---|---|---|---|
| **01** | **“Migrated the EBO Engine and Realtime Assistant from a local Docker Compose deployment to two containers in a single AWS Fargate task in ca-central-1…”** 中文：把原来本地 Docker Compose 的 Engine 和 Realtime Assistant 迁到 AWS Fargate，一个 Task 里跑两个 container；Home Assistant 仍留本地。 :chatgpt-content-reference{index="1"} | `aws fargate / ecs / cloud migration / hybrid architecture` | 这条非常直白。你原来 EBO 全在本地，后来把两个核心服务搬 AWS，但 HA 留家里，所以形成 local + cloud hybrid。**这是“云迁移”能力，不是什么额外的新技术。** |
| **02** | **“Generated the AWS environment through Python-maintained CloudFormation covering a VPC, two public subnets…”** 中文：用 Python 维护/生成 CloudFormation，里面定义 VPC、两个 subnet、route、SG、ECS、ECR、EFS、Secrets Manager、IAM、CloudWatch。 | `CloudFormation / IaC / Python / VPC / ECS` | 你不是手动在 AWS Console 一个个点，而是项目里有 `make_template.py` 和 CFN template。所谓 **Infrastructure as Code** 就是这个。 |
| **03** | **“Refactored inter-service addressing to use same-task localhost networking…”** 中文：因为两个 container 在同一个 Fargate Task，调整了服务之间的地址，让它们通过 localhost 通信，并修复端口冲突和 WAV fallback URL。 | `container networking / localhost / troubleshooting` | 原本 Docker Compose 的 hostname/port 逻辑搬到 Fargate 后不完全一样，你为了云端架构改过地址。这就是所谓 **container networking**，不是你专门学了一套复杂网络系统。-补充一下那个 WAV fallback URL，意思就是它播放音频的那个 WAV 往哪找。因为 OpenAI 那边的模型出来的是音频，不管是完整音频还是断断续续进来的流式音频，发给 EBOBot 那边播放的时候都得给它一个 URL，所以这个 URL 就是所谓的 WAV fallback URL |
| **04** | **“Designed an outbound-only Fargate network with no public inbound rules, NAT Gateway, load balancer, or ECS Exec…”** 中文：云端只需要主动往外访问，不开放公网 inbound，也没用 NAT Gateway、LB、ECS Exec，而是 Task public IP 做出站。 | `VPC / network security / cost optimization / least privilege` | 这实际上是一个**很简单但合理的网络取舍**：机器人和 OpenAI 都是你的服务主动连出去，所以没必要接受互联网请求。`least privilege` 在这里是抽象出来的安全原则。 |
| **05** | **“Provisioned separate encrypted EFS access points for the Engine and Assistant…”** 中文：Engine 和 Assistant 各自使用 EFS Access Point，启用传输加密和 IAM authorization，并没有把过去家庭对话/媒体全部复制上云。 | `EFS / encryption / IAM / privacy` | 就是两个 container 需要持久化文件，所以用了 EFS；又给它们分开目录/Access Point。后半句是数据隐私边界。(为什么 EFS？
→ Fargate Task 会被替换，需要持久化数据。为什么两个 Access Point？→ Engine 和 Assistant 的数据尽量分开，不让两个应用共享整个文件空间。为什么 IAM + encryption？→ 限制谁能访问，并加密 Task ↔ EFS 的传输。) |
| **06** | **“Injected bootstrap configuration through AWS Secrets Manager…”** 中文：启动配置通过 Secrets Manager 提供；检查两个服务 token 是否一致；初始化完成后把大块 bootstrap payload 从子进程环境变量移掉。 | `Secrets Manager / configuration / credential handling / input validation` | 这不是复杂 secret platform。核心就是：**敏感启动配置别硬编码进 image；启动后也别一直把整块配置留在环境变量里。** (注意这边的 service token，指的是我自己的两个服务之间通信用的内部密码，跟类似 OpenAI 那边的 API key 完全没关系，也跟 Ebo Bot 那边的账户密码完全没关系。具体而言，它是 engine 和 assistant 之间互相认证用的：他们之间有内部通信，需要互相认证-engine 需要把图像传给 assistant + assistant 同样需要把音频的 URL 传给 engine。 这个就有点像一个密码一样的关系，也可以理解成钥匙吧，就是大家都有一样的钥匙。这个盒子本身在传出去的时候是被锁上的。接收方那边拿到这么一个被锁上的盒子（或者说 package，别管这是一个什么东西了），他得把它打开。怎么打开呢？用的就是这个共享的 token。 既然谈到这里，而且我们确认 token 可以存在 Secrets Manager 里，这边就得再说明一下背景。因为 token 本身是非常敏感的信息：• 首先肯定不能硬编码在程序里，否则源代码直接泄漏就完蛋了。• 其次也不能打进 image 里，因为 image 本身可以作为一个独立的 artifact 存在，别人拿到 image 一看也能知道 token 是什么。所以放在哪里都不保险，最终才决定统一存在 AWS Secrets Manager 里面。不过现在云端那边的实现方式其实有点太周折了。目前的情况是：1. 云端先启动一个 wrapper。2. 从 Secrets Manager 里拿到 token，生成一个原应用能识别的 config 文件。3. 接着 agent 和 assistant 这两个服务各自去读自己的 config 文件，然后再正常启动运行。其实完全没必要绕这么大一圈, Engine 和 assistant 是可以自己分别去调用一遍 AWS Secrets Manager SDK，每个service把 token 拿出来。但这样的话，要改的代码实在太多了。所以当时做迁移的时候，为了以简洁明快为主，就直接不折腾这个 SDK 了，所有人都以自己的 config 为主，仍然保留了一切以 config 文件为准的逻辑。 “初始化完成后把大块 bootstrap payload 从子进程环境变量移掉” 这句话在这里专门提，是因为环境变量会被子进程继承。Wrapper 那边确实需要这些 bootstrap 配置来做初始化，但在启动真正的 Engine 和 assistant 这两个服务的时候，完全不需要把原来那些东西放进去，因为子系统根本用不着。所以这边提了一嘴，只把 payload 相关的配置作为环境变量继续传给子进程，避免把无关的东西透传下去) |
| **07** | **“Published independently built Engine and Assistant images to ECR using immutable tags and digest-pinned task definitions…”** 中文：分别构建两个镜像放进 ECR，tag 不允许覆盖，并用 digest 固定 TaskDefinition。 | `ECR / immutable deployments / release engineering / rollback` | 核心概念：部署的镜像版本不能悄悄被同名 tag 替换。digest 能准确指向某一份 image。**“release engineering” 是对这个行为的职业化叫法。** (我把 EBO 的两个 Docker service 发布到 ECR。为了避免同一个 image tag 后续被覆盖，我把 ECR repository 配成 immutable。发布脚本 push image 后还会读取 ECR 返回的 image digest，然后生成 digest-pinned image URI，所以 ECS 部署时可以明确绑定到一个具体的 container image，而不是依赖一个可能变化的 tag。这样版本追踪和 rollback 会更可靠。) |
| **08** | **“Built a staged deployment toolchain for provisioning, configuration, image publication, preflight validation, service start and stop, status inspection, and rollback…”** 中文：把 provision、配置、publish、preflight、启动停止、status 等做成脚本化步骤，而不是全部手点 Console。 | `deployment automation / devops / preflight / rollback` | 这里 `deployment automation` 没问题。但我们之前已经发现：**你没有一个真正独立的自动 rollback command**，更准确是“有脚本化部署 + documented rollback procedure”。这条现在略写重了。 |
| **09** | **“Pre-provisioned the ECS service at desired count zero…”** 中文：先把 ECS Service 建好但 `desiredCount=0`，部署参数 min healthy=0/max=100，切换时先停旧的再开新的，避免两个 Engine 同时登录机器人。 | `deployment strategy / single-instance workload / change management` | 为什么这么麻烦？因为机器人账号只能让一个 Engine 占着。(这里我补充一下为什么有这个要求：主要是这边测试过，如果两台设备或者两个服务使用同一个账号去登录，虽然能登得上，但会导致另一台设备掉线。具体的表现是它不会被直接踢掉，如果开着就还会一直开着，但下次要登录时就得重新登，之前的登录状态就没了。因为这里要求唯一性，所以为了防止云端搞两个 task 来保证 robustness，导致两边互相抢连接（一会儿你连着、一会儿我连着），这种情况是绝对不能发生的。因此这边做了限制，为了预防问题，一开始的 desired count 也只能是 0)**这不是常规高可用 deployment，反而是为了保证永远只有一个实例。** |
| **10** | **“Created cloud preflight and verification checks for resolved configuration, Secrets Manager access, EFS read/write behavior…”** 中文：部署前后检查配置解析、Secret、EFS 读写、离线启动、SDK、health endpoint 等。 | `preflight / integration testing / deployment validation` | 简单理解：部署 AWS 之前先自动检查“这些东西是不是基本都能工作”，避免启动以后才发现 secret/EFS/SDK 坏了。 |
| **11** | **“Separated ECS process liveness from application readiness and business health…”** 中文：不把“进程还活着”当成“EBO 正常”；另外检查 Realtime、video、transport audio、真实 microphone packet/PCM。 | `liveness / readiness / business health / observability / SRE` | 这是一个很值得保留的点。比如 Python 进程还在 ≠ 摄像头还在传画面 ≠ 麦克风真的还有数据 ≠ OpenAI Realtime 还连着。所谓 **business health** 就是后面这些更接近真实功能的检查。（这个是真的非常需要，因为它是受制于硬件限制，或者说第三方厂商的硬件限制。毕竟 EBOBot 它也不是我生产的，我也不知道原厂商给它配了什么稀奇古怪的配置，这就导致会多出来很多这种状况。所以它最好能有多一些这种保全措施，最好能多排查一下。） |
| **12** | **“Added graceful SIGTERM handling and made the Assistant exit when required worker threads terminate…”** 中文：ECS 要停服务时能正常处理 SIGTERM；关键 worker 挂掉时让主进程也退出，让 ECS 真正发现故障并重启 Task。 | `graceful shutdown / process supervision / fault recovery` | 如果 worker 死了但 Python 主进程还装作活着，ECS 不知道有问题。这条就是解决这个。（这个主要是因为场景里面还是有点复杂，导致有听音频的、收视频的，还有各种推流之类的处理。在 Python 的这个主进程里面，其实有很多个不停运行的 thread，也就是很多个 worker 在做不同的事情。这些 worker 一个都不能死，一旦死了一个，程序就无法正常跑了。所以如果发现里面有一个关键 worker 真的挂了，就必须让 main process exit with failure。至于怎么停：首先得是SIGTERM graceful shutdown，不能直接把电源拔了，它停下来也是有一套流程的，所以这边才会用这个机制。另外 startup grace 那个配置，是因为正式测下来起码得过个 30 秒：从你点下启动、把整个服务拉起来开始，起码要 30 秒，所有音频、视频流才能正常流入，所以必须得给它留一个 warm-up 的时间。） |
| **13** | **“Wrapped application output as structured JSON with schema version, UTC timestamp, service, boot ID…”** 中文：日志变成统一 JSON，有时间、service、boot ID、event、severity 等字段，同时做敏感字段过滤。 | `structured logging / redaction / observability / privacy` | 就是把原来散乱 `print()` 日志变成机器更容易搜索/分析的 JSON。`boot_id` 可以知道日志属于哪次启动。 |
| **14** | **“Combined CloudWatch application logs, Embedded Metric Format health metrics, AWS/ECS service metrics, and Container Insights…”** 中文：把应用日志、EMF 健康指标、ECS metrics、Container Insights 一起用于部署验证和排障。 | `CloudWatch / EMF / Container Insights / metrics / RCA` | 这里没有一个神秘的“observability platform”。就是你实际看了这几类 AWS telemetry，然后联合判断是 container 问题、媒体问题还是模型连接问题。 |
| **15** | **“Added structured CloudWatch events for final user transcripts, final model replies, connection lifecycle…”** 中文：把最终 transcript、模型回复、连接/恢复/session rotation/health change 写成结构化 CloudWatch event，并设置 14 天 retention。 | `LLM observability / event logging / retention` | 可以理解为：云端以后出了问题，不只看到 CPU 内存，还能知道 Realtime 当时发生了什么。不过真人完整端到端体验的验证没有 bullet 给人的感觉那么强，因此面试时不要夸成“production-grade conversation monitoring”。 |
| **16** | **“Investigated an Enabot login timeout after CPU right-sizing and restored service through an audited replacement of the exact observed task…”** 中文：降 CPU 后出现 Enabot 登录 timeout，你定位到具体 Task，再受控 replacement，并确保不会两个 Engine 重叠。 | `incident response / investigation / controlled recovery / audit` | 这是一次**真实发生过的云端 incident 操作**。注意：你解决了故障，但**没有证明 CPU 降配就是 login timeout 的根因**。所以 tag 里的 `root cause investigation` ≠ 已经找到 root cause。（这个他没查出来，我知道是为什么。其实跟刚才说的“两个设备不能同时连”对上了：当时我用手机登录了，而且挂了蛮久，导致云端那边被 log out 了；但我手机这边连接一直保持着，所以云端就在不停尝试重新登录，肯定就登不上去。这跟什么 CPU 降速没有任何关系，只能说明它这边有自动机制，当发生 fatal incident 时，就能够自动进行 replacement 来尝试解决问题） |
| **17** | **“Right-sized the Fargate task from 2 vCPU and 4 GiB to 1 vCPU and 2 GiB after reviewing approximately 65 hours of telemetry…”** 中文：看了约 65 小时数据和约 320 MiB 内存峰值，把 Fargate 从 2vCPU/4GiB 降到 1vCPU/2GiB。 | `right-sizing / capacity planning / cost optimization` | 这个就是很典型的 cloud engineering：**根据实际 telemetry 判断资源明显给多了，再降规格。** |
| **18** | **“Reduced estimated Fargate compute cost from approximately $79.26 to $39.63 per 730-hour month…”** 中文：按照当时价格和每月 730 小时估算，Fargate compute 从约 $79.26/月降到 $39.63/月。 | `FinOps / AWS pricing / cost optimization` | 这里最重要的是 **estimated**。不是 AWS 账单已经连续几个月证明节省了 50%，而是按照 pricing model 算出来的。 |
| **19** | **“Built read-only cost inventory and pricing tools to model Fargate, CloudWatch, data transfer, EFS, AWS Backup…”** 中文：写了只读成本调查工具，把 Fargate、日志、网络、EFS、Backup 等费用因素拉出来分析，不改资源。 | `FinOps / cost analysis` | 所谓 **FinOps** 在你这里其实就是：把云资源实际用量/价格结构算清楚，然后决定哪里值得优化。不是说你成为了专业 FinOps Engineer。 |
| **20** | **“Implemented an on-demand cloud evidence collector that normalizes ECS events, running and stopped tasks…”** 中文：做了一个按需诊断采集器，把 ECS event、运行/停止 Task、exit reason、CPU/内存、有限日志整理进 SQLite/JSONL/JSON，并加 evidence ID。 | `diagnostic pipeline / SQLite / JSONL / evidence management` | 这是从“普通运维脚本”开始过渡到 Diagnostic Agent 的关键点：**先机器化收集证据，再让后面的诊断逻辑使用这些证据。** |

第 21 条想说的就是 recovery first。我做了一个 diagnostic agent，里面分了 Tier 1 和 Tier 2，都是用 Codex CLI 去做证据收集和诊断。但真正在跑项目的时候，谁也不会一开始就直接把 model agent 叫起来，不管是从经济角度还是实用角度都不合适。不能人家单纯是 Docker 挂了，第一件事不按直觉来：肯定得先把 Docker 叫起来，把 container 重新拉起来，看它能不能正常跑；而不是让 OpenAI 自己去长篇大论调查，现在没人这么干。所以 Tier 0 一律要求先把这些 health checks 基本排查跑一遍，排不出来再去叫 Codex CLI 往下走

第 22 条涉及到一个权限分离，就是讲一个低权限的东西，然后怎么去拿高权限的事情。我这边直接自己写了一个程序叫 host bridge。因为我们这个 diagnostic agent 本身集成了本地和云端诊断两种能力：1. 云端那边大部分还好说，直接拿权限的 role 或者 permission 都可以干了。2. 本地这边，比如我这个 Docker 它在宿主机上跑，所以就需要做一下限制。这边限制的具体实现就是用 host bridge。但 host bridge 这个东西说来话长了，估计我会新写一篇，反正现在先往下推吧，现在先不讲 host bridge 了

22 是“架构层面的权限分离”，23 是进一步把这种思想落实到 Docker 配置。
这里的一堆词不需要死背，核心就是：
“即使 Codex Worker 出问题，我也尽量限制它能造成的影响范围。”
比如：
non-root：模型进程不是管理员。
read-only filesystem：不能随便改自己的基础系统文件。
capabilities drop：减少 Linux 进程拥有的特殊权限。
PID / CPU / memory limit：模型失控也不能无限吃资源。
no Docker socket：不能直接控制整个 Docker 环境。
control / analysis network 分开：负责执行动作的组件和只负责分析的组件不是全部混在一张网络里。
所以它本质是一个 blast-radius containment，也就是“限制故障或模型错误的影响范围”。

第 24 条：Local / AWS Adapter 抽象
英文原文：Defined interchangeable local Docker and AWS ECS/Fargate adapters behind snapshot, evidence, prepare-restart, and restart interfaces, while enforcing a single active runtime environment to prevent dual robot ownership.中文：在统一的 snapshot、evidence、prepare-restart 和 restart 接口之后，实现了可替换的本地 Docker 与 AWS ECS/Fargate Adapter，同时强制只允许一个运行环境处于活动状态，避免本地和云端同时争抢机器人控制权。
你的 Diagnostic Agent 要面对两种环境：
本地 Docker 和 AWS ECS/Fargate。
但是你不想让上面的 Controller 写成：
“如果是 local 就执行 A，如果是 AWS 就执行 B，如果以后再加环境就继续 if/else……”
于是你统一抽象出几个操作，例如：
snapshot：现在状态是什么？
evidence：给我诊断证据。
prepareRestart：如果要重启，先检查能不能安全执行。
restart：真正执行恢复。
上层 Controller 不需要知道下面到底是 Docker 还是 ECS。
另外还有一个 EBO 特有的问题：同一个机器人账号不能本地 Engine 和云端 Engine 同时连接。
所以系统还要保证：
Local active → AWS 必须停。
AWS active → Local 必须停。
这个就是 single active runtime environment。


