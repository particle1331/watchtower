Status: Draft
Owner: ML platform team
Canonical for: Online model and LLM HTTP serving
Depends on: [production architecture](./00-production-architecture.md), [platform foundation](./01-platform-foundation.md), [reproducible ML](./02-reproducible-ml.md), [GenAI release artifacts](./03-genai-release-artifacts.md)
Last reviewed: 2026-07-29

# 05 — Online serving

## Outcome

An authenticated client calls a stable HTTP API backed by a packaged model or
LLM runtime. The service starts only when the exact approved artifacts and
configuration have been validated, exposes honest readiness, enforces bounded
latency/concurrency/quota, and can be promoted or rolled back by an immutable
release descriptor plus hashed deployment intent/observation records.

## Production decisions

- **Default:** deploy a packaged model/LLM runtime as an **Azure Container Apps
  HTTP application**. The image is immutable and identified by an ACR digest.
  Conventional ML models include preprocessing and schema metadata; LLM
  runtimes include the exact prompt/model package and provider client. A GenAI
  artifact is an actual `mlflow.pyfunc.PythonModel`.
- **Default artifact loading:** ACA startup retrieves the exact artifact from
  the descriptor's approved, SAS-free Blob URI and required Blob version ID
  using managed identity. It verifies the descriptor-specified byte length
  and SHA-256 before readiness. **Blob digest/version is the canonical artifact
  identity** — no Azure ML model registry query is used at startup or runtime.
  Image bundling is not the default; it is allowed only as a documented approved
  exception and startup must still verify the bundled bytes against the
  descriptor's byte length and SHA-256.
- **ACA Apps are the only HTTP serving runtime.** Azure Functions (non-Durable)
  and Azure ML managed online endpoints are not serving alternatives. The
  non-Durable Function app in the current demo Bicep is local demo IaC only and
  will be replaced by the ACA App in production.
- **Bicep owns ACA App definition deployment.** Durable Functions workflows
  validate the deployment intent and observe the deployment outcome but never
  deploy or mutate ACA definitions.
- Runtime code never resolves a mutable `latest`, `champion`, or deployment
  alias per request. Promotion may use aliases to select a candidate, but the
  release descriptor records the resolved immutable artifact and release-level
  behavior configuration; the deployment intent records the environment provider
  configuration.

## Shared concepts

The online service and [durable workflows](./04-durable-workflows.md) share the
release descriptor's `release_id`, `contract_version`, exact artifact manifest
and provider-configuration references, correlation IDs, redaction, and the rule
that telemetry is not business state. An online `prediction_id`
is returned to the caller and links the request to traces and optional feedback.

The package boundary is the unit of deployment: application code, dependency
lock, preprocessing, model artifact, prompt/model package, release-level
behavior configuration, request/response schema, and startup checks are tested
together. Release preparation may choose a candidate alias, but serving receives
only its resolved immutable references.

## Target design/contracts

### Container and startup validation

Build a versioned image and include a machine-readable `runtime-manifest.json`
with at least `release_id`, `contract_version`, package build SHA, dependency
lock hash, and expected artifact/config identifiers. At startup the process
must fail closed, before advertising readiness, if any check fails:

The ACA workload identity receives `Storage Blob Data Reader` only at the
approved artifact Blob container/resource scope containing the descriptor's
versioned objects. The release descriptor contains no SAS, storage key, or
other secret, and its artifact URI is an approved Blob URL without credential
query parameters.

1. Read the release descriptor supplied as a mounted, immutable configuration
   object or environment reference. Verify its schema, release ID, and allowed
   environment.
2. Read each descriptor artifact's immutable Blob URI, version ID, byte length,
   and SHA-256. Use the ACA managed identity to retrieve that exact versioned
   Blob object, verify its byte length and SHA-256 before loading the declared
   `mlflow.pyfunc.PythonModel` signature. If the descriptor names the documented
   approved `image_bundle` exception, load the specified local bundle and
   perform the same byte-length/SHA-256 verification before loading.
   After deployment, no model-registry query or alias use is permitted.
