Status: Draft
Owner: ML platform team
Canonical for: Azure resource inventory, identities, RBAC, IaC, networking
Depends on: [00 — Production architecture](./00-production-architecture.md)
Last reviewed: 2026-07-30

# 01 — Platform foundation

## Outcome

Every plane from [00](./00-production-architecture.md) has a home Azure resource,
each workload has its own least-privilege managed identity, and the whole
footprint is described as code so it can be recreated and reviewed. The
foundation is intentionally small — a container registry, a container-apps
environment, two Postgres databases, one storage account, a Key Vault, and a
Log Analytics workspace.

## Production decisions

### Resource inventory

| Resource | Purpose | Notes |
|---|---|---|
| **Azure Container Registry** | Immutable images for Jobs, serving App, MLflow, dashboard | Images referenced by digest, never `latest` |
| **Container Apps Environment** | Hosts all Jobs and Apps | One environment; Log Analytics attached |
| **Azure Database for PostgreSQL (flexible server)** | `mlflow` DB (registry/tracking) + `results` DB (run state) | One burstable/small server, two logical databases; separate logins per identity |
| **Azure Storage (Blob)** | MLflow artifacts, batch outputs, immutable manifests | Separate containers per concern |
| **Azure Key Vault** | Connection strings and any unavoidable secrets | Accessed via managed identity, never baked into images |
| **Log Analytics workspace** | Infra telemetry and alert rules | Feeds App Insights and Grafana |
| **Azure Managed Grafana** | Deep operational dashboards | Reads Log Analytics + Postgres |
| **Microsoft Entra ID** | Workload identities + dashboard sign-in (Easy Auth) | Per-workload managed identities |

This is the entire baseline. There is **no** Service Bus, Redis, Durable
Functions storage, or Azure ML workspace in the foundation — those appear only if
a documented upgrade path (broker) or exception (multi-GPU) is triggered.

### Identities and RBAC

Every workload gets its own user-assigned managed identity with the minimum roles
it needs. No workload shares an identity, and no workload gets broad `Contributor`.

| Identity | Assigned to | Roles (least privilege) |
|---|---|---|
| `id-jobs-train` | Training/eval Jobs | ACR pull; Blob read/write (datasets, artifacts); Postgres access to `mlflow` + `results`; Key Vault secret get |
| `id-jobs-batch` | Batch inference Jobs | ACR pull; Blob read/write (inputs/outputs); Postgres access to `results`; Blob read of MLflow artifacts (read-only model) |
| `id-serving` | Serving App | ACR pull; Blob read of MLflow artifacts; Key Vault secret get |
| `id-mlflow` | MLflow App | Postgres access to `mlflow`; Blob read/write (artifacts) |
| `id-dashboard` | Dashboard App | ACA execution start (scoped to specific Jobs); Postgres read of `results`; Log Analytics read |
| `id-ci` (federated / OIDC) | GitHub Actions | ACR push; ACA Job/App definition update; no runtime data access |

Manual job triggering from the dashboard is gated by a specific role assignment on
`id-dashboard` scoped to the Jobs it may start; every manual start is audited via
the results DB `triggered_by` column.

### Human access via Entra groups

The identities above are **machine** identities (workload-to-Azure auth). **Human**
access is separate: people sign in through the dashboard's Entra Easy Auth, and
who may do what is controlled by **Entra ID security groups**, not by managed
identities. Two groups cover the project's scope:

| Group | Grants | Backing role |
|---|---|---|
| `ml-platform-operators` | Sign in to the dashboard and trigger manual runs | Scoped trigger role (the same one `id-dashboard` uses to start Jobs) |
| `ml-platform-viewers` | Read-only visibility into MLflow and Grafana | `Monitoring Reader` / MLflow read |

Ownership splits cleanly: the **identity team owns group membership** (who is an
operator vs a viewer), the **platform team owns the role assignments** (what a
group can do). Adding or removing a person is a membership change with no infra
change; `triggered_by` still records that person's Entra identity on every run
they start (see [04](./04-periodic-and-batch-workflows.md)).

### Infrastructure as code

The full footprint is defined as IaC (Terraform under `infra/`) and
applied by CI. IaC covers resources, identities, role assignments, and the ACA
Job/App **definitions** (image digest, env, schedule, identity binding).
Human-in-portal changes are not the source of truth.

