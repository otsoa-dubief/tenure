# Security policy

Tenure is a guard: it decides whether an AI agent may act alone, keeps a signed ledger of what happened, and protects itself from the agent it watches. A flaw in any of that is a security issue, and reports are welcome.

## Supported versions

Only the latest release receives fixes. Today that is 1.1.x.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting instead: on this repository, open the **Security** tab and click **Report a vulnerability**. Include the Tenure and Hermes versions, the steps to reproduce, and what you expected to happen.

You will get an acknowledgement as soon as possible, and a fix or a written answer once the report is understood. Reporters are credited in the release notes unless they ask otherwise.

## What counts

- an agent acting alone where the rule says it should ask, or removing, disabling or editing Tenure without the owner's approval;
- a way to forge, rewrite or truncate the ledger, or to produce a passport that verifies but does not match the ledger;
- a secret shown in clear where Tenure claims to mask it, or written to the ledger;
- a crash or an error that makes Tenure stop guarding without saying so.

## Known limits

Some limits are declared on purpose and are not vulnerabilities in themselves: see [docs/self-protection.md](docs/self-protection.md). If you find a way around one of them that the document does not describe, please report it.
