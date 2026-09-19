[Chinese original](ShootToTheAWSCloud_zh.md)

This is a record of the chain of problems and solution research triggered by two related efforts: building a diagnostic agent for the operations side of this project—yes, a project for the project, intended to keep the current system stable—and migrating the application to AWS.

An early update: after adding the diagnostic agent and connecting it to the cloud deployment, the new work diverged too far from the project currently published here. I initially thought that opening a branch in this repository would not be ideal and planned to create a new repository once the work was ready. Then I changed my mind because having too many repositories was becoming annoying. Final decision: the `main` branch of this repository now contains the latest version with the diagnostic agent. The cloud version does live in a separate repository because it addresses a genuinely different problem. The earlier application-only version without the diagnostic agent is preserved in the `archive/main-before-local-diagnostics-2026-09-17` branch of this repository.

---

AWS released AWS DevOps Agent this year, and it carries considerable authority in the industry. The AI's summary was that everyone is copying the pattern. After reading AWS's material, I can see why: the collection of inputs and the architecture itself function like a knowledge graph.

AWS DevOps Agent can perform automatically triggered investigations; a human does not need to open it manually every time. AWS currently supports several entry points: built-in ticketing and incident integrations, webhooks, and manual starts. Its documentation explicitly describes investigations triggered by events such as PagerDuty tickets and Grafana alarms. It can investigate using observability data from CloudWatch, Datadog, Grafana, New Relic, Splunk, and other sources. In rough terms, AWS DevOps Agent is an AI SRE and diagnostic engineer priced at about USD 29.88 per active-agent hour.

In practice, however, nobody starts AWS DevOps Agent the instant any small incident occurs.

The process has tiers. Tier 1 begins with CloudWatch alarms, usually triggered because a metric is abnormal, a log reports an error, or some data looks wrong. A simple preliminary assessment decides whether the event deserves escalation into an incident. Sometimes the network stalls briefly or another transient problem occurs. The cause may be nothing more than a cloud provider hiccup that resolves almost immediately. Many alerts are false positives and can be filtered out directly. Investigation becomes necessary only when the problem persists or is severe; there is a threshold for escalation.

DevOps Agent is used only when the incident genuinely requires more advanced intelligence, or when existing runbooks and past cases are insufficient.

Another advantage is parallelism. An investigation may produce three or four possible causes: a deployment that just completed, a database failure, or any number of stranger possibilities.

As an aside, this is also why I prefer a Fargate task over renting an EC2 instance, installing Docker, and running the two EBO Bot containers there. Their operational complexity is different. If I also had to monitor and troubleshoot Linux itself, I would not have enough attention left—and operating Linux is not the point of this project.

A human investigator is effectively single-threaded and cannot investigate every possibility at once.

An agent, by contrast, can be treated as an auto-scaling system. Its architecture can expand intelligently and investigate three, five, or even a dozen possible causes in parallel, then aggregate the results.

That kind of intelligent scaling is an area where AI decisively outperforms humans.

---

Wow, Codex is smart. Two completely different projects were running at the same time, and it still discovered that my task could not proceed because another active task had taken over the required services:

> Root cause identified: another running task, “Research AWS Fargate Diagnostic Architecture,” is carrying out the cloud cutover you authorized. At 23:18:39 local time, it issued the commands that stopped the local Engine and Assistant. Docker events also recorded the corresponding SIGTERM signals and clean exits.

I had not even told it that the two tasks might conflict. It found the conflict by itself. Can humans really continue competing with AI?

---

CloudWatch Agent is designed for EC2 instances. With Fargate and ECS, there is no accessible host machine, so the agent cannot simply read host logs or be configured in the same way.

I also have a complaint about CloudWatch Log Management: it is so detailed that readability suffers.

A local log is straightforward: a timestamp followed by the actual message. CloudWatch includes a large amount of additional information. That information is useful during a deep dive, but it sacrifices everyday readability.

After scrolling through half a page, I may see only seven or eight actual messages. The detail has value, but it feels extremely redundant. AWS, would you consider a compact view? Then I realized that AWS never intended humans to read every raw message. Features such as anomaly-detection configuration already exist precisely because people are not expected to inspect the raw log stream line by line.

---

