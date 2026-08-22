#!/bin/sh
set -eu

until mc alias set local http://minio:9000 minio minio-password; do
  sleep 1
done
mc mb --ignore-existing local/mlflow
