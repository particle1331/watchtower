Status: Draft
Owner: ML platform team
Canonical for: CI/CD, promotion, rollback, observability, alerting, and the workflow dashboard
Depends on: [00 — Production architecture](./00-production-architecture.md), [01 — Platform foundation](./01-platform-foundation.md), [04 — Periodic & batch workflows](./04-periodic-and-batch-workflows.md), [05 — Online serving](./05-online-serving.md)
Last reviewed: 2026-07-30

# 06 — Release & operations

## Outcome

Code ships through GitHub Actions (build/test/scan/deploy only), models are
promoted and rolled back by version, and the whole platform is observable through
three non-overlapping layers plus one lightweight dashboard that unifies them. An
operator can see what is scheduled, what is running, what failed and why, and can
launch or rerun a workflow with an audit trail.

## Production decisions

### CI/CD stays in its lane

GitHub Actions does exactly four things and nothing more:

1. **Build** container images (Jobs, serving App, MLflow, dashboard).
2. **Test and scan** them.
3. **Push** to ACR by digest.
4. **Update** ACA Job/App definitions (image digest, env, schedule) via IaC.

It is **never** a scheduler or orchestrator — scheduling lives in ACA Job triggers
([04](./04-periodic-and-batch-workflows.md)) and orchestration lives in job
scripts + the results DB. CI authenticates via OIDC as `id-ci` with push +
definition-update rights only, no runtime data access.

### Promotion is a version + definition change

Promoting a model means: an evaluated registry version ([02](./02-reproducible-ml.md)/[03](./03-llm-release-artifacts.md))
is marked as the promoted version (MLflow stage/alias or an equivalent tag), and
the relevant Job/App definition is updated to reference that version. There is no
hash-chained release ledger; provenance is:

> registered version → its evaluation record → Git tag → deployed Job/App image
> digest.

That chain answers "what is live and where did it come from" without bespoke
machinery.

### Rollback

- **Model rollback** — repoint the Job/App definition at the previous promoted
  version (still in the registry). No rebuild.
- **Code rollback** — repoint the definition at the previous image digest (still
  in ACR). No rebuild.

Both are reviewed IaC/definition changes, not portal edits.

### Observability: three layers, no duplication

| Layer | Answers | Source |
|---|---|---|
| **Results DB** | What ran, is running, failed, and why — per run and per batch item | Postgres `results` table ([04](./04-periodic-and-batch-workflows.md)) |
| **Log Analytics / App Insights** | Infra telemetry + alerts | ACA execution logs/metrics |
| **Azure Managed Grafana** | Deep operational dashboards | Postgres (`results`) + Azure Monitor (Log Analytics + App Insights) |

The results DB is canonical run state. Log Analytics/Grafana add infra depth. We do
not re-record run state in three places.

### Alerts

Alert rules (Log Analytics/Azure Monitor) fire on the conditions that actually
page a small team:

- a Job execution **failed**,
- a scheduled run was **missed** (no execution in the expected window),
- **permanent failures** (`FAILURE` children) exceed a per-workflow threshold,
- a batch is **stalled** (no progress before the circuit breaker trips).

### The workflow dashboard

A lightweight ACA App (Streamlit or FastAPI) is the human surface. It is a
**catalog + launcher**, not a new source of truth:

- **Lists** every registered workflow (scheduled and manual) with type, schedule,
  last-run status/duration, records processed + drift, and model version.
- **Reads** status from the ACA job-execution API and the results DB, and model
  links from MLflow.
- **Deep-links out** to Grafana (charts) and MLflow (model detail) instead of
  re-implementing them.
- **Launches** workflows: "Run now" and "Run with params…" call the ACA execution
  API; every manual start records `triggered_by = <caller email>`. That email is
  the initiator's **Entra sign-in identity** (from Easy Auth), not the
  `id-dashboard` managed identity that authorizes the call — authorization is by
  machine identity, attribution is by human identity.
- **Auth**: Entra ID Easy Auth; runs as `id-dashboard` with a scoped
  trigger role; least privilege.

> **The dashboard is decoupled from execution.** It launches runs but does not
> host them. If the dashboard App is down, scheduled runs still fire (ACA cron)
> and in-flight executions keep running (independent containers). And a manual
> run is never blocked on the UI: **you can still trigger any workflow directly
> via the ACA execution API/CLI** (`az containerapp job start …`) with the same
> identity and audit. The dashboard is a convenience surface, not a dependency.

The intended surface is captured in
[`mockups/workflow-dashboard.html`](./mockups/workflow-dashboard.html).

## Shared concepts

- **Promotion** — marking an evaluated version as live + updating a definition.
- **Provenance chain** — version → evaluation → Git tag → deployed digest.
- **Three-layer observability** — results DB (state) + Log Analytics (infra) +
  Grafana (dashboards).
- **Catalog + launcher dashboard** — reads and triggers; stores nothing
  authoritative.

## Target design

- GitHub Actions workflows for build/test/scan/deploy under `.github/workflows/`,
  authenticating via OIDC.
- Promotion action that sets the promoted version and updates the Job/App
  definition.
- Alert rules in IaC; Grafana dashboards provisioned as code where practical.
- Dashboard App in `src/ml_platform/` bound to `id-dashboard`.

## Runnable demonstration

Not yet demonstrated. Acceptance requires: a CI run that builds and deploys a
digest; a promotion + rollback by version; alert rules firing on an injected
failure; and the dashboard listing workflows and launching an audited manual run.

## Failure modes and acceptance evidence

| Failure mode | Prevented by | Acceptance evidence |
|---|---|---|
| CI becomes orchestrator | GitHub Actions restricted to build/deploy | No scheduling/orchestration in workflows |
| Risky/opaque rollback | Version/digest revert via definition | Rollback restores prior model/code without rebuild |
| Silent failures | Alert rules over results DB + infra | Injected failure/missed run pages within the window |
| Duplicated/os inconsistent run state | Results DB canonical; others additive | Dashboard and alerts agree; one source of run truth |
| Unaudited manual trigger | Scoped role + `triggered_by` | Manual run shows caller in results DB and dashboard |

## Open decisions

- MLflow stage/alias versus a tag convention for "promoted".
- Grafana dashboard-as-code coverage at launch.

## References

- Results DB and continuation — [04](./04-periodic-and-batch-workflows.md).
- Identities for CI and dashboard — [01](./01-platform-foundation.md).
- Serving rollback — [05](./05-online-serving.md).
- Dashboard mockup — [`mockups/workflow-dashboard.html`](./mockups/workflow-dashboard.html).
