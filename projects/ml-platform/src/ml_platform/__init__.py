"""ml_platform — MVP MLOps platform package.

The ML platform is built up chapter by chapter in the `mlops` course
(`courses/mlops/`). The course is documentation; the runnable source lives here,
independent of the notebooks, and the notebooks reference these modules and
scripts when they demo each stage.

Package layout as the course builds it (see `docs/` for the production contract):

    src/ml_platform/
        common/      # results-DB client, MLflow helpers, hashing, schemas
        results/     # generic results DB: schema + parent/child batch model
        llm/         # pyfunc artifact builder + evaluator (Phase 5)
    src/train_job/   # ACA Job image: training + evaluation entrypoints
    src/batch_job/   # ACA Job image: scheduled / batch inference entrypoints
    src/serving_app/ # ACA App image: online HTTP serving at an exact version
    src/mlflow_app/  # self-hosted MLflow container (Phase 0)
    src/dashboard/   # catalog + launcher ACA App (Phase 4)
    src/train_aml/   # Azure ML command-job entrypoint (multi-GPU exception)
    infra/           # IaC for the whole footprint
    deploy/          # provisioning + smoke-test scripts
"""

__version__ = "0.1.0"
