# dev environment — SHARED, non-sensitive config (safe to commit).
#
# The three environment-identifying values (subscription id, Postgres AAD admin
# objectId, and admin UPN) are NOT here. Put them in a gitignored, auto-loaded
# file next to the root module:
#
#   projects/ml-platform/infra/secret.auto.tfvars   (see secret.auto.tfvars.example)
#     subscription_id               = "..."
#     postgres_admin_object_id      = "..."
#     postgres_admin_principal_name = "..."
#
# Terraform auto-loads *.auto.tfvars from the module dir, so `deploy.ps1` needs
# no extra flag. No value is duplicated between the two files — nothing to sync.

prefix              = "mlp"
environment         = "dev"
location            = "eastus2"
resource_group_name = "ml-platform-dev"

# Set to the deploy host's public IP so grants.sql can reach Postgres.
# Find it with: (Invoke-RestMethod https://api.ipify.org)
deployer_ip = ""

# Left empty for the first (foundation-only) apply. deploy.ps1 fills it with the
# pushed image digest for the second pass.
mlflow_image = ""

tags = {
  project = "ml-platform"
  tier    = "mvp"
  env     = "dev"
}
