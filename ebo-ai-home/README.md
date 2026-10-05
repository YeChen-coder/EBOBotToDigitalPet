# EBO Bot: Frigate Sessions and Diagnostic Agent

> **Branch: `frigate` — the Frigate edition, not main.** This architecture currently targets local operation; its new AWS Dashboard migration is unfinished. The complete local/cloud + Diagnostic Agent edition is [`main`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/main). [Version guide](../VERSION-GUIDE.md).

[中文说明](README.zh-CN.md)

The current local version connects the Enabot EBO Engine to Frigate, Mosquitto, finite Realtime voice sessions, separate family memories, and an updated Diagnostic Agent.

**Release status (2026-10-03): the local implementation is published. The AWS side of the Diagnostic Dashboard has NOT been migrated to this architecture or validated.** Existing ECS/Fargate adapters, CloudWatch readers, and AWS documents remain as legacy references. They do not establish support for this release on AWS. The example configuration uses `runtimeControlScope: "local"`; cloud startup is disabled and local start/stop does not control AWS.

The complete previous GitHub version is preserved on [`archive/pre-frigate-2026-10-03`](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/archive/pre-frigate-2026-10-03). See [release and migration notes](docs/RELEASE-2026-10-03.md) for the architecture changes and remaining AWS work.

## Current architecture

```text
EBO -> Engine RTSP -> Frigate frames / face recognition -> MQTT identity hints
   -> Engine audio listener -> complete-utterance wake validation -> Realtime session
   <- Engine PCM talkback <- Realtime output (WAV fallback)
                            -> per-user session summaries and long-term memory

Diagnostic Dashboard -> local controls / assistant pause / session controls
                    -> Watcher -> bounded recovery -> triage -> advanced diagnosis
```

Voice wakes the assistant after transcription validates a complete utterance; face recognition supplies identity hints. Unconfirmed identity uses a temporary guest session without access to parental memories. Frigate images provide the latest frame during a conversation. Automatic Realtime responses and interruptions are disabled; the primary final transcript gates responses, while an independent live transcription channel records speech. The default takes turns speaking and excludes microphone input during playback and its tail guard. Local interruption remains experimental.

The Diagnostic Agent now understands `specter-ebo-v2`, the five local services, standby without a Realtime connection, audio listener health, Frigate/MQTT conditions, and assistant pause/session controls. It checks real recovery independently of model conclusions. See [audio-first behavior](docs/assistant-audio-first.zh-CN.md), [pause controls](docs/assistant-pause.zh-CN.md), and the [migration details](docs/specter-migration.zh-CN.md).

## Local setup

Requirements: Windows, Docker Desktop, PowerShell, and Node.js 22 or newer for diagnostics tooling.

Run these commands from `ebo-ai-home`, rather than the repository root:

```powershell
Copy-Item .env.example .env
# Supply your own account, device keys, API key, region and host address in .env.
.\scripts\prepare-ebo.ps1
.\scripts\start-ebo-home.ps1 -RebuildAllServices
Invoke-RestMethod http://127.0.0.1:8099/health
```

The start script builds the business and diagnostic images, refreshes the diagnostic source snapshot, recreates services, restores the host tasks, and checks health. The first diagnostic setup creates local configuration and internal tokens in observation mode. Review the [diagnostic setup guide](ops/diagnostics/README.zh-CN.md) before enabling recovery and model diagnosis.

- [Diagnostic Dashboard](http://127.0.0.1:8179): local runtime status, pause/resume, family sessions, diagnostics, and transcripts.
- [Home Assistant](http://127.0.0.1:8123): device controls and cameras.
- [Frigate](https://127.0.0.1:8973): this project's separate face library and login.

Stop with `.\scripts\stop-ebo-home.ps1`; configuration and persistent data are retained. Configure parent face enrollment using `.\scripts\register-parent-faces.ps1`; see [Chinese instructions](README.zh-CN.md) for usage and deployment details.

## Privacy and credentials

The public snapshot excludes real `.env` files, account/device secrets, AWS credentials, Engine options, Home Assistant instance data, Frigate faces/media/models, family memories, transcripts, recordings, generated audio, diagnostic state, and `private/`. Supply these locally; do not commit runtime data. See [public snapshot notes](PUBLIC_SNAPSHOT.md).

## Tests

```powershell
cd ops/diagnostics
$tests = Get-ChildItem -LiteralPath test -Filter '*.test.mjs' | Select-Object -ExpandProperty FullName
node --test $tests
```

Assistant unit tests are in `realtime-assistant/tests`; Engine tests are in `ha-enabot/ebo/tests`. Run them with their Python dependencies in an isolated environment. Real API/robot smoke scripts are separate from unit tests. Synthetic AWS adapter tests do not validate the new AWS deployment.

## Licenses

Original project code uses the MIT License. Vendored components retain their upstream licenses; see [VENDORED_SOURCES.md](VENDORED_SOURCES.md).
