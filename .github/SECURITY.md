# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do not open a public issue.**

Instead, please use GitHub's private vulnerability reporting (the repository's **Security** tab → **Report a vulnerability**) to submit a report. Include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You should receive a response within a few days. I'll work with you to understand the issue and coordinate a fix before any public disclosure.

> **Note:** Private vulnerability reporting must be enabled on the repository for the link above to work. Enable it under **Settings → Code security → Private vulnerability reporting**.

## Scope

This is a learning lab, not production software. It deploys short-lived OSS AI gateways into a GCP lab project and tears them down at the end of each phase. Reports about the lab's own Terraform, agent, harness or tooling are in scope; vulnerabilities in LiteLLM, Bifrost or Kong themselves should go to those projects.

## Supported Versions

Only the latest version on the `main` branch is actively maintained.

## Security Measures

- **`.gitignore`** excludes Terraform state, tfvars, `.env` files and service-account keys
- **Pre-commit hooks**, when installed, run gitleaks and private-key detection on staged changes before each commit (`.pre-commit-config.yaml`). They are opt-in per clone and can be bypassed with `--no-verify`
- **Least-privilege identities**: one service account per gateway, and gateways can read only `agw-*` secrets
- **No long-lived keys** in the repo; any keys used for testing live in Secret Manager

## Disclosure Policy

Once a vulnerability is confirmed and fixed, a security advisory will be published with appropriate details.
