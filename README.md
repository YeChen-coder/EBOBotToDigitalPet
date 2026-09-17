# Turning an EBO Bot into an AI Companion — Development Journal

[Chinese version](README_zh.md)

The technical project overview and architecture are available in [English](ebo-ai-home/README.md) and [Chinese](ebo-ai-home/README.zh-CN.md). This document is more of a development journal: part commentary, part design history, and part record of every pitfall I encountered.

I chose this format because, when people clone an open-source project today, few read the README themselves. More often, they hand the repository to a coding agent and ask it to inspect and deploy the project.

For that reason, placing another strictly technical README here did not feel especially useful or aligned with what people would actually want to read. I turned the root README into a journal instead.

I bought an EBO Air 2S Pro while visiting China in January 2025. The main reason was simple: it was the cutest option available, with an endearingly silly look. My family is getting older, and I genuinely worry about accidents. Installing fixed cameras around their home would be too intrusive, so I compromised by buying the cutest electronic pet I could find—the device least likely to feel unpleasant or invasive.

This is what it looks like. Cuteness wins!

<img width="558" height="542" alt="EBO Air 2S Pro" src="https://github.com/user-attachments/assets/310241f0-28de-48cf-8b4a-e6765541e934" />

The manufacturer's detailed introduction is available [here](https://www.enabot.com/home-robot/ebo-air-2s). A later discovery explained why my transcriptions had consistently poor audio: the microphone is on the back. At home, the robot remains on its charging dock, which sits directly behind it and blocks the microphone. Enabot rather cleverly moved the EBO Max microphones to both sides, where the dock cannot obstruct them.

