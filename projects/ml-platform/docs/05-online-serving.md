Status: Draft
Owner: ML platform team
Canonical for: Online HTTP serving as an ACA App at an exact model version
Depends on: [00 — Production architecture](./00-production-architecture.md), [02 — Reproducible ML](./02-reproducible-ml.md)
Last reviewed: 2026-07-30

# 05 — Online serving

## Outcome

When a model needs low-latency online inference, it is served by an ACA App whose
container loads an **exact MLflow model version** at startup. We bring our own
image, so there is no framework/runtime lock-in; rollback is a version change, not
a rebuild; and the running app's model identity is unambiguous.

Online serving is **optional** — batch-only deployments skip this document.

## Production decisions

### Serving is an ACA App with our own image

The serving container is our image (FastAPI or similar) that, at startup, loads
`models:/<name>/<version>` from the self-hosted MLflow registry and exposes an
HTTP inference endpoint. Because it is our image, we control the framework,
runtime, and dependencies — the freedom that motivated self-hosting MLflow in the
first place ([00](./00-production-architecture.md)).

### Exact version pinning

The served model version is pinned in the App definition (an env value or config),
never "latest" and never a floating alias resolved at request time. The resolved
version is logged at startup and exposed on a readiness/health response so the live
version is externally verifiable.

### Deploy and rollback

- **Deploy** = update the App definition to a new image digest and/or a new model
  version. ACA rolls out a fresh revision.
- **Rollback** = point the App definition back at the previous digest/version. No
  rebuild required; the previous model version is still in the registry.

Promotion of a model version to "serving" status follows [06](./06-release-and-operations.md).

### Identity and secrets

The App runs as `id-serving` with read-only access to MLflow artifacts and Key
Vault. It holds no write access to training data or the registry. Any external
credentials are resolved at runtime via managed identity.

### Health and scaling

The App exposes readiness (model loaded, version reported) and liveness. ACA
scales it per HTTP load, including to zero if the workload tolerates cold starts;
otherwise a minimum replica count keeps it warm.

## Shared concepts

- **Exact version pin** — the App serves one named registry version, logged and
  health-reported.
- **BYO image** — serving runtime is ours, not a managed provider's.
- **Version rollback** — revert the App definition; no rebuild.

## Target design

- A serving image in the repo and an IaC-defined ACA App bound to `id-serving`.
- Startup loads the pinned `models:/name/version`; `/health` reports the resolved
  version and load status.
- CI updates the App definition on promotion; rollback is a definition revert.

## Runnable demonstration

The current repo has a stubbed inference path locally. Acceptance requires an ACA
App loading a real registered version from the self-hosted MLflow and reporting it
on `/health`, plus a demonstrated version rollback.

## Failure modes and acceptance evidence

| Failure mode | Prevented by | Acceptance evidence |
|---|---|---|
| Ambiguous live model | Exact version pin + health report | `/health` shows the exact served version |
| Rollback requires rebuild | Version/digest revert in App definition | Revert restores prior version without rebuilding |
| Framework lock-in | BYO serving image | Serving runtime/deps chosen freely |
| Over-privileged serving | `id-serving` read-only roles | No write access to registry/training data |

## Open decisions

- Whether launch scope includes online serving or is batch-only initially.
- Warm minimum replicas versus scale-to-zero per model's latency SLO.

## References

- Model identity and MLflow — [00](./00-production-architecture.md), [02](./02-reproducible-ml.md).
- Promotion and rollback flow — [06](./06-release-and-operations.md).