3. Resolve the deployment intent's exact provider-configuration reference and
   hash; verify the nonsecret Azure OpenAI endpoint, deployment, quota profile,
   provider model/API behavior, safety settings, and token limits. A mutable
   provider deployment must have an approved immutable configuration record;
   credentials are obtained only through managed identity/Key Vault.
4. Verify required feature names/types, output schema, package/dependency
   compatibility, and supported `contract_version`. Run a deterministic
   canary prediction against a fixture and compare the expected shape and
   bounded values; do not log sensitive fixture content.
5. Confirm required Key Vault/managed-identity access and downstream endpoint
   connectivity without making an untracked production request. Expose
   `artifact_blob_sha256`, `model_manifest_digest`, provider-configuration hash,
   and `release_id` in readiness metadata.

Readiness is `503` until all checks pass. An artifact mismatch, missing secret,
unsupported contract, or failed canary causes a crash/restart and an alert; it
must not leave a process serving an unvalidated model.

### HTTP and authentication contract

| Endpoint | Contract |
|---|---|
| `GET /healthz` | Process-only liveness; `200` when the event loop is alive, no model call |
| `GET /readyz` | `200` only after startup validation; `503` with a safe reason otherwise |
| `POST /v1/predictions` | Authenticated JSON request; returns `prediction_id`, `release_id`, exact artifact/config versions, output, and timing metadata |
| `GET /v1/metadata` | Non-sensitive build, contract, and version information for diagnostics |

Use Microsoft Entra ID/OAuth2 app roles for service clients and least-privilege
managed identities for Azure callers. Reject unauthenticated prediction calls,
validate issuer/audience/scopes, and use HTTPS only. Accept a caller-supplied
`X-Correlation-ID` only after length/character validation; otherwise generate
one. For operations with external side effects, require an `Idempotency-Key`
and persist its result in the owning business system. Do not put tokens,
document text, or full prompts in logs.

Initial request schema for a conventional model:

```json
{
  "inputs": [{"feature_a": 0.2, "feature_b": 1.1, "feature_c": 0.7}],
  "contract_version": 1
}
```

The response must be schema-versioned and reject unknown/incompatible feature
shapes with `400`. Use `401/403` for auth, `409` for an idempotency conflict,
`429` for admission or provider quota, `503` for not-ready/dependency outage,
and `504` only when the bounded service deadline is exceeded. LLM request and
response schemas are separate contracts and must enforce input/token limits.

### Timeout, concurrency, and throttling

Start with these explicit defaults and change them only through a tested release
descriptor:

- 30-second HTTP deadline, 3-second connect timeout, and 25-second downstream
  deadline for an ordinary prediction;
- no unbounded retry; at most one retry for a transient connection failure or
  provider 429 when `Retry-After` fits inside the remaining deadline;
- `CONCURRENCY=4` per Container Apps replica for the conventional CPU package,
  lowered if load tests show contention; LLM concurrency is the quota-derived
  value from [durable workflows](./04-durable-workflows.md), with a separate
  admission limiter for interactive traffic;
- bounded request body, feature count, prompt tokens, completion tokens, and
  in-flight requests; return `429` with `Retry-After` instead of queueing
  unbounded work in process;
- autoscale on HTTP concurrency/requests and keep a quota-derived maximum
  replica count. Scale-to-zero is allowed only if the cold-start budget is
  accepted by the caller; otherwise set a minimum replica explicitly.

For LLM calls, calculate the shared limit from approved requests/minute,
tokens/minute, p95 latency, expected tokens/request, and the safety factor in
[durable workflows](./04-durable-workflows.md). Online and batch budgets must be
partitioned so a batch surge cannot starve the interactive API.

## Runnable demonstration