Calculating the bill gave me a headache. Fargate was the cost I had prepared for, but every large and small supporting service also costs money. At this point, buying a Raspberry Pi and running everything locally began to look attractive. My head hurt.

The following estimate assumes 1 vCPU and 4 GiB of memory, with all other resources and measured transfer rates unchanged, using on-demand pricing. Official unit prices came from the [Fargate regional price index](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonECS/current/ca-central-1/index.json), [CloudWatch regional price index](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/ca-central-1/index.json), and [VPC regional price index](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/current/ca-central-1/index.json).

| Cost item | Quantity and unit price | Estimated USD/month |
|---|---|---:|
| Fargate CPU | 1 × 730 hours × $0.04456/vCPU-hour | **32.53** |
| Fargate memory | 4 × 730 hours × $0.004865/GiB-hour | **14.21** |
| Public IPv4 | 1 address × 730 hours × $0.005/hour | **3.65** |
| Container Insights Enhanced | 212 active time series × $0.07/metric-month | **14.84** |
| Custom application metrics | 4 × $0.30/metric-month, before the free tier | **1.20** |
| Two application log streams ingested | About 0.355 GiB/month × $0.55/GB | **0.20** |
| Application and performance log storage | Application logs retained 14 days; performance logs currently retained 1 day; conservative uncompressed-byte estimate | **Less than 0.01** |
| Private ECR image storage | About 0.53 GiB × $0.10/GB-month, rounded up | **About 0.06** |
| Secrets Manager | 2 secrets × $0.40/month | **0.80** |
| EFS, backups, small numbers of key and secret requests | Current file volume is very small; see the growth model | **About 0.01 or less at current scale** |
| **Subtotal above, excluding Internet egress** | Before the CloudWatch free tier; line items rounded | **About 67.50** |
| Network egress: shared 100 GB free allowance available | Estimated from the task's observed send rate | **About 9.7–11.1** |
| Network egress: free allowance exhausted by other resources | Same traffic at full tiered pricing | **About 18.7–20.1** |
| **Total with free egress allowance available** | | **About 77–79** |
| **Total without free egress allowance** | | **About 86–88** |

---

The local diagnostic agent was assembled with two tiers:

1. **Tier 1:** Use an API key or run a less capable Codex model.
2. **Tier 2:** Use Codex's Astra model.

If neither tier can solve the incident, the system should find a way to notify a human. Telegram Bot is the most readily available notification channel for me, although I had not implemented it yet because it was not the priority. The immediate goal was to make the agent loop work reliably.

Unfortunately, Codex Astra consumes an enormous number of tokens. It cools down for five hours and then spends the allowance in less than ten minutes. For at least the next few days—probably three—there was almost no Codex capacity available for the diagnostic agent. I would have to squeeze out whatever I could.

Why does everything require tokens? I do not like it.

Because local and AWS cloud versions now coexist, I also created a role with permission to read the monitoring data produced by the cloud version and connected that evidence to the diagnostic system.

---

Because this work involved agent architecture, I studied the logic behind `pi-agent` and compared it with Codex. Its philosophy is deliberately minimal: retain only the essential modules and let developers customize everything else. Add whatever you need; otherwise, keep it simple.

I understand why that design exists. Some users believe frameworks such as Codex or Claude Code are too large and include many features added by model providers that a particular task does not need. From the perspective of token efficiency, the approach makes sense.

I simply do not have a comfortable use case for it:

1. Even a diagnostic agent needs strong analytical ability and a mature harness. This may be only a personal project running on AWS, but I do not want a poorly designed agent loop—with weak permission controls, insufficient file isolation, or another overlooked detail—to break the cloud system and leave me with the repair work.
2. Financial use cases involve my very real money and demand even stronger analysis, making them an even worse match for a minimalist agent framework.

After thinking it through, I could not identify a cleanly isolated, simple use case. Most purely simple tasks can already be handled by the ChatGPT web app. Even small monitors, scheduled tasks, and notification jobs are well covered by ChatGPT, so that part of the use-case space is already occupied.

This may sound like an overly broad claim, but I think the reason is that I build things to achieve an outcome.

From the very beginning, I build something because a need exists. The need appears because I encounter a problem while doing something else and want to remove it. The problem can be anything: I am too lazy to write more, I do not want to check items one by one, or the task itself is simply annoying. Those are all real problems, and solutions arise from them. Every tool I have built—and especially every tool I did not quickly abandon and still genuinely use—addresses a specific problem.

