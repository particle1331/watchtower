# Managed storage

Use the CMS, `.venv/bin/wt` CLI or API to change these files:

- `data/`: catalog, plans, course outlines, profile, gallery, portfolio and Kanban.
- `assets/`: managed image uploads and CMS illustrations.
- `attachments/`: context files with artifact/card ownership in managed data.
- `runtime/`: ignored locks, recovery journals and build records.

Direct edits are for deliberate repairs. Managed operations carry revisions,
validate related records and save them together. Do not move or remove active
assets or attachments manually; their ownership and references are managed by
the services.

Author notebooks and sidecars in `content/`. Deleted history under
`archive/deleted/` can be removed manually without breaking active state or builds.

See the [repository philosophy](../README.md#repository-philosophy) for details.