**Decision:** keep the managed-identity RBAC model in `infra/` as written — the
demo and prod run the **same** code path, so no key/connection-string fallback is
introduced. The one prerequisite is a role-assignment grant for the deploying
principal: `Contributor` (which we hold) can create every resource and the
managed identities, but **cannot write role assignments**
(`Microsoft.Authorization/roleAssignments/write` needs `Owner` or
`User Access Administrator`). The plan is therefore to **request a
`User Access Administrator` grant scoped to the one resource group** from the
subscription owner (see [Open decisions](#open-decisions)); with that grant the
full `terraform apply` succeeds unchanged. This is preferred over a key-based
demo shortcut, which would fork the application's client-construction code and
leave demo != prod.

**One deliberate exception: Postgres grants.** Almost everything above is pure
declarative IaC, including creating the managed identities and every Azure RBAC
role assignment (`AcrPull`, `Storage Blob Data Contributor`, `Key Vault Secrets
User`, the dashboard's Job-start role). Postgres access is the exception: adding
an identity as an Entra principal on the flexible server is IaC, but the per-database
privileges are **SQL that runs inside the database** and cannot be expressed as a
Terraform resource. These live in a checked-in, idempotent **`infra/grants.sql`**
that the deploy pipeline runs (via `psql`) **after** the server and the `mlflow` /
`results` databases exist:

```sql
-- infra/grants.sql — idempotent; run post-provision, after DBs exist.
-- Each workload identity gets least-privilege access to only its database(s).

-- Training/eval Jobs: read/write both mlflow and results.
GRANT CONNECT ON DATABASE mlflow  TO "id-jobs-train";
GRANT CONNECT ON DATABASE results TO "id-jobs-train";
-- Batch Jobs: results only (models are read from Blob, not the DB).
GRANT CONNECT ON DATABASE results TO "id-jobs-batch";
-- MLflow app: mlflow only.
GRANT CONNECT ON DATABASE mlflow  TO "id-mlflow";
-- Dashboard: read-only on results.
GRANT CONNECT ON DATABASE results TO "id-dashboard";
-- (Per-schema/table GRANTs on tables + default privileges follow the same pattern.)
```

It is still code, still in the repo, still reproducible — just executed by `psql`
rather than Terraform. The only sequencing rule is that this step runs after
provisioning, not as part of the main deployment call.

### Networking

Baseline is public endpoints protected by identity (Entra Easy Auth on the
dashboard, managed-identity auth to Postgres/Blob/Key Vault, ACR pull via
identity). Private networking (VNet integration, private endpoints) is an
available hardening step but not required for the baseline to be correct.

**Decision (MVP):** ship the public-endpoint + identity baseline. Everything is
still gated by managed identity, and it is far less to build and debug. Private
endpoints are **deferred to the prod hardening phase**, where they are additive
(attach a private endpoint per resource, flip resources to private, wire private
DNS) rather than a rewrite. This is viable for us because a work VPN and
`Contributor` access are already available to reach and build a private VNet
later. The one thing that would force private-from-day-one instead is an Azure
Policy at the org level that forbids public endpoints — verify no such policy
applies before treating this as settled.

### Secrets

Connection strings and any unavoidable secrets live in Key Vault and are read at
runtime via managed identity. No secret is baked into an image, committed to Git,
or passed as a plaintext env literal in a Job definition.

## Shared concepts

- **User-assigned managed identity** — the unit of workload authorization; bound
  to a Job/App definition in IaC.
- **Job/App definition** — the IaC-owned description of a workload: image digest,
  identity, env, schedule/trigger.
- **Two-database Postgres** — `mlflow` and `results` on one flexible server;
  distinct logins per identity.

## Target design

`infra/` contains modules for: registry, container-apps environment + Log
Analytics, Postgres server with two databases, storage account with containers,
Key Vault, Grafana, and per-workload identities with scoped role assignments. A
`make infra` (or CI job) plans and applies it. Job/App definitions are IaC
resources so a deploy is a reviewed digest change.

## Runnable demonstration

The current `infra/` demonstrates local/demo wiring only and does not provision
the production foundation. Present it as illustrative, not as acceptance.

## Failure modes and acceptance evidence

| Failure mode | Prevented by | Acceptance evidence |
|---|---|---|
| Over-broad access | Per-workload least-privilege identities | Role assignments list shows no shared/broad identity |
| Secret leakage | Key Vault + managed identity | No secrets in images/Git; runtime reads from Key Vault |
| Config drift | IaC owns resources and Job/App definitions | Recreate environment from IaC; diff is empty |
| Unaudited manual runs | Scoped trigger role + `triggered_by` | Manual start shows caller identity in results DB |

## Open decisions

- **RBAC role-assignment permission — confirmed gap; grant requested.**
  The foundation's role assignments (`AcrPull`, `Storage Blob Data Contributor`,
  `Key Vault Secrets User`, the dashboard's Job-start role, etc.) require
  `Owner` or `User Access Administrator`; writing a role assignment
  (`Microsoft.Authorization/roleAssignments/write`) is **not** something
  `Contributor` can do. **Verified 2026-07-30:** the deploying user
  (objectId `<deployer-object-id>`) has only **`Contributor`** on the target
  subscription `<subscription-id>` (a Dev/Test subscription) — no
  `Owner`/`User Access Administrator` anywhere. Creating a personal RG does
  **not** close this (you inherit subscription-level `Contributor`).
  - **Decision:** keep the managed-identity RBAC model and **obtain the grant**
    rather than fork the code for key-based auth. A key-based demo shortcut was
    rejected because it would rewrite every data-client construction and make
    demo != prod (see [Infrastructure as code](#infrastructure-as-code)).
  - **Action:** ask a subscription owner for **`User Access Administrator`
    scoped to the target resource group** (RG-scoped, not subscription-wide).
    Ask an owner who also holds root-scope `User Access Administrator`.
    Microsoft Graph name resolution is blocked for the deploying user, so have
    them grant by **objectId** (`<deployer-object-id>`), not UPN. Once granted,
    the full `terraform apply` runs unchanged.
- Networking baseline — **resolved:** public endpoints + identity for the MVP,
  private endpoints deferred to prod hardening (see [Networking](#networking)).

## References

- Planes and identities rationale — [00](./00-production-architecture.md).
- How identities are used at runtime — [04](./04-periodic-and-batch-workflows.md),
  [05](./05-online-serving.md), [06](./06-release-and-operations.md).
