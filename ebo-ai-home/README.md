# EBO Bot Local and Diagnostic Agent

This repository runs an Enabot EBO assistant either on a local Docker host or on AWS Fargate, with one bilingual dashboard for runtime control, diagnostics, and conversation transcripts.

## What it includes

- Local EBO Engine, Home Assistant, and Realtime Assistant services.
- A three-state runtime controller: **Run in cloud**, **Run locally**, or **Stop everywhere**.
- Safe switching that stops and verifies one environment before starting the other.
- A Diagnostic Agent with deterministic health checks and bounded recovery before model diagnosis.
- Two diagnostic tiers: `gpt-5.6-luna / low` for triage and `gpt-5.6-sol / high` for advanced diagnosis.
- A bilingual English/Chinese dashboard at `http://127.0.0.1:8179`.
- A combined local and CloudWatch transcript timeline with cached, budget-aware cloud polling.

## Privacy and credentials

Runtime secrets and household data are intentionally excluded from Git. This includes `.env`, Home Assistant storage and databases, EBO data, conversation transcripts, generated audio, diagnostic state, AWS credentials, and files under `private/`.

Copy the example configuration files and add credentials only on the machine that runs the services:

```powershell
Copy-Item .env.example .env
Copy-Item ops/diagnostics/.env.example ops/diagnostics/.env
```

Review both `.gitignore` files before adding new runtime outputs.

## Local services

Requirements:

- Windows with Docker Desktop
- PowerShell
- Node.js 22 or newer for the Diagnostic Agent tooling

Configure `.env`, then start the local assistant stack:

```powershell
docker compose --profile assistant up -d --build
```

Install and start the Diagnostic Agent from `ops/diagnostics`:

```powershell
node scripts/setup.mjs
docker compose build
powershell.exe -NoProfile -File scripts/install-host-task.ps1
```

See [`ops/diagnostics/README.zh-CN.md`](ops/diagnostics/README.zh-CN.md), [`ops/diagnostics/USAGE.zh-CN.md`](ops/diagnostics/USAGE.zh-CN.md), and [`ops/diagnostics/AWS.zh-CN.md`](ops/diagnostics/AWS.zh-CN.md) for configuration and operating details.

## Tests

```powershell
cd ops/diagnostics
$tests = Get-ChildItem -LiteralPath test -Filter '*.test.mjs' | Select-Object -ExpandProperty FullName
node --test $tests
```

## Vendored projects

The `ha-enabot` and `ha-llmvision` directories preserve their upstream licenses. See [`VENDORED_SOURCES.md`](VENDORED_SOURCES.md) for source revisions.

## License

Original code in this repository is available under the MIT License. Vendored components remain under the licenses included in their directories.
