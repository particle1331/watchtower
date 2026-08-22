# Local ML platform POC

This Compose stack is a local stand-in for the deployed platform. It keeps the
same planes and job images while replacing Azure-only infrastructure:

| Production | Local POC |
|---|---|
| Azure Database for PostgreSQL | Postgres container (`mlflow` and `results` databases) |
| Blob Storage | MinIO S3-compatible object storage |
| MLflow ACA App | MLflow container |
| ACA train/batch Jobs | One-shot Compose services plus the local runner |
| Serving ACA App | FastAPI serving container |
| Dashboard ACA App | FastAPI dashboard with local trigger buttons |

## Run the demo

From this directory:

```bash
docker compose up --build
```

On a clean volume, startup trains and registers `wine-quality` version 1,
runs a batch scoring job, and starts the serving and dashboard apps. The data is
the public MLflow wine-quality CSV, so the first run needs internet access.

Open:

- Dashboard: <http://localhost:18000>
- Serving readiness: <http://localhost:18080/readyz>
- Serving prediction: `POST http://localhost:18080/v1/predictions`
- MLflow: <http://localhost:15000>
- MinIO console: <http://localhost:19001> (`minio` / `minio-password`)

Example prediction:

```bash
curl -X POST http://localhost:18080/v1/predictions \
  -H 'content-type: application/json' \
  -d '{"instances":[[7.0,0.27,0.36,20.7,0.045,45.0,170.0,1.001,3.0,0.45,8.8]]}'
```

The dashboard's **Run training** and **Run batch scoring** buttons use a small
local execution-plane service. It is deliberately not a Docker-socket or Azure
API integration. It executes the same job entrypoints and records the same
results rows, which keeps this POC safe to run on a laptop while preserving the
production interaction shape.

The same controls are available as a parameterized API. Submit command-line
parameters under `parameters`; values are validated and forwarded to the real
job entrypoint:

```bash
# See job names, accepted parameters, and ready-to-copy examples.
curl http://localhost:18000/api/jobs
```

The `job_name` is the path segment after `/api/runs/trigger`: use `train` for
training or `batch` for batch scoring. For example:

```bash
# Train and register a new model version.
curl -X POST http://localhost:18000/api/runs/train/trigger \
  -H 'content-type: application/json' \
  -H 'X-MS-CLIENT-PRINCIPAL-NAME: demo-user' \
  -d '{"parameters":{"alpha":0.25,"l1_ratio":0.8,"random_state":7}}'
```

Batch scoring supports parameters such as `model_version`, `chunk_size`, and
`max_attempts`:

```bash
# Score the CSV with registered model wine-quality version 1.
curl -X POST http://localhost:18000/api/runs/batch/trigger \
  -H 'content-type: application/json' \
   -d '{"parameters":{"model_version":"1","chunk_size":500}}'
```

The trigger response returns an execution id immediately because jobs run in
the background. In the local POC, `result_id` is intentionally the same value
as `execution`, so poll the returned `result_url` until `result` is complete:

```bash
curl http://localhost:18000/api/results/<execution>

# Or inspect runner status and the result together:
curl http://localhost:18000/api/executions/<execution>
```

Use `GET http://localhost:18000/api/runs` to inspect the resulting operational
records. The results API is also grouped as **Results** in the FastAPI docs at
<http://localhost:18000/docs>:

```bash
# Recent results
curl 'http://localhost:18000/api/results?limit=20'

# Only failed results
curl 'http://localhost:18000/api/results?status=FAILURE'

# One result by id
curl http://localhost:18000/api/results/<result-id>
```

The local POC supports parameterized triggers; the ACA backend rejects them
until production job argument overrides are wired in.

To reset the demo and get model version 1 again:

```bash
docker compose down -v
docker compose up --build
```

The Compose services are intentionally a demonstration environment, not a
production security boundary. The credentials in the file are local demo
credentials only.

If those host ports are occupied, override them when starting the stack, for
example `DEMO_DASHBOARD_PORT=8000 docker compose up --build`.
