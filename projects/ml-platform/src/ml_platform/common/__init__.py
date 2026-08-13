"""Shared platform helpers used by every job/app image.

These modules are the small, stable seam the course builds on: MLflow client
configuration, MLflow-tracked datasets, boundary schema validation, and the
generic results-DB run record. Job images (`train_job`, `batch_job`) and the
serving app import from here so lineage, validation, and operational recording
are identical across workloads (docs/02, docs/04).
"""