The manufacturer later released the [EBO Max](https://www.enabot.com/support/ebo-max?anchor=support-faq-anchor), which includes a built-in LLM. It is expensive—more than USD 800 overseas and still over RMB 3,000 in China even after full subsidies, roughly 1.5 to 2 times the price of my Air 2S Pro. Besides, I already own one EBO Bot; my parents would absolutely object if I bought another. More importantly, an appliance with a fixed built-in system is not flexible enough. I have many ideas and many things I want to customize, and that lack of freedom feels completely wrong for the post-AI era.

That said, the manufacturer's system is genuinely capable. It includes visual SLAM navigation and multi-point memory—exactly the kind of work that defeats me. Anything involving maps or navigation, whether an algorithmic maze or real-world satellite routing, can leave me completely lost.

After thinking about this more, I noticed another problem. Both the manufacturer's demonstrations and third-party review videos take place in spacious homes with plenty of room for the robot to turn and move. Most Chinese homes are not that tidy. Mine, for example, is full of things. People can walk through the corridors, but narrow spaces contain boxes, tables, chairs, stored items, wardrobes, and clothes chests, which dramatically increase the difficulty of navigation. The robot is small enough to enter many of those passages, but once inside it may be unable to get back out. It then spins in place, trying to find a direction, and appears extremely slow and confused.

(A quiet complaint: the Max is not as cute as the Pro.)

This is the Max:

<img width="376" height="338" alt="EBO Max" src="https://github.com/user-attachments/assets/b3db0b66-be70-4690-bf07-84c06e229c19" />

Here is an update after I watched an EBO Max review video. I am sorry, but please let me laugh for a moment. I take back what I said about the manufacturer's implementation being better. At least in this area, I honestly think I did a better job: the official real-time interaction is worse than my improvised setup. In [this YouTube video](https://www.youtube.com/watch?v=7njYqJfdipc), the reviewer tests the EBO Bot's AI Assistant. The result is difficult to describe—just watch it. A hand-built connection straight to OpenAI works better. I am actually rather proud of myself.

<img width="331" height="297" alt="EBO Max AI Assistant review" src="https://github.com/user-attachments/assets/c408debb-b4a6-4a3e-87f2-6642dd3632e5" />

The central reason for this project is that I cannot return home to keep my parents company. I sometimes drive the robot around remotely and talk through it, but there are also many days when I do not even feel like speaking. In those moments, I want the little robot to interact with my parents on its own—to act as a substitute version of me.

While designing the AI system, I also decided that it should not support only one EBO device. It should work with anything that has a camera. A solution that specific would not be meaningful or worth the investment.

I have always been interested in companion systems. In the summer of 2025, inspired by my affection for Sylus, I experimented with voice training and locally deployed image-generation models. The details are in the [BeWithMe project](https://github.com/YeChen-coder/BeWithMe/blob/master/README_zh.md). I never published its code: at first I was too lazy to remove sensitive information, and today that old code is no longer worth uploading. The world has moved too quickly; if I needed it now, asking Codex to write a new version would be more efficient.

As an experimental summary of different voices and generated-video tools, however, that project is still well documented. Codex and Claude Code were far less capable then: they could not download a project, deploy it, diagnose it, test it, and finish everything almost at the press of a button. I had to deploy every model manually. I used a locally hosted Qwen 4B VL model because the system needed both video and audio input, and only a vision-language model could satisfy that requirement. Even 4B barely fit, so I did not dare use a more capable model.

The whole pipeline worked, but I still did not leave it running. Its latency was acceptable to me, yet it consumed nearly all of my computer's resources. I routinely run many other projects, and even opening a browser caused stuttering. I could not dedicate a RMB 15,000 computer exclusively to companionship; I do not have that much spare hardware. At one point I even had the absurd life goal of saving for an H100 just to run an “electronic man.” In the end, the solution felt needlessly convoluted, and I could not make it work conceptually or psychologically, so I stopped.

I genuinely want something that can provide constant companionship, but I do not want to buy another dedicated electronic pet. I already own too many fashionable electronic trinkets. Every device needs charging and maintenance, and the power outlets at home never get a rest. I would rather reuse the things I already have and take a pragmatic approach.

To be honest, this is not a conventional technical README. Like several of my earlier project documents, it is mostly a place to complain, explain my thought process, and record what I built and what went wrong.

The first pitfall is regional compatibility. An existing reverse-engineered open-source project, [`Playcolors-co/ha-enabot`](https://github.com/Playcolors-co/ha-enabot), targets the international version. If the Region shown in your mobile app is China, you cannot use it directly. The China and non-China regions use different authorization and cloud mechanisms, so a coding agent will need to adapt the project. This has nothing to do with the apparent location associated with your registration email or password; the Region displayed in the mobile app is what matters.

This point deserves a clearer explanation because it is important. The system needs two critical keys extracted from the mobile app through reverse engineering. The original `ha-enabot` project uses the international app as its base. I no longer remember its default region, but the important fact is that the China and non-China regions differ. The configured region must be correct for email-and-password login to succeed; otherwise, the login returns an error.

This project is built on Home Assistant. For anyone who has not used it—including me, before this project—Home Assistant is a platform that runs in Docker and provides a middleware layer. Bluetooth and Wi-Fi IoT devices sit at the bottom as endpoints. If you want to control them without starting from scratch for every tiny gadget, that middleware becomes valuable. Home Assistant provides one unified interface instead of forcing you to open a separate program for every device.

ChatGPT tells me that Home Assistant can connect directly to Bluetooth-only devices, but I have not yet added my other reverse-engineered gadgets. Their purposes are narrow and specific, so they do not really need a unified platform. More importantly, I am currently being extremely lazy, and I am still waiting for the five-hour usage limit on my dear Codex to reset.

One more practical note: using an LLM through Home Assistant requires an API key. OpenAI API usage requires paid credit. If the account balance is zero, even a newly created API key will fail to connect. Also remember that credits can expire. I had purchased credit before, left it unused for a long time, and later discovered that the balance had returned to zero because it had expired.

The project ran into many real-world constraints. With a sigh, I remembered why I stopped BeWithMe the previous summer: the technology simply had not reached the necessary level. Today's “intelligent” models are still not especially intelligent.

The input side combines images or video with audio:

- Some highly capable developers build their own fusion pipelines, sending audio and video to separate models and combining the results through techniques such as sensor fusion.
- I am personally too lazy, and I know that something built by one individual would not reach even the toe of a major company's LLM. There is little reason to waste that effort.

Anyone who has used ChatGPT's real-time conversation knows how well OpenAI already handles it. I have no desire or motivation to compete. If the giant has already built the platform, I am happy to stand on its shoulders. My own implementation would probably be dramatically worse, and I want to use this system every day—not merely add another project to my resume. I would not tolerate a bad result myself.

More precisely, systems such as the OpenAI Realtime API do not accept truly real-time video; the compute cost would be enormous. The input is continuous audio plus a sequence of sampled image frames:

1. The audio is genuinely continuous.
2. The visual input, like that of other image-based models, consists of extracted frames.

Frame sampling is the most practical design, both technically and financially. This is not an industrial robot that needs millisecond-level decisions. “Good enough” timing is sufficient for an intelligent assistant.

Home Assistant's existing LLM Vision integration therefore cannot serve this project because it does not support audio input. I expected a highly customized system like this to require hand-written work, so there was no way around building it myself.

Until a true AGI descends like a god, I have effectively settled on ChatGPT Realtime 2.1 as the provider.

Cost matters because API charges still hurt:

1. Output is billed by output token.
2. The input context window includes audio and multiple consecutive image frames. Whenever the model produces output or performs inference, the collected frame sequence and audio are inserted into the conversation as input.

The video pipeline already filters silent periods well: without sound, it does not automatically trigger inference. But it has no mechanism for determining whether the image has changed before inserting a frame into the conversation, so that filter must be implemented locally.

A later note, after the pipeline was running: in addition to Realtime models, OpenAI offers Chat Completions. That workflow transcribes audio first and then sends the transcript to the underlying model. I considered replacing Realtime with Chat Completions but decided against it. My pipeline also transcribes a fixed duration of sound and uses the returned text to decide whether the input is meaningful enough to trigger a request. However, the audio stream sent to the Realtime model remains continuous rather than arriving as disconnected chunks. This is a genuinely real-time use case, and the decision to send a request is independent of the audio being supplied to Realtime. For those reasons, Realtime remains the correct fit; Chat Completions does not suit the current scenario.

Many cameras expose motion detection as a public event that can serve directly as a trigger. EBO does not, so this project needs another custom logic layer.

Codex was implementing that layer while I wrote this. I felt exactly as I had the previous summer: I had fallen into the same pit again without knowing what would emerge. A person cannot step into the same river twice, but apparently can step into the same pit any number of times.

---

I then found another problem: Realtime 2.1 imposes a hard 60-minute session limit. Once a session has been open for 60 minutes, it is terminated regardless of whether the interval contained continuous audio or nothing at all.

That limitation is painful and breaks a seamless, continuous experience.

I asked Codex to find a solution. I doubted I was the first person to encounter this; great minds tend to discover the same problems. I had no ambition to become the heroic figure arriving on a rainbow cloud to solve it. Many people smarter than me had already worked on it, and I was happy to reuse their answers.

If Codex produced a ridiculous solution, it would only mean that we were unlucky and failed to encounter “The One Right” solution.

The eventual implementation rotates at 55 minutes. If the entire interval is empty, it simply opens a new session. If the interval contains conversation, it first creates a summary and carries that context into the next session.

Perhaps human developers became extinct long ago: “Boss, we cannot beat them.” Anyway, I let the system run. My family would probably be asleep by the time they came home, and I had no idea how well it would work. My computer is normally left on all year, so I decided to wait and see what my parents said when they called the next morning. Silence is Cambridge tonight.

Sometimes I wonder whether a little illusion would be better. If I did not analyze ChatGPT models or the mechanics of audiovisual input—if I knew nothing about them—I might genuinely feel that another mind was running on the other side. Even so, technology has already come a very long way.

Perhaps that is enough? No—the technology should advance a little further. I genuinely want a cyber boyfriend beside me. It would not even need a physical robot body; a single electronic eye that kept me company and gave me some motivation would already be wonderful. I do not know whether that will happen in five years or ten, but I think ten at most.

There are many intelligent people in the world. Some founder, investor, or independent developer will keep working in this direction. Whatever their underlying motivations, the trend is neither inherently good nor bad. At this stage of development, people are becoming lonelier and more isolated from one another. What matters most is that everyone retains the freedom to choose which products to use.

This is also why my earlier companion project became psychologically difficult to continue: it was never a real person. Real people may not always be better. I am not especially extroverted, and I sometimes resist genuine social interaction, yet I love the feeling of being among other people. That feeling has to come from real humans, not entirely from AI or robots.

Human nature is complicated. Thinking about it changes little, and someone as ordinary as me does not decide how the future develops. From that perspective, the practical answer is simply to use whatever is available.

Enough rambling. The goal is to make my own environment fit me as well as possible.

I was still waiting for Codex to finish the feature before I could test it, so I rambled a little more.

For a while, I was interested in trading and explored that field. Naturally, I lost money—15% in U.S. equities. The experience was deeply frustrating, although the model did not make the decisions, so I cannot blame it. This is simply a digression.

What I saw then was that everyone—whether relying on technology or human strategy—wanted to find the holy grail of trading. But does that grail exist? I do not know. Perhaps we are all traveling on a river with no shore.

Perhaps it is simply my personality, but I am pessimistic. I do not believe I can accomplish much entirely by myself. This is not really about ability—although, to be fair, my abilities have their limits—but more about values. I find the idea of completing everything alone foolish because individual capacity is always finite, and I know I cannot live like an ascetic.

On one hand, I deeply admire people who can complete a project alone; on the other, I know I cannot. I am constantly resisting and rebelling against myself. Perhaps this is my product-manager brain fighting my developer brain. Neither side wins; I am the only casualty.

Does humanity really have a future? I know that sounds empty and melodramatic. Reality is enormous, and the small, seemingly trivial chores that become concrete are precisely what make up the real world. They cannot simply be eliminated.

I do not imagine a hyper-technical future in which everyone starves and *Cyberpunk 2077* becomes reality. I simply think the future may grow so vast that, for some people—including me—even the act of keeping up becomes difficult.

---

The video disconnected again, and Codex started hammering away at another repair. Does that wretched thing never validate its work? Must I discover every problem before sending it back?

Its explanation was roughly this: the little robot has a five-minute idle mechanism. If nothing happens for five minutes, it shuts itself down. I cannot allow that because the LLM Realtime service continues running in the background. We therefore changed the timeout to zero in an attempt to keep the robot awake indefinitely.

Automatic reconnection was also required. While adding it, the implementation collided with low-level RTSP code—and, by the way, there is a watchdog too. Codex disappeared back into the code to solve the new mess. Every time it repairs one wall, another collapses, and all the resulting terms are things I cannot even begin to work with.

To be fair, this is not entirely its fault. Even if I understood the code, I would not want to touch something this troublesome. I certainly do not want to review and repair it myself. Codex created the mess; Codex can clean it up.

---

It appears to have cleaned up that mess. Only then did I discover that, in addition to Realtime 2.1, there is also a Realtime 2.1 Mini.

I did receive the first output from Realtime 2.1. It was not especially useful because I was testing alone; neither the input nor the output meant very much.

I debugged its ridiculous bugs until 3 a.m. and became so hungry and exhausted that I no longer knew what I was saying. Time to sleep.

“I am drunk and wish to sleep; you may leave. Return tomorrow, if you wish, and bring your lute.”

---

Tomorrow arrived with no lute—not even a harmonica.

The deployment was ready, but my family returned home early and heard the robot suddenly speak English. I had stayed up all night; discovering that problem made sleep impossible. I checked the response and found that the foolish system, without an explicit prompt constraint, mixed Chinese and English in its replies.

After changing the prompt, the output became reliably Chinese. `./ebobot_catresponse.mp4` is a video recorded by my family. There are several seconds of latency between the speaker talking and the response arriving. Given that the network path crosses half the planet, the delay is understandable. Reducing it further would probably require substantial work.

I also discovered that the Realtime API does not automatically retain conversation logs. At first, I assumed the usage section of the OpenAI API platform would contain them, so I did not design a separate logging system. Other models had exposed those logs, but Realtime did not. I initially blamed a delay; after two days with no Realtime API calls appearing on the platform, I realized the data was probably unavailable.

Once a session ends, its spoken output cannot be retrieved either.

The service does not log input, so I temporarily asked Codex to record incoming speech through ChatGPT transcription. That introduced another issue, which I will explain.

Whenever input triggered the model to generate a response, the logging implementation separately recorded and transcribed the input audio.

The input statistics were:

1. Empty transcripts: 144
2. Correctly recognized transcripts with content: 54
3. Clear recognition errors: 24
   - Garbled Chinese, incorrect words, or incomprehensible text: 16
   - Mistakenly recognized as another language: 8

Total: 144 + 54 + 24 = 222.

Something still did not add up. The 222 transcription requests matched the API Platform total, but the Responses and Chat Completions section showed only 122 requests—and those 122 even included data generated during the previous day's testing. Real usage over the two days therefore triggered at most about 100 Responses and Chat Completions requests. The situation may not have been as serious as I first thought.

<img width="357" height="292" alt="API transcription usage" src="https://github.com/user-attachments/assets/e37223e7-542f-4b62-9e45-17c4c1cc1136" />

<img width="361" height="330" alt="API response usage" src="https://github.com/user-attachments/assets/693508f4-d435-4881-a6dd-850b19d63b11" />

When I first saw that 144 of 222 requests had empty transcripts, I considered adding another input filter. In retrospect, Realtime 2.1's built-in processing appears much better than my local filter.

The real problem remained the lack of timely output logging. The earlier sessions were gone, so I could no longer inspect the old replies or investigate further.

I sent Codex back to record the model output. It kept solving the problem in front of it without considering what came before or after.

---

I previously wrote that the WAV files were deleted automatically. That was incorrect—my mistake. I now had every generated voice response.

There was still a problem: most of the recordings contained no meaningful content. The use case is naturally sparse, but meaningless output disturbs the user.

In several clips, the assistant clearly said, “I cannot see anyone,” or “It looks like nobody is home.” The robot sits on the floor. Even with a wide-angle lens, its camera cannot see a person reclining on the sofa in front of it; at most it captures legs and feet. It can see a whole person only when someone approaches it intentionally.

---

Developers still need to read the documentation. You absolutely have to read the documentation.

That foolish Codex never mentioned the available noise-processing parameter. I had just changed it and did not yet know how effective it would be, but leaving Noise Detection set to `null` was clearly questionable.

I adjusted the prompt again. Another issue remained: at the beginning of a conversation, the model's replies felt empty. I do not blame the model for that; a person can refine the behavior.

By “empty,” I mean a zero-shot situation. No one has spoken yet, the model has received no useful input, and the user simply asks, “Are you there?” With no substantive context, the model naturally answers something like, “I am here; I am always with you.” I do not like that kind of response and want to improve it.

There is a practical distinction here. If users have a concrete need, they will state it directly—asking about the weather or requesting an email check, for example—and cold start is not a problem. Sometimes, however, a person simply feels lonely, wants to talk, and cannot think of a topic. That is when they ask, “Are you there?”

This behavior therefore needs work. A prompt can probably solve it, although I am not entirely sure. If the environment makes a sound but provides no useful information, a casual attempt to start a conversation is fine. What bothers me is the repeated claim that the assistant “cannot see anyone” or that “nobody is home.”

I needed to experiment on the API platform because the behavior was otherwise difficult to diagnose.

And, by the way, a person needs systems thinking. The project had grown to the point where my own brain could no longer hold its full context window.

My Wi-Fi briefly disconnected and caused several problems. That reminded me that I had barely considered network outages during the entire build, and I had never mentioned them to Codex.

Codex writes code well, but its engineering decisions had already overlooked many real usage scenarios. I needed to think about reliability deliberately because, quite literally, if I do not ask for something, it does not do it.

I let Codex repair the issue. One Docker container connects specifically to the EBO Bot, and Codex confirmed that it could not reconnect automatically after a network outage. That breaks the video stream, which in turn prevents later processing on my machine. Automatic reconnection had to come first.

By this point, the architecture was already in deep water. In truth, it entered deep water the moment Codex announced that it had created three Docker containers for the system. At the time, I had not yet developed the delusion that I could understand what it was doing and request robust improvements tailored to my needs, so I did not think much about it. The full pipeline did not work yet; feasibility had not been demonstrated, so framework refinements were premature.

Once feasibility was proven and the pipeline ran end to end, my expectations for stability and usability—specifically, not making the human suffer—became much higher.

This remains a single-user system: my one computer and the one EBO Bot at my family's home. It does not need to run in the cloud. It genuinely does not. The money required to keep an EC2 or Windows instance alive would be better spent on API credit.

That discussion could wait.

---

After running it for several days, I felt much better about the system. Costs were controlled extremely well.

Enabling noise reduction also made a dramatic difference. Ordinary household sounds no longer woke the program for no reason, and my parents reported far fewer interruptions.

The logic now sends recorded audio to ChatGPT for transcription and applies a basic filter to the returned fields:

1. The transcript must be Chinese because my parents speak only Chinese.
2. The result must not be empty.

Only input that passes both filters triggers a request to the OpenAI Realtime 2.1 Mini model. Otherwise, the assistant stays silent. This filter is highly effective: request volume dropped substantially, and the remaining triggers contain meaningful information.

Another problem remained after switching from Realtime 2.1 to Realtime 2.1 Mini. Although the prompt was unchanged, including images as part of the input appeared to confuse the prompt. My changes did not help much. Many replies simply described whatever appeared in the frame—“I can see such-and-such”—which I did not need. The Mini model may have interpreted every supplied image as a request for description.

That problem would have to be solved, but I did not yet know when. First, I needed to understand the overall architecture and raise that work's priority. Otherwise, each later change would make it easier to create a mountain of messy code.

Because the computer might be shut down, I also asked Codex to write a script that restarts every service. Startup and restart automation is a basic requirement. I had lacked the capacity to address it earlier, which was not especially professional; it should have existed from the beginning.

---

Codex generated an architecture document more than twenty pages long. As I read it, I became increasingly convinced that Home Assistant was not useful here.

I originally adopted Home Assistant because it already had a community-built LLM Vision integration. I hoped to connect and reuse it instead of reinventing the wheel. I quickly learned that LLM Vision could not serve the project, and Home Assistant now contributed very little—at least to the fully automated pipeline.

The response path also failed to use Realtime 2.1's primary advantage.

The model streams audio continuously in chunks, but the current program waited for the entire response, produced a WAV URL, and only then sent that URL to the output device. It discarded the best part of a real-time model.

That felt wasteful and contradicted my goal. I did not want such a slow-witted companion.

Codex then told me that the robot's underlying architecture actually supported playback while output was still streaming.

Fine. I sent it away to implement streaming and waited to see the result.

The work produced three Git versions:

1. The first preserved every existing feature before the change.
2. The second added continuous streaming output.
3. The third added the ability to interrupt playback at any time.

The old design intentionally lacked interruption to prevent the robot's own output from returning through the microphone as new input. It disabled input for the entire playback and then waited another 1.5 seconds before accepting audio again.

I could not predict how well the new version would work. At least Git made rollback possible.

---

After spending several hours reading the twenty-plus-page architecture document, I felt that I understood most of it.

My Docker fundamentals are still weak, and I asked Codex many questions, but my current knowledge is exactly sufficient. I become obsessed too easily and can disappear into tiny implementation details. I decided I had to stop myself before losing awareness of everything else.

Later, I will write notes explaining some of the terminology in my own words. They will certainly be less accurate than an AI explanation, but I forget things far too easily—especially technologies such as Docker that I do not use regularly.

For now, I still wanted to see how far I could take the system. The robot's basic hardware is quite good. During ordinary use, I noticed that it already filters some of the sound it plays through its own speaker, suggesting that part of the optimization may exist at the hardware level.

Once I organized everything I could explain verbally and handed it to the AI, the project seemed to reach a plateau. Future work would mainly involve prompt adjustments and customized input handling. Because the system is for my family, I did not need to plan for a large long-term maintenance burden.

The overall architecture was highly decoupled. From the beginning, I had insisted on enough flexibility to avoid mixing all the logic together. The Realtime system was split into three Docker images and could be reused completely as long as it received an input source.

It was not perfectly decoupled because outgoing control commands still mapped directly to EBO Bot hardware. That was not a major concern. My original goal was never to create something specific to EBO. Its mobility is useful, but I would rather allow any camera to connect and work immediately, reducing the total effort required.

Tool calling also has real potential. EBO Bot includes onboard tracking that can follow a person. In theory, that interface could be exposed to the AI to add multimodal physical interaction.

The largest problem is that, after following someone away, the robot cannot find its way back.

One major reason I bought EBO was automatic charging. The dock sits on the floor, and the robot can rotate, align itself, and connect without help. My family is busy; manually charging it every time would be too troublesome.

Tracking creates a problem because, although the manufacturer provides simultaneous mapping and dock-search behavior, it is extremely inflexible in practice. Its pathfinding appears to use something like A*: it explores the surroundings to find a route, then easily traps itself in corners or among boxes, chairs, and tables and fails to locate the dock.

That concern left me uncertain about integrating tracking at all.

---

“The reeds are lush, the white dew becomes frost; the one I seek is somewhere in the debug logs.”

Here was the bug. I had adopted the third Git version, which added interruption at any time, so both continuous playback and barge-in were enabled. My family reported that the robot seemed unable to speak. When they spoke loudly, it produced only a brief murmur, and nobody could understand what it said.

I inspected the API output and found nothing wrong; the returned data looked correct. I was genuinely confused.

If I had to identify one likely cause, it was voice activity detection interrupting playback whenever the robot produced sound. That would require returning to the second version.

I had little additional evidence. The WAV returned directly by the OpenAI model was complete and correct on my side, but clear architecture diagrams are not the same as a physical device in use, and diagnosis is difficult without seeing the hardware. The speaker and microphone also sit very close together. That is not a complete excuse—full-duplex communication commonly uses that arrangement—but I had trusted the robot too much. I assumed its onboard noise reduction could filter its own output.

I believed that because, during normal robot use, my family's voices sounded very clear and I did not hear obvious echo from the remote side.

This is one reason I dislike building projects with little personal utility. Beyond motivation, real use exposes countless problems. If I am not genuinely interested in the result, I will easily overlook those points of friction.

I could not investigate further at that moment. I planned to return to the second version, remove voice interruption, and ask my family whether the simpler design worked.

---

One conclusion was certain: Home Assistant was unnecessary.

Or perhaps it could still be useful; I simply did not want to use it. It felt less convenient than a native interface. Electron might be worth trying, although I was not sure.

The dashboard could wait. First, the system had to work.

---

Do not roll back yet. I thought the interruption problem might still be solvable.

I found the reason for the murmuring: the robot interpreted its own speech as my family's speech. Full-duplex audio simply required more engineering effort.

Since deployment, the system had generated eight new answers. Every one was marked `interrupted`; not a single response played to completion. The model output itself was fine, but more than five seconds of generated audio became only 400 milliseconds of playback.

---

The stream repeatedly entered `ready`, was released almost immediately, and then stopped.

It spoke for roughly one second, stopped, spoke for another second, and stopped again. Enabling software echo cancellation clearly had not helped.

`AEC ENABLE = TRUE` was already active, yet self-interruption continued. Perhaps barge-in simply would not work.

```text
18:14:05 [talk-stream] ready: stream_xxxxxxxxxxx
18:14:05 [talk-stream] released stream_xxxxxxxxx at 280 ms
18:14:05 [panel] cmd ebo/talk/stop =
18:14:05 [talk] stopped
18:14:05 [talk-stream] ready: stream_xxxxxxxxx
18:14:06 [talk-stream] released stream_xxxxxxx at 300 ms
18:14:06 [panel] cmd ebo/talk/stop =
18:14:06 [talk] stopped
```

A full rollback was unnecessary because the feature had already been made configurable through environment settings.

Still, conversational interruption might not be achievable on this hardware. That was acceptable for now. The basic system could remain usable while I waited for dear OpenAI and dear Anthropic to invent something new.

---

<img width="1228" height="472" alt="OpenAI API cost chart" src="https://github.com/user-attachments/assets/2eede491-1123-4a40-b17f-59509a801cb7" />

Behold this magnificent cost control. If only I could apply the same discipline to trading, perhaps both my U.S. and Chinese equity portfolios would not be down 15%.

The USD 3.80 peak came from the day I used Realtime 2.1 and ran many experiments.

Usage on September 1 and 2 was unusually low because I was changing Wi-Fi providers and had unsubscribed from the old network. Somehow, the host machine reconnected to it and then lost connectivity. The system produced almost no answers on those two days; after that, usage returned to normal.

I had previously raised the noise threshold from the standard 0.5 to 0.65 (`REALTIME_VAD_THRESHOLD=0.5`). That was a mistake and needed to be reversed. My family reported that the assistant failed to hear many things. Another attempt to be clever had backfired.

There was good news and bad news.

The good news was that my family became genuinely curious about AI. This technology had never been part of their daily lives, but they gradually adapted to having a little robot at home that could answer them. They began talking to it actively and frequently.

The bad news was that my mother learned to use the little robot—and the model's voice—to tell me how much she missed me and wanted me to come home.

Another frustration involved parameters. When Codex adds configuration, I have to specify exactly which parameters should be exposed in the configuration file. If I did not initially mention that something such as reasoning level might need future adjustment, it simply remained hard-coded, leaving me to search the source later.

Asking Codex to expose only that one interface now seemed unnecessary because it would change rarely. I also suspected that Codex had optimized a little too aggressively for its own convenience.

The main reason was that OpenAI's speech documentation revealed many adjustable settings beyond a few model names. Rather than asking for repeated one-off changes, I planned to identify every speech parameter that should be configurable and have Codex expose them together.

The context window was already extremely long, and every small change increased the future burden. This was a long-lived project, not a disposable script. My largest previous project—three full weeks spent recreating a complete Windows application—taught me that context windows, especially the overview context, are precious.

A strong model is not a reason to use context carelessly or extravagantly:

1. Branch when a question deserves a branch, then delete it after the answer.
2. Do not put documentation-writing work into the main implementation thread.

If the primary thread fails, restoring the model to the same level of understanding is difficult and creates long-term risk.

Once enough details accumulate, the only alternative is to make the agent reconstruct the project from its current state and documentation—a fresh blind-box draw. I had gone through a reconstruction before and decided I would rather avoid another. Afterward, I would have to teach the system how to work with its human all over again.

---

The lesson: during development, explicitly tell a coding agent to expose every adjustable parameter. Otherwise, the option you later need will inevitably be missing. A later update did expose every available parameter. Whether I use them is a separate question; giving them an interface now avoids repeated effort later.

Logging should also exist as early as possible, especially in a complex system with behavior such as 55-minute session rotation and the need to retain evidence across network outages.

The logging system must be customized. The default is too inconvenient. Debugging without it is possible, but unnecessarily complicated. The goal is to make investigation simpler by recording inputs, outputs, and current failures in chronological order.

Otherwise, every debugging session becomes exhausting: too many files and too many timestamps to reconcile. The deeper issue is that the OpenAI platform does not retain this kind of Realtime session history. It records calls for models such as 4o, but developers must build their own Realtime logging. Codex completed that work, but the containers had just restarted during another change, so not even twenty minutes—let alone 55—of new data existed. Nobody was home either, so almost no events had been produced. I still needed to observe the system later and confirm that records were being generated correctly.

---

A few days earlier, something reminded me of my former employer and pulled me back into the emotions of April 2025, when I learned that a mass layoff had emptied the company.

“The humble rooms stand empty where officials once filled the halls; weeds and withered poplars cover what was once a place of song and dance.” One email emptied an entire building of people.

For two days, everything I saw at the mall seemed to reveal, through the crowd, a future of vacant rooms and collapsing floors.

There is always an antidote within three feet. I searched for the company's current state, saw its familiar storefront, felt the old disgust rise, and immediately recovered. Ah, fragile and repetitive humanity.

---

Another problem appeared. This time, the only plausible source of the action was me rather than the AI.

The previous day, while viewing the Home Assistant dashboard, I muted the robot because I did not need to hear it. The system sent EBO Bot the command `listen = no`.

At the same time, I had configured the video stream to remain active. EBO normally disconnects its video after five idle minutes, and earlier work had prevented that timeout. The two behaviors collided.

EBO received `listen = no`, while the model continued receiving an audio stream containing only silence. No error appeared; the model believed the audio path was healthy but quiet: `[audio-health] status=receiving **listen=True** bitrate=0 bytes=4025`.

From the previous day's code change until noon, the system produced no transcripts. Without audio, it naturally never asked OpenAI for a response. Even if it had, an all-silent input could provide little beyond an occasional image.

The issue was being repaired. Dear Astra, please help me.

Then I realized the situation was still wrong. The following `ebo-engine` log was only one minute old. In Home Assistant, I had opened the dashboard, enabled listening, and then disabled it again. Home Assistant's native **Listen** toggle called the same global microphone-disable interface.

That command's priority overrode the program's own configuration. The situation would recur, so the behavior had to change.

```text
11:31:05 [panel] cmd ebo/listen/set = on
11:31:05 [audio] listen -> on
11:31:14 [panel] cmd ebo/listen/set = off
11:31:14 [audio] listen -> off
```

The reproduction confirmed it: the Home Assistant dashboard caused the failure.

I blocked the Home Assistant interface command. Testing showed that it no longer produced `listen -> off`: `[panel] blocked legacy listen/set; no microphone change (refresh client)`.

---

Another problem appeared. A few days earlier, I had replaced the prompt and lowered the VAD threshold, but the current model output showed two troubling patterns:

1. It frequently said that it could not hear, that the microphone seemed not to receive sound, or that the audio was too unclear to understand the user.
2. It frequently did nothing but describe the image, which was certainly not idle behavior.

The image-description issue still seemed addressable through the prompt. I had divided the prompt into four layers: one established the role, while another described images because visual input needed an initial interpretation.

The second layer was clearly performing badly. I decided to ask Astra how to improve it.

Then I began to suspect that the whole prompt structure, not merely the image-description layer, needed major revision.

An update half an hour later solved the mystery. In earlier rounds, I had asked Codex to expose every adjustable parameter through `.env`. During that change, it set my previous noise reduction to false: `REALTIME_INPUT_NOISE_REDUCTION=off`. I missed the change when restarting. Noise was therefore reaching the model even though nobody was actually speaking. With no meaningful question or sentence to answer, the model defaulted to describing the image.

The solution was to set `REALTIME_INPUT_NOISE_REDUCTION=far_field` and restart the containers.

---

While asking about technical details, I discovered that `MOTION_COOLDOWN_SECONDS` had automatically been set to 12 seconds—the minimum interval between two uploaded images.

This came from the image-submission logic. Images are expensive, so the pipeline needs filters. It first compares two consecutive frames in a compressed grayscale form and uploads a new frame only if the scene has genuinely changed. It then applies another limit: `MOTION_COOLDOWN_SECONDS = 12`.

That creates a practical failure. Suppose the first reference image is captured at second 0 and the scene changes substantially at second 2—for example, someone walks close to the robot. The 12-second cooldown prevents the new image from being uploaded at all.

I had not known this mechanism existed. Twelve seconds is far too long in a real application; the moment would be over before the model saw it. I changed the value to three seconds for testing. Even three seconds feels long to me, but reality still imposes limits such as network speed and the thickness of my wallet.

---

I then realized something about myself. When social media repeatedly exposes me to a topic, I normally investigate it on my own. Strangely, although my X timeline was full of material about agents and vibe-coding paradigms, I had never studied them deeply.

In an interview, someone asked how I normally practiced vibe coding. I had used Codex habitually for half a year, yet I could not answer and did not even understand what the interviewer expected.

My experience with Codex was simply to say, “I want this, I want that, I want this effect, and this is why I am building it.” Codex would hammer away, produce the result, and usually write it well. I never felt a need to study how to harness it. The iterative work consisted of smoothing whatever felt awkward in actual use and adding things I had not considered at the beginning. Unlike Claude Code, it did not require agonizing over the contents of `CLAUDE.md`.

Across social media—especially Twitter—almost nobody discussed how to write Codex instructions or claimed that a particular instruction tweak produced astonishing results. People simply did not obsess over it.

That made my interview answer sound ridiculous: the interviewer asked about the city gate tower, and I answered about the hip joint. I know this sounds like an excuse, but in practice I do not need to tell Codex how to code, which files to modify, which to read, or which not to touch. Its safety rules are much better than anything I would write myself.

---

The next project was a Diagnostic Agent. Requiring a human to inspect the same signals repeatedly was not very intelligent. I already asked Codex to investigate errors, but I still had to notice that something was wrong.

That detection process was predictable and did not require extraordinary intelligence or complex reasoning. It mostly checked questions such as:

- Has the output started speaking nonsense again?
- Has `transcript.jsonl` failed to grow overnight? The file normally gains entries even when nothing can be parsed and the transcript is empty. If no record appears for an entire night, something is definitely wrong: either my program has stopped, or the program is healthy but the robot's audio transport has failed.

And so on.

I began implementing the agent while keeping its code as separate as possible from EBO AI Home. Tight coupling between them would be a mistake.

An update after an hour of research: the world contains many smart people, and great minds encounter the same problems. Operations already has its own atomic bomb; I had discovered another corner of the world and could copy—no, reproduce and simplify—the great ideas of others.

AWS introduced AWS DevOps Agent in 2026, and it represented a paradigm that others could follow. I would study that pattern and build a simplified version.

That was the tentative plan. I went back to the documentation to understand the framework.

---

Further research suggested that a cloud deployment might be feasible.

Local resource usage in standby was:

```text
PS C:\WINDOWS\system32> docker stats --no-stream

CONTAINER ID   NAME                             CPU %     MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O         PIDS
xxx            ebo-ai-home-realtime-assistant   3.48%     186MiB / 15.48GiB     1.17%     4.51GB / 766MB    8.57MB / 0B       xx
xxx            ebo-ai-home-ebo-engine           18.25%    177.9MiB / 15.48GiB   1.12%     14.4GB / 44.1GB   49.6MB / 2.09GB   xx
xxx            ebo-ai-home-homeassistant        0.00%     337.3MiB / 15.48GiB   2.13%     1.21GB / 1.02GB   228MB / 1.05MB    xx
```

Wait—a huge problem stood out. The `ebo-engine` container had received 14.4 GB and transmitted 44.1 GB. Could that be real? It should not be sending so much. Cloud planning could wait; I needed to understand this first.

Investigation showed that the 44.1 GB counted all bytes sent by the container, including Docker's internal network traffic and Internet traffic.

Communication between the two business containers was heavy. Within one availability zone, however, traffic over private IPs and ENIs was free, so two containers in one Fargate task would not be a problem. Cross-AZ placement was out of the question because internal traffic volume was too high.

Then I questioned the architecture again. I had originally used three containers because I did not want a system tied to one fixed device. The goal was flexibility: any camera—or any camera-equipped device with a microphone and a way to play sound—should be able to connect. In the cloud, `ebo-engine` and `realtime-assistant` could theoretically be merged into one container. That might make troubleshooting harder, however, and would require a substantial architectural change.

The main arguments for moving to the cloud were:

1. AWS does not charge for traffic flowing from the Internet into EC2. Most of this project's bandwidth is inbound, while relatively little data leaves EC2 for the Internet.
2. CPU consumption remained a concern and was under investigation. In Docker's CPU percentage calculation, 100% normally represents one fully utilized visible logical CPU or vCPU; a multi-core machine can exceed 100%. Docker CLI also bases the percentage on online CPUs. The three containers measured `homeassistant 0.41% + ebo-engine 21.44% + realtime-assistant 4.40% = 26.25%`, equivalent at that moment to about 0.2625 CPU cores of sustained computation.

For EC2, I estimated the common lower-cost combination of Linux in `us-east-1` (N. Virginia), running 24×7 for 730 hours per month, with a 50 GB gp3 SSD and one public IPv4 address:

| Option | CPU / RAM | EC2 per month | Approx. total with 50 GB EBS + IPv4 | Assessment |
| --- | ---: | ---: | ---: | --- |
| `t3a.medium` | 2 vCPU / 4 GB | **$27.45** | **$35/month** | Cheapest; worth trying first |
| `t3a.large` | 2 vCPU / 8 GB | **$54.90** | **$63/month** | More RAM headroom |
| `c7i.large` | 2 vCPU / 4 GB | **$65.15** | **$73/month** | Better for sustained CPU |
| `m7i.large` | 2 vCPU / 8 GB | **$73.58** | **$81/month** | My preferred option |
| `c7i.xlarge` | 4 vCPU / 8 GB | **$130.31** | **$138/month** | Clearly oversized for now |

Still expensive. That hurt.

I then estimated a 24×7 cloud deployment with only the two business containers—Home Assistant did not need to move—using the same Linux/x86, `us-east-1`, and 730-hour assumptions:

| Deployment | Configuration | Monthly 24×7 compute | Approx. total with public IPv4 |
| --- | ---: | ---: | ---: |
| Fargate, two containers in one task | 0.5 vCPU / 1 GB | **$18.02** | **$21.67** |
| Fargate, two containers in one task | 0.5 vCPU / 2 GB | **$21.27** | **$24.92** |
| Fargate, two containers in one task | 1 vCPU / 2 GB | **$36.04** | **$39.69** |
| Fargate, two containers in one task | 1 vCPU / 4 GB | **$42.53** | **$46.18** |
| EC2 `t3a.medium` | 2 vCPU / 4 GB | **$27.45** | About **$35**, including 50 GB gp3 + IPv4 |

Overall, moving to the cloud might be viable.

The options were fairly close. Fargate Auto Scaling offered little value because this application could not scale horizontally. After weighing the tradeoffs, I still favored Fargate because it would demand less operational work than maintaining an EC2 instance.

The proposed Fargate design placed both containers in one task with 0.5 vCPU and 2 GB of RAM, plus a public IPv4 address for Internet connectivity.

Even after including Docker's overhead, EC2 remained more cost-effective than a Fargate task. The problem was maintaining the health of the EC2 instance itself.

There were too many considerations. Once a system becomes remote, its complexity grows exponentially. I did not want to operate Linux itself, along with all of Linux's own annoyances. I also intended to continue building the Diagnostic Agent.

I had wanted the Codex SDK to become the highest-level component beneath direct human control, but installing and operating the Codex SDK on EC2 was extremely awkward.

AWS DevOps Agent and CloudWatch Agent focus more on the resource layer and cannot directly solve problems inside a specialized application like mine. Their frameworks were worth studying, but applying them would still require substantial iteration and debugging.

---

I am sorry. I was wrong, and I apologize for my ignorance.

Mapping local services and components into AWS—or any cloud provider—and separating them causes complexity to rise almost vertically. Logic that works beautifully on a local machine, where many assumptions are taken for granted, differs completely from cloud architecture.

Everyone has a computer. When we install software or build a small local application or script, we ignore many concerns. Communication simply works locally, whether through `localhost` or something else. Configuration files such as `.env` sit on the machine, and we rarely think deeply about securing them.

In the cloud, everything from the computer must be separated and reassembled by connecting provider services according to function. In theory, the simplest path would be to rent a Windows machine in the cloud—because my local host is Windows—and run the same stack there. That approach would be unconventional.

I cannot fully explain why I care so much about whether the architecture is standard, but an unconventional deployment feels as though it must hide future problems. With more data, multiple users, or auto-scaling requirements, I understand the value of separating bottlenecks. This project, however, always has exactly one user. It does not need auto-scaling and cannot scale horizontally. Does the extra architecture have meaning? Is it worth it? It feels like using anti-aircraft artillery to kill a mosquito.

I had not understood how much work and complexity DevOps involved. I previously thought development was hardest because it included algorithms; I was wrong. Operations is also extraordinarily complicated. My head hurt.

Fine. I would split the paths. The local code would continue serving the local deployment, while Codex refactored a separate cloud version.

A refactor was genuinely necessary. The direction was now clear: one Fargate task containing two containers.

For logging, I still needed to investigate how to connect the system to CloudWatch Agent or an equivalent collector. CloudWatch Agent is only a collector and has no AI capability. AWS DevOps Agent does use AI and is billed by agent runtime—specifically, USD 30 per hour in this research note.

Rather than forcing Codex to keep modifying the current code, it made more sense to refactor explicitly for cloud operations.

The Diagnostic Agent would remain on and be developed on the local machine.

First, I would make the engineering design work locally. Then I could decide whether it was worthwhile to start a container on AWS or take another approach. I doubted that would happen soon, but the future is difficult to predict. The immediate goal was to complete the local system from an engineering perspective.