As a result, the goal of these projects is not to build a project for the sake of learning its architecture or technology. The goal is to produce a concrete effect.

That resembles OpenAI's emphasis on success criteria. My interactions with Codex work the same way: I explain the problem, say what feels wrong, describe the result I need, admit that I do not know how to get there, and ask it to make the result happen.

I also know that my own knowledge is limited. Any architecture or solution I prescribe is constrained by what I have previously seen and is usually neither the industry's standard pattern nor its latest work. “Man is the measure of all things” applies here mainly to the user experience.

In the AI era—when most people can spend more energy discovering information—it may be better not to seek a sense of control through a project's implementation details or architecture.

People get tired and accumulate decision fatigue. Racing after the sun has no finish line; perhaps the race should never have begun.

This is especially true in IT. Once coding agents arrived, everything accelerated. Traditional industries may retain stable knowledge for longer, but IT seems to receive an atomic bomb every three days and a shocking new development every two. The replacement cycle has become too fast for an individual human to follow.

---

The cloud logs needed to change. They did not emit transcripts to CloudWatch, which made operational monitoring much harder because Logs Insights could not search them.

Astra burns tokens like water. I asked it to write one document and—whoosh—“5-hours limitation reached.”

---

Oh ocean, you are made entirely of water; oh Astra, you are made entirely of smoke. The allowance had just cooled back to 100%, and one instruction consumed 41% in a puff.

The new logs were added.

They now include the final user transcript; the model's final response text and correlation ID; response completion, playback failure, fallback, and interruption events; connection loss, transcription failures, and file-save failures. After deployment, all of these events are available in CloudWatch under `/ebo-cloud/assistant` and retained for 14 days.

Seriously, Tibo? During validation, it announced that it had “hit my limitation” and simply stopped.

Please finish the validation before abandoning the job. A later update confirmed that the logs were visible. For example:

```json
"source_timestamp": 1789201821.5552154,
"transcript": "Yes, I heard you. I heard you ask, ‘Can you hear me?’ If you want me to confirm whether there are other sounds in the room, you can give me a more specific and clearer prompt—for example, whether you want to know if someone is speaking or want me to listen for a particular sound source. I can listen again and help you check.",
"transcript_chars": 103
```

---

I thought that my earlier experience with trading had trained me to think more rationally. I discovered that it had not. At most, I had learned to recognize when I was experiencing FOMO.

The effects of FOMO remained.

Fragile humans. Perhaps allowing AI to rule the world truly is the wisest solution, discovered only after a sage crossed three thousand worlds.

Tonight I take my lantern and sleep; let tomorrow's flood come if it must.

An update one day later: people are weak and their condition fluctuates dramatically. Trust the stop-loss line you set for yourself.

The circumstances differ, but the meta-problem is the same. Until a method exists to resolve it, the issue returns again and again. Humans have never been rational; do not begin by assuming that they are.

---

OpenAI released another Chat model. I skimmed the announcement and decided not to change anything. I still needed Realtime 2.1 Mini because I remained committed to visual input.

That requirement is also the main reason I kept saying Fargate was painfully expensive without reducing the deployment further or scheduling it to turn on and off. Standby availability is the project's core experience.

My parents have regular work schedules, but their actual movements are often flexible. I want them to feel that something is always present at home rather than available only within rigid time windows.

In theory, I could install an infrared sensor at the door and start the system when someone enters. That would require new hardware, however, and I am not at home. My parents could not maintain it, and if it failed, I could not repair it remotely. I want to avoid disturbing their lives as much as possible. Unfortunately, leaving Fargate running and paying for idle time still gives me a headache.

Yesterday—or perhaps the day before—I saw that ChatGPT had released a new Agent API. I think there is enormous potential there.

---

Yesterday, I watched a livestream from China's DevOps community in which Tencent engineers discussed their experience deploying operations agents.

Last year, their work was still largely in the “telling an AI story” phase: isolated AI experiments, such as handling a particular incident. This year, they have moved into real deployment. The system is beginning to look mature, including digital counterparts and workflow execution.

One clear use case for an operations agent is answering urgent, fixed, well-defined questions. I may not be using the most professional description, but I mean questions from a development team such as, “Is the current release ready?” or “What is the status of this service?” The agent retrieves the relevant information—from data pages, APIs, or other sources—and answers directly.