The current repository can demonstrate the packaged training artifact, but it
does not yet contain an online HTTP handler:

```text
make up
make train       # synthetic data, Pandera validation, MLflow model registration
```

The existing `infra/main.bicep` includes a non-Durable Functions hosting
baseline, not a finished serving implementation. A production-ready
demonstration will add a local Container Apps-compatible HTTP image and run:

```text
docker build -t ml-platform-api:<git-sha> .
docker run --rm -p 8080:8080 \
  -e RELEASE_DESCRIPTOR=/run/secrets/release-descriptor.json \
  ml-platform-api:<git-sha>
curl -f http://localhost:8080/healthz
curl -f http://localhost:8080/readyz
curl -X POST http://localhost:8080/v1/predictions \
  -H 'Authorization: Bearer <test-token>' -H 'Content-Type: application/json' \
  -d '{"inputs":[{"feature_a":0.2,"feature_b":1.1,"feature_c":0.7}],"contract_version":1}'
```

The latter commands are an implementation acceptance target, not a claim that
the image or handler currently exists. The current Bicep baseline does not
prove that a runnable Azure runtime exists; deployment and integration evidence
are required.

## Production implementation

1. Define the request/response, feature, LLM, error, auth-scope, and telemetry
   contracts. Add redacted fixtures and an exact artifact/config release
   descriptor.
2. Build the HTTP application with startup validation, readiness/liveness,
   bounded clients, structured correlation telemetry, and graceful shutdown.
3. Implement the default authenticated download of the exact artifact from its
   immutable Blob URI with version ID, byte-length, and SHA-256 verification,
   plus a local cache. Permit image bundling only through the approved
   exception.
4. Provision Container Apps App, ingress, managed identity, Key Vault references,
   ACR digest deployment, autoscaling, network restrictions, and Application
   Insights.
5. Add contract, unit, integration, load, quota, auth, startup-failure, and
   rollback tests. Promote through the [release workflow](./06-release-and-operations.md)
   using exact versions.

## Failure modes/acceptance evidence

| Test | Acceptance evidence |
|---|---|
| Wrong artifact/config/hash in descriptor | Startup fails, `/readyz` stays `503`, no prediction is served |
| Blob URI or version changes after deployment | Running process continues to report and use the descriptor's exact artifact and content hash |
| Missing/expired identity or secret | Safe startup failure and actionable alert; no secret in response/logs |
| Invalid auth, schema, size, or contract | Correct `401/403/400/413` response; downstream model is not called |
| Provider timeout/429 | Deadline is honoured, retries are bounded, `429/504` is classified, no request storm |
| Burst above configured concurrency | `429` admission control is stable; p95 latency and error SLO remain within budget |
| Replica replacement during traffic | Requests finish or return a retryable error; no silent response loss |
| Cold start and scale-out | Readiness gates traffic; measured cold-start and p95 meet the approved budget |
| Production rollback | Previous compatible image and exact artifacts serve successfully; version telemetry changes as expected |
| Canary correctness | Fixture output/schema and model signature match the recorded evaluation evidence |

Minimum load evidence is a 15-minute representative request mix at 2x expected
peak, with p95 under the approved deadline budget, zero unauthorized successes,
no unbounded memory growth, and provider throttling below the agreed threshold.

## Open decisions

- What is the first API's latency/cold-start SLO, input sensitivity class, and
  required minimum replica count?
- Which image-bundled asset exception, if any, is approved, and where are the
  resolved immutable artifact Blob URI and content hashes recorded?
- Which Azure OpenAI deployments and quota partitions are reserved for online
  traffic, and what is the interactive fallback when quota is exhausted?

## References

- [Durable workflows](./04-durable-workflows.md)
- [Release and operations](./06-release-and-operations.md)
- [Delivery journey](./07-delivery-journey.md)
- [Production architecture](./00-production-architecture.md)
- [Reproducible ML](./02-reproducible-ml.md)
