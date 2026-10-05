# Security and privacy

> **Branch: `main` — the complete local/cloud + Diagnostic Agent edition.** The separate [Frigate edition](https://github.com/YeChen-coder/EBOBotToDigitalPet/tree/frigate) is not main; its unfinished AWS migration does not apply to this edition's existing AWS integration. [Version guide](../VERSION-GUIDE.md).

Do not commit runtime credentials, Home Assistant storage, EBO account data, conversation transcripts, generated audio, diagnostic state, or AWS credential files.

Use the provided example configuration files and keep real values in ignored `.env` files. If a credential is committed accidentally, revoke it before removing it from Git history.

Security reports should be sent privately to the repository owner through their GitHub profile rather than opened as public issues.