Their internal architecture uses one main agent and many sub-agents. The main agent classifies the request and dispatches it to the appropriate specialized sub-agent.

I expect mature products of this kind to appear quickly. For small and medium teams or low-complexity architectures, the solution should be relatively achievable. The world always contains smart people who can build it. I am simply lazy and would prefer to copy an existing solution—no, to reproduce a great idea.

One more thought: the livestream strongly emphasized the concept of “AI labor hours.” I did not think deeply about it from a technical perspective at the time, but it matters inside a company or organization. Individual developers may find the metric unnecessary. In a company—especially within a business unit—results need visibility and must be reported upward, and then farther upward. “AI labor hours” capture both the tokens spent by the AI and the value of the human time used to build the system. Organizations need a way to express that value, demonstrate a positive return on investment, and justify continuing the work.

---

Infrastructure is expensive. It is genuinely expensive. A single Fargate task with 1 CPU and 4 GB of memory cost five dollars after only two days. My head, wallet, heart, and blood pressure all hurt.

<img width="420" height="282" alt="AWS infrastructure cost" src="https://github.com/user-attachments/assets/4bfdfcb2-0c0d-437f-8bf3-24cf2a58ff9d" />

No. I reduced the memory from 4 GB to 2 GB. After the change, usage did not even reach 1 GB. Could I reduce it again?

---

I had a train to catch, so I wrote the next thoughts quickly.

The previous day, I watched a video about production operations. The team placed a Claude tag in a channel to automate alert response. If an API's success rate dropped by 2%, an alert in the channel caused Claude to investigate automatically, prepare a pull request, and send it to the person on call. The operator could review and approve the PR, merge it, and then ask Claude to monitor the next ten minutes. Only a stable result counted as resolution.

I also looked into the Claude tag itself. I had wondered why I had not encountered it earlier. It launched in June of this year, but Chinese communities only began discussing it gradually in early August. The largest barrier is not a Claude Code subscription but a USD 50 minimum cost. The feature targets Enterprise and Claude Team customers. A Team workspace requires at least two seats at USD 25 each, creating the USD 50 entry price. That explains the limited discussion: most developers build consumer products, while far fewer business teams are working on this type of system.

This led me to think about the meaning of operations work in the current era. Ultimately, a human must remain accountable for an incident; responsibility cannot be handed entirely to AI because AI does not really understand responsibility or reputation. When an operations engineer owns a system and fails to resolve a problem, the consequences may range from damage to professional reputation and integrity to subtler effects on personal identity. AI has no concept of any of that.

My earlier work on the diagnostic agent prompted this thought. To save effort, I made every diagnosis follow one workflow: check whether Docker is running and whether the services are healthy; if they are healthy but something is still wrong, ask Codex to diagnose it.

The resulting workflow was approximately:

- **Layer 0:** Check whether the containers are running. If one is stopped, start it directly. If it cannot start, service is impossible, so restart it. If three restarts fail, the situation is serious and requires diagnosis.
- **Layer 1:** Ask a lower-tier Codex model, such as 5.5 Luna, to perform preliminary investigation.
- **Layer 2:** Ask Codex Astra to perform a deep investigation. A later note: this tier had to be downgraded because Astra consumes too many tokens for routine use.

I reviewed the reports. Several incidents appeared, but the system did not discover meaningful causes. In one case, nothing was wrong: I had decided that the local Home Assistant container was unnecessary and paused it manually. The diagnostic system reported that a container had inexplicably paused for 85 seconds and found no cause. The cause was simply me, so the service itself was fine.

The system may also have been simple and stable enough that most events were only minute-scale transient fluctuations. By the time Tier 1 started, the system had already recovered. After three days of operation, almost nothing serious happened and little useful incident history accumulated.

A later update: I had Codex build a dashboard that refreshes once per minute and reports what happened. I was also reading Astra's extremely long Diagnostic Agent design document. It was genuinely excellent and detailed, with every field mapped clearly to its code location. I had not seen technical documentation that comfortable to read in a long time. Using Astra for documentation was worth it, even though it consumed a freshly reset five-hour allowance.

