# Authoring workspace

Edit notebooks and their supporting sidecars here in VS Code or Jupyter.
Notebook bodies, stored outputs, inline attachments and cell options belong to
the authored source. Site metadata, uploaded assets and navigation are managed
under `backend/` and generated into separate build copies.

Use `.venv/bin/wt` from the repository root to create/register notebooks and
change publication metadata. Retire an active entry with `wt delete` so its links
and registrations are cleaned up together. Agents use the supported notebook
commands for cell edits.

Validation and rendering happen before a new build replaces the last successful
preview or site. A failed authoring edit leaves that successful output available.
Local saves do not deploy the live site.

Deleted content under `archive/deleted/` is safe to prune manually in VS Code or
bash. Active content and builds do not depend on those archives.

See the [repository philosophy](../README.md#repository-philosophy) for details.
