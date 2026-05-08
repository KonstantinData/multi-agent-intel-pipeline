# Target Server Deployment

## Purpose

This document defines the target server model for making Liquisto available as
a browser-based product at:

```text
https://liquisto.condata.io
```

The target is not a local developer setup and not a user-installed desktop
application. Future users access Liquisto only through the hosted web address.
They do not install Python, Docker, repository files, local dependencies, or API
keys on their own machines.

This document is the deployment-side companion to the runtime architecture:

- `docs/drawio/target_runtime_architecture.md`
- `docs/target_runtime_architecture.md`
- `docs/review-gates.md`

## Target Outcome

Liquisto is operated as a server-hosted Streamlit application. Authorized users
open `https://liquisto.condata.io` in a browser and receive access to the
product through that entry point.

User-side requirements:

- a modern browser
- internet access
- an approved login method if access control is enabled

User-side non-requirements:

- no local Liquisto installation
- no Python installation
- no Docker installation
- no cloned repository
- no local OpenAI API key
- no local `.env` setup

## Target Hosting Model

The intended production path is:

```text
User browser
  -> liquisto.condata.io
  -> Cloudflare DNS / Access / WAF
  -> Cloudflare Tunnel
  -> Hetzner server
  -> Docker Compose
  -> Liquisto Streamlit container on port 8501
```

Cloudflare is responsible for the public edge:

- DNS for `liquisto.condata.io`
- TLS termination at the edge
- optional WAF and rate limiting
- access control through Cloudflare Access
- tunnel routing to the Hetzner host

Hetzner is responsible for compute:

- Linux server runtime
- Docker Engine and Docker Compose
- Liquisto application container
- `cloudflared` tunnel container or service
- persistent run/report storage where required
- host-level operational controls, logging, backups, and patching

The Liquisto application container should remain reachable only from the local
host or Docker network. Port `8501` should not be exposed directly to the public
internet.

## Access Model

The product entry point is `https://liquisto.condata.io`.

The preferred access model is controlled access through Cloudflare Access:

- allow listed email addresses or identity-provider groups
- one-time PIN, Google, Microsoft, or another configured identity provider
- no anonymous public access for production use unless explicitly accepted as a
  business decision

Cloudflare Access protects entry to the hosted application. Liquisto runtime
authorization and run-level data visibility are separate application concerns
and must be reviewed before broad customer or multi-organization use.

## Deployment Model

GitHub Actions remains the control point for CI/CD.

The target deployment flow is:

1. A push or pull request to `main` runs the compliance/security/test gates.
2. A release or approved deployment workflow builds the OCI image.
3. The image is pushed to GitHub Container Registry.
4. The Hetzner host pulls the approved image.
5. Docker Compose restarts Liquisto with the new image.
6. A post-deployment smoke check verifies `https://liquisto.condata.io`.

The deployment workflow should not bypass the existing security pipeline.
Deployment should depend on the successful aggregate status gate, not on a
manual judgment that individual jobs "look green".

## Secrets And Configuration

Runtime secrets are server-side or deployment-side only.

Required secret categories:

- OpenAI API key or equivalent model-provider credential
- Cloudflare tunnel token or tunnel credentials
- GitHub Container Registry pull credential if the image is private
- deployment SSH key or another controlled Hetzner deployment credential

Secrets must not be stored in the repository, committed `.env` files, generated
reports, run artifacts, SBOMs, AI-BOMs, logs, or screenshots.

Configuration should be supplied through:

- GitHub Environment Secrets for deployment automation
- server-side environment files outside git
- Docker Compose environment references
- Cloudflare-managed tunnel/access configuration

## Persistent Data

Liquisto produces run artifacts, reports, memory snapshots, and follow-up
history. In the hosted model, these artifacts live on the server side.

Before production access, the project must define:

- which directories are persistent Docker volumes
- backup and restore expectations
- retention periods for run artifacts and reports
- whether different users or customers can see each other's runs
- whether run data requires per-user, per-customer, or per-organization
  isolation

The current target server model establishes the hosting path. It does not by
itself prove multi-tenant application isolation.

## Security Pipeline Fit

The existing security pipeline must be reviewed against this target server
model. At minimum, the pipeline should cover:

- lint and type gates for application correctness
- SAST for source-level security defects
- dependency vulnerability scanning from the locked dependency set
- secret scanning of current tree and history
- Dockerfile hardening
- pinned GitHub Actions and pinned Docker scanner images
- SBOM generation and validation for the deployable artifact
- AI-BOM generation and validation for configured model use
- container image build and provenance/SBOM attestations
- deployment workflow hardening
- branch protection and required aggregate status checks
- post-deployment smoke checks for `liquisto.condata.io`

Any new deployment workflow for Hetzner and Cloudflare must follow the same
hardening standard as the existing workflows: least-privilege permissions,
timeouts, concurrency, no placeholder shell blocks, no unpinned external
actions, and no direct secret exposure in logs.

## Initial Non-Goals

The target server model does not require:

- Azure App Service
- a native desktop installer
- user-side Docker Desktop
- user-side Python setup
- direct public exposure of the Streamlit port
- storing user secrets on user devices

## Open Decisions

The following items must be settled before production rollout:

- exact Cloudflare Access policy
- Hetzner server size and region
- GHCR private vs public image policy
- deployment trigger: tag, manual approval, or protected environment
- persistent volume layout
- backup location and schedule
- log retention and redaction policy
- user/customer data isolation model
- rollback strategy
- operational owner for server patching and incident response