The important realization was this: if the diagnostic agent is responsible for ensuring that the cloud or local EBO Bot application is healthy, what ensures that the diagnostic agent itself is correct? If the diagnostic agent fails first, it can no longer guarantee the EBO Bot service it monitors.

That recursion has no end. No matter how many layers of decision logic or alerting programs are added, responsibility ultimately reaches a person. Perhaps three or four people once took turns checking different systems every hour, while now one person glances at an aggregated dashboard and assumes that the entire chain is healthy if no alarm appears.

Regardless, a human remains at the end. Neither engineering nor common sense allows operations to be solved indefinitely by stacking higher levels of intelligence. The person is still there to take responsibility—or, rather, to ensure site reliability.

Anyway, I truly had to leave. Missing the train would mean waiting another half hour.

---

Grokbot is genuinely useful. It perfectly solved my shortage of ChatGPT tokens. Later, I also helped my family use Grokbot from the other side of the planet. Once it was signed in, it no longer depended on an international network path. It was slower, but avoiding the Great Firewall was already a major improvement.

Also, 360 is dreadful. It takes advantage of older people who are less familiar with computers, installs an entire family of 360 products, and fills the machine with advertisements.

Still, this was wonderful: a small, completely isolated computer. Elon Musk, you genuinely, genuinely, genuinely benefited humanity. Please move a little faster on the Mars work; going to Mars is one of my life projects.

I also built a personal website on Cloudflare, using Grokbot for the entire process from account registration onward.

The first design gave me a headache. It was unimaginably ugly. The current version is ugly in an oddly cute and memorable way. I still feel sorry for the audience's eyes, but memorability matters more to me than restraint and subtlety, so I will go with this one.

The copy still needed work. At minimum, the Chinese text was painfully AI-generated and did not sound like a person. It had to be rewritten in human language.

I did not want to spend too much time on a personal website. I am not a front-end developer; I would rather focus on the substantive work.

Still, the result really is ugly-cute. People expect an AI aesthetic to be balanced and restrained, especially for technical pages, and it is difficult to imagine an AI producing this particular design.

I also redirected the GitHub Pages site to the Cloudflare site:

https://clair-chen.yechenworking.workers.dev/

---

