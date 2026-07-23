.PHONY: up down reset train worker beat producer demo
.PHONY: az-up az-down az-status az-login

SUFFIX ?= demo
LOCATION ?= southeastasia
RG = ml-platform-$(SUFFIX)

# ── Local dev ─────────────────────────────────────────────────────────────

up:
	docker compose up -d
	@echo "MLflow → http://localhost:5000"
	@echo "MinIO  → http://localhost:9001"

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up -d

train:
	uv run python -m ml_platform.train

worker:
	uv run celery -A ml_platform.tasks worker --loglevel=info --concurrency=2

beat:
	uv run celery -A ml_platform.tasks beat --loglevel=info

producer:
	uv run python -m ml_platform.producer

demo:
	@echo "=== Local Demo ==="
	@echo "1. make up       → start stack"
	@echo "2. make train    → train + register model"
	@echo "3. make worker   → start Celery worker"
	@echo "4. make beat     → start reconciliation producer"
	@echo "5. make producer → publish demo tasks"
	@echo "6. Check http://localhost:5000"
	@echo "7. make down     → stop stack"

# ── Azure ─────────────────────────────────────────────────────────────────

az-login:
	az login
	az account show --output table

az-up:
	@echo "Deploying to Azure: $(RG) in $(LOCATION)"
	az group create -n $(RG) -l $(LOCATION) --tags demo=true owner=$(SUFFIX)
	az deployment group create \
		-g $(RG) \
		-f infra/main.bicep \
		-p suffix=$(SUFFIX) \
		--output table
	@echo ""
	@echo "=== Deployed ==="
	@az deployment group show -g $(RG) -n main --query properties.outputs -o table
	@echo ""
	az deployment group show -g $(RG) -n main \
		--query "properties.outputs.mlflowUrl.value" -o tsv \
		| xargs -I {} echo "MLflow → {}"

az-down:
	az group delete -n $(RG) --yes --no-wait
	@echo "Tearing down $(RG) — this may take a minute."

az-status:
	az resource list -g $(RG) -o table
	@echo ""
	az monitor metrics list \
		--resource-group $(RG) \
		--resource-type Microsoft.App/containerApps \
		--metric Requests \
		--interval PT1H \
		-o table 2>/dev/null || true