I discovered a YouTube creator whose explanations I could genuinely absorb: [Caleb Writes Code](https://www.youtube.com/watch?v=XvmixEXPT3Q).

Remarkably, his way of explaining mirrors the way I think. He begins with the original problem, which makes the reasoning exceptionally easy to follow.

When I try to understand the world, I see everything as the result of step-by-step development. Many technologies we encounter today are already mature products. They have passed through long histories of exploration and evolution in many directions, and we see only the final result.

I have always struggled when someone hands me a mature result containing many features and says, “Just use it,” or, “Any of these three options meets the requirement, so choose whichever one you like.” Perhaps the simpler explanation is that I am not clever enough to remember what everything does and need the supporting context as a memory aid.

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

I looked up the ChatGPT Agent API and wanted to record a few ideas first.

My current Diagnostic Agent takes a clever shortcut: it uses Codex CLI directly. When ChatGPT released the Agent API, I therefore researched the new option.

I do not know whether the later project will need it. The application is genuinely used, so practical value comes first and resume value comes second. I will probably build only a small proof of concept to validate the concept and workflow. To avoid forgetting what I learned, I am recording these notes here.

1. Sandbox

Normally when we use Codex, it maintains a sandbox on our personal computer. However, if we use the Agent API, there still needs to be a sandbox. This sandbox can be self-hosted, or it can be OpenAI-hosted. If we choose self-hosted, there are multiple ways to provide it.

The core principle about the sandbox is that it doesn't need to be so thorough or fully prepared before the agent session works. This is more realistic because we don't know what the agent needs when it actually runs. Preparing everything beforehand would be too complicated, tricky, and create a lot of friction before development. What the agent actually needs is just a platform or an environment open enough to install whatever it requires, while remaining under the environment's restrictions. This makes the whole sandbox setup much more flexible and practical.

2. Sub-agents

Based on the OpenAI documentation, the use of sub-agents and their maximum number can be controlled by parameters set by users/developers. However, the actual usage and decision to invoke sub-agents are determined by the main agent itself, not explicitly decided by developers, users, or any human being.

3. The naming of the API

I'm more familiar with HTTP APIs or traditional APIs, where user post a request and get a response (a 1:1 interaction). In that sense, calling this an "Agent API" felt confusing at first.

In practice, it operates as a session: when we post a request to the Agent API, we actually start a session. Within this session, there can be multiple turns, sub-agents, context compacting, and sub-agent orchestration, all handled by OpenAI internally rather than by ourselves.

This also explains recent commentary suggesting that companies focusing on agent orchestration over the past six months may see their value diminish. The LLM providers have built this natively, and naturally, they can execute it better than anyone else. They control the source, the infrastructure, and the inference process, so their advantage goes without saying.

- The term "AI wrapper" carries a somewhat derogatory connotation, so do not use it carelessly. It describes a product, whereas prompts, context harnessing, and engineering refer to engineering methods and are actually more technical. A wrapper, on the other hand, is contrasted with a pure Large Language Model or the plain OpenAI API. To emphasize this again: do not throw the term around, because it really is mildly disparaging. It suggests that the other party has little core technology of its own and has merely placed an interface and some prompts around a model. From a technical perspective, though, that is essentially what everyone is doing now, because an LLM API sits at the very center. Just as the differences between people can be greater than the difference between a person and a dog, wrappers also vary greatly in quality.

---

The Diagnostic Agent really does need a major overhaul.

Look at the screenshot below. This is its current health dashboard, and it simply does not provide the information I need.

<img width="1064" height="350" alt="image" src="https://github.com/user-attachments/assets/ad786b51-4b02-49e0-a008-446e367866a5" />

More specifically, from my point of view, there is one basic principle for judging AI or any program: it must be useful. "Useful" has two specific meanings here:

1. Support human decision-making: this includes, but is not limited to, providing relevant information and filtering out irrelevant information, thereby reducing the amount of input that consumes the human brain's context window.

2. Create value: this is more abstract than supporting decisions. In essence, it means increasing the probability of arriving at a "valuable product." That value might be reputational—recognition in the market or among the people around you—or it might be a financial return from the market, whether B2B or B2C. Either is fine. Some ideas are brilliant but too flimsy in themselves: a single update from the original vendor can easily wipe them out, or they are so atomic that they can exist only as one small feature rather than as something genuinely usable. Those do not count as useful either.

(For example, shortly after Claude Code introduced connectors—I remember this clearly because Claude Code was the first to support custom connectors, which was why I switched from ChatGPT and subscribed to Claude Code—when the concept of MCP had just appeared, I built a local MCP server for Rize.io: https://github.com/YeChen-coder/RizeIO-LocalMCPServer. Later, Rize.io released its own official MCP implementation, and that was the end of the story. The MCP I had built disappeared into the dust of history. Looking back, its only real value was proving how quickly I kept up with things online and how aggressively I executed. They used a GraphQL API, which caused a great deal of trouble. It differs from an ordinary API: a conventional REST API returns all the values, and the client then filters out what it needs; GraphQL is friendlier to the server, so the client must specify exactly which values it wants before the server will return them. Even now, thinking about it gives me a headache. Their documentation and parameter lists were enormous, and Claude Code was nowhere near as capable at the time, so the whole process was a real struggle. But now the original vendor offers its own solution. I also stopped using Rize.io because of the price, so much of that work has simply been lost in the vast river of time.)

Returning to the current Diagnostic Agent, its visibility is poor. It pushes a large volume of content to me, yet I cannot extract any valuable information from it. The screenshot shows only two items; in reality, more than a dozen similar items are generated every day. They are not very useful and instead increase the cognitive cost of making decisions. By this logic, the agent needs a major overhaul.

There are also some historical issues. Whether because of authentication restrictions or the project's own functional design, the project on the ebo-engine side is exclusive. In practice, only one of the cloud and local instances can exist at a time; otherwise the connection drops, and once the video stream goes down, features such as natural breathing stop working. The consequences of a conflict are not especially severe—it may simply disconnect for a while—but since I am already changing the Diagnostic Agent page, I will have Astra integrate these issues as well and add proper switching and shutdown flows.

This will probably be a large job. My five-hour limit has only just reset, and I suspect it is about to be exhausted again.

The bills are coming from two sides: AWS in the cloud and the OpenAI Developer Platform, where all the AI token usage is charged.

At the moment I have to check them every couple of days, which is not ideal. This will probably have to wait until the next round, though; the work in the current round looks as if it will only just get finished. It will need to move even further back because integrating the logs has a higher priority.

Human energy is so expensive. I did not sleep well, and now I do not even feel like talking, typing, or expressing myself.

---

Boss, our wallet is saved!

I finally brought local/cloud switching and all the miscellaneous local and cloud tasks—including logs, incident response, and diagnostics—together on a single page.

<img width="1078" height="587" alt="image" src="https://github.com/user-attachments/assets/8a7b1b0e-820e-4678-9e9c-25639d9c94ff" />

<img width="827" height="278" alt="image" src="https://github.com/user-attachments/assets/316c7405-502b-424e-a657-8cb0fa38f97a" />


When I determine whether the system has a problem, I do not rely primarily on its basic status. Basic status is easy to assess, and Astra handled that well a long time ago. The core question is whether the functionality is actually working. When I troubleshoot and decide whether something is genuinely wrong, the key signal is whether it has produced any replies: if there is no record for an entire day, something has most likely failed. I therefore added both the local and cloud transcription records to this page as well. Finally, it feels right.

This connects directly to my earlier concern about "useful information." The Health Dashboard has actually gone through three versions:

1. Version one simply checked every minute whether each service was running. At that point, however, I still had to inspect the transcription-related logs locally myself.

2. Version two covered only the cloud. At the time, transcription messages were not even written to CloudWatch as a log item, so there was no way to pull them down locally. After I added the Diagnostic Agent, the dashboard also produced an enormous amount of information but very little useful information, making it impossible to use for decision-making.

3. Version three is finally usable. The only missing feature is billing lookup, although in theory I have already confirmed that the workflow works. My weekly usage is now down to 7%, and I have other things to deal with, so I will add this feature after Tibo resets my weekly usage.

This also gave me something to think about. An article I read yesterday said that, at this stage, it is extremely easy to have AI throw together an attractive interface that appears substantial. But whether it can provide useful information—and even the definition of "useful information" itself—always remains in the hands of the person who genuinely uses it. That person needs to be motivated not by AI panic, but by a sincere desire to change things, make the process smoother, and reduce pointless friction and decision fatigue.

That is also why I am reluctant to build toy projects detached from real needs. If you do not use something genuinely and over the long term, you cannot discover its problems. This is especially true in a field you do not know well: nobody pays much attention to something they use only once or twice, and the return on further investment is not worthwhile. Only when something needs to be done more than three times, and will visibly continue to be done in the short to medium term, do people naturally want to automate the entire process.

I have built some toy projects before, and they truly were not useful. For example, I made a resume-focused RAG project using resume data from an open-source repository online. I got the workflow running and learned techniques such as tokenization and chunking, but I am not an HR professional. Screening resumes has no value in my daily life, so I had no motivation to keep investing in it at a deeper level.

The RAG system for fortune-telling—Bazi and Liuyao—was useful only during the period when I was intensely obsessed with divination. The main reason I later abandoned it was that I had no ability to judge whether its output was correct. The same logic applies to an AI agent: something that cannot be verified has extremely limited usefulness.

---

All right, this time something has officially, genuinely gone wrong.

While switching from the cloud to local operation, my computer displayed notifications two or three times warning that Tier 0 had detected a Docker health-check problem with the Realtime Assistant container. The dashboard also showed the assistant—the Realtime Assistant container—as unhealthy. At the same time, the Docker page looked normal, meaning that the container was running but the program inside it was malfunctioning.

After investigating, I first determined that the audio-source connection had failed. This audio source must continuously push audio into the project; even when the other side is silent, it still has to push silence. So this was unquestionably a problem.

<img width="982" height="130" alt="image" src="https://github.com/user-attachments/assets/e9fa3ad1-7c07-4331-8bad-7d74c3c550af" />

Further investigation found the cause: during the switchover, the program sent a command to enable audio, but the robot was delayed and came online after the command had already been issued, so it never received it.

In other words, ever since I switched from the cloud to local operation this afternoon, no audio had been received for three or four hours. Without incoming audio, the subsequent programs and ChatGPT responses naturally could not be generated.

Incident timeline (Toronto time):

1. From 10:43 to 14:18, audio remained normal at approximately 72–73 kbps, with about 112 MB received in total. This shows that the robot's microphone and network had both been working normally beforehand.
2. At 14:18:52, Realtime Assistant detected an interruption in the RTSP video stream and invoked the wake-up and camera-recovery procedures.
3. EBO Engine consequently rebuilt the entire Agora RTC session.
4. A new session was established at 14:20:35, but the robot did not rejoin until 14:21:17.
5. The Engine's "resend the unmute command after 20 seconds" action ran at 14:20:55—before the robot joined—so it had no effect.
6. After the robot joined, the Engine sent the unmute command only once and retried the subscription. The subscription API returned success, but none of the following ever appeared afterward:
   - audio track subscribed
   - first remote audio frame
   - ROBOT MIC OPENED
7. The video subsequently recovered completely, but the audio has remained at 0 bytes / 0 bitrate ever since.

This was the first issue I encountered that truly qualified as a real incident. After fixing it, I also added an incident-response folder to the current project containing bilingual incident reports in Chinese and English.

It also proved that the Diagnostic Agent on this side is genuinely effective—at least when it comes to calling for help through a PowerShell notification after it cannot resolve an issue—even though that is only Tier 0. Why did Tier 1 and Tier 2, both of which run through Codex, fail to activate? A major reason is that token consumption has been enormous over the past few days. The five-hour limit gets exhausted as soon as it opens, leaving no tokens for the agent. As a result, the model could not invoke Codex CLI at all, which also delayed the response to this incident to some extent.

I checked the Diagnostic Agent logs and found that the program itself had indeed worked correctly. It detected the problem immediately, actively tried to repair it, repeatedly reported it as recovered, and did invoke the Tier 1 Codex CLI. However, because Codex had genuinely reached its usage limit, it could not complete the investigation.

<img width="771" height="261" alt="image" src="https://github.com/user-attachments/assets/7a8393fa-5e0d-49c3-8e31-2cad25153278" />

<img width="776" height="593" alt="image" src="https://github.com/user-attachments/assets/88d53a35-88bb-42e6-92c7-0b3573152dec" />

---

Here is a horror story. A few days ago, I had just finished integrating the cloud and local sides, so I switched back to local operation. Then, on the very next day, there was a power outage! Yes, the once-a-year power outage happened on precisely the second day after I switched this project back to local operation.

I slept through the afternoon that day. The entire apartment was dark, with absolutely no electricity. The apartment administration said they did not know when the power would return and told us to call the utility company. How can I put it? The whole situation was just absurd...

Could this be improved? Certainly. I could give the local computer a heartbeat so that if it fails to send a message or respond to a ping for a certain amount of time, the system automatically switches back to the cloud. The logic is easy enough, but implementing it would still require something that always exists and always stays on, would it not? That component would basically have to run in the cloud; otherwise, it would be difficult to guarantee its robustness.

The cloud is not necessarily absolutely reliable either. Cloud disaster recovery generally requires deployment across at least two availability zones. So I think I should stop tinkering with this. If I keep digging, I will return to the original question: why integrate local operation after getting the cloud version working? Simply to save some money. AWS services are genuinely expensive. Their pricing is brutal—truly brutal.

So some things can simply stay as they are. I think the current setup is already quite good—genuinely quite good.

---

I added a cost module to the dashboard. This is fantastic.

<img width="1183" height="370" alt="image" src="https://github.com/user-attachments/assets/40ea292b-d7d7-4439-8e37-aa5afc2536ee" />

Look at this magnificent dashboard:

<img width="1763" height="4371" alt="image" src="https://github.com/user-attachments/assets/5ebcd8f5-9c65-48a5-ba30-8bbed549e851" />

Great, now I can use this to show off and fool people—just kidding, I am off to share it.

Honestly, once I get something running and then look back, I realize there is so much to talk about inside it. For example, right now I genuinely want to grab someone and vent. It was not even that difficult; I simply have an overwhelming urge to express myself with nowhere for it to go.

I could pull out any one detail and ramble about it for half a day:

• Why did this have to be built this way?

• Why was this part designed like that, and how did it end up this way?

• Why were the first dashboard and all those first-line checks filled with useless information?

Of course, there are still problems I cannot solve. For example, why does Codex usage run out so quickly? And how can power outages still happen in this era? Is Canada not a developed country? We did not even have a particularly severe snowstorm here.
