# 5. Prototype operations and deferred adoption notes

[Plan index](README.md)

**Active scope:** operate, back up, restore and evaluate isolated prototype
resources. **Deferred reference:** the adoption/cutover/rollback sections below
apply only if you later choose to adopt v2. They are not implementation stages
or authorization to move live data, disable `wt`, redirect current agents, or
change the live site. Whether to migrate remains undecided.

Import/export/GC commands described here need implementation and help text;
they are not commands available in the current CLI.

Website publishing has a separate [deployment plan](website-deployment.md): CI
generates frontend notebooks from a frozen release, renders them, and deploys
HTML/assets. Prototype this in an isolated target. A future switch of the live
site from `gh-pages` commits to Pages artifacts would require its own adoption
decision and reviewed workflow/settings changes.

## Deferred: adoption invariants

- Preserve stable IDs, permanent task numbers, retired reservations, public routes,
  dates, order, relations, notes/checklists, ownership filenames, and lifecycle.
- Preserve exact notebook/sidecar/project bytes. Do not Start, reseed, execute,
  publish, or rewrite content as a side effect of import.
- Import exact verified payloads, including currently untracked managed files.
  A clean Git checkout is not the complete current workspace.
- Preserve unknown/legacy data with provenance; report fields requiring a decision.
  Malformed YAML or duplicate keys require explicit repair, not silent overwrite.
- Only one backend accepts authoritative writes at a time. No indefinite
  dual-write period between YAML and Turso.
- Replace the former manual `archive/deleted/` pruning workflow with managed
  retention/purge. Until a supported archive-purge operation exists, retain legacy
  archives. Migration inventories/classifies them before any policy removes bytes.

## Deferred: possible rehearsal and cutover sequence

### 1. Capture and resolve the source inventory

Stop pending recovery conflicts before making a migration baseline. Record the
workspace revision and checksums for managed records, active source files,
managed images/attachments, and referenced archived code. Include ownership and
missing/untracked-file reports; reconcile every referenced payload before import.
Classify historical archives separately from active dependencies and disposable
deleted history.

Back up the working filesystem, not only Git HEAD. Capture a read-only original
record export, exact source bytes, and a manifest of all payload hashes. Verify
that the backup can be read before proceeding. No history rewrite belongs in
this step.

### 2. Import into isolated resources

Use an empty disposable database and B2 namespace. Give the run a migration ID
and durable checkpoints so replay can resume without duplicating entities or
objects. Verify every upload version's length and SHA-256 before attaching it.
Keep a mapping from former file path to logical object and exact physical version.

Import all current record families, counters, reservations and relationship order.
Retain original metadata preimages outside ordinary Git state for the declared
migration-retention period. Inventory archives rather than blindly importing
every historical file as an active object.

### 3. Compare behavior without switching writers

Run v1 reads and v2 reads against their captured equivalents. Compare normalized
contexts, plans/consumption state, notes/to-dos, cards/refs, attachment owners,
course ordering, collection rows, dependency validation, and source hashes.
Verify full counts plus exact per-ID comparisons; counts alone can hide swaps.

Build preview and production from equivalent frozen inputs. Compare routes,
navigation, visible text, asset digests, publication filtering, and absence of
private/internal data. HTML byte equality may be inappropriate where generated
timestamps differ; report the specific normalization used and keep substantive
differences visible. Exercise CLI/API/Flet parity separately, translating the v1
HTML mechanisms according to the [explicit interface adjustment](cli-v2-and-flet.md#explicit-parity-adjustment).
Include keyboard/focus, unsaved editors, upload recovery, navigation, and native
desktop checks only if native packaging is part of the selected delivery.

V1 remains the sole writer while comparisons run. Shadow reads must not seed
notebooks or trigger migration writes. Rehearse interrupted imports and the full
restore/rollback procedures before live resources are involved.

### 4. Review the concrete cutover packet

Provide the inventory and unresolved-item count, import/parity results, exact
provider/engine/driver versions, configured retention, backup/restore evidence,
credentials/permissions summary without secrets, CI release behavior, local GC
triggers/catch-up behavior, and rollback steps. Required unresolved items must reach zero or have
an explicit accepted resolution.

### 5. Freeze and switch

Pause CMS/CLI writes, notebook execution, affected IDE saves, workers, and GC.
Capture a final v1 revision and delta, import it, and rerun the critical checks.
Bind the authoring checkout to v2, start one authoritative writer, and exercise
read/save/conflict/upload/build paths. Keep v1 metadata as a read-only recovery
export outside active authoring inputs. Remove obsolete tracked managed data
only after v2 source ownership and CI inputs have been proven.

Use `wt2` for the v2 workspace and move instructions/scripts to it explicitly.
The separate `wt` executable does not by itself prevent split writes: block v1
mutations/services against the migrated authoring workspace and keep any fallback
v1 data read-only until a deliberate rollback.

Changing the working tree prevents new accumulation; old committed payloads
remain in Git history. Rewriting that history is a separate, explicitly reviewed
operation after successful migration, with its own clone/branch coordination.

## Deferred: adoption rollback boundaries

**Before v2 accepts new writes:** switch back to the preserved v1 workspace after
checking source files still match the baseline.

**After v2 accepts new writes:** a simple restore of old YAML loses those writes.
Freeze v2, export its *current* records to the supported v1 representation,
rehydrate required managed bytes, reconcile notebook/source changes, and validate
and build that candidate before switching. Rehearse this compatibility export
while the fallback promise is offered. If new data cannot be represented safely,
choose a forward fix or a reviewed repair instead of claiming instant rollback.

Retire the v1 fallback only after parity and restore evidence are accepted.
Retaining old snapshots indefinitely is not a substitute for a current backup.

## Backup and restore

The following backup/restore design is active prototype work. Demonstrate it
using isolated records, object versions and content copies; it does not establish
a new recovery promise for the existing system.

Decide the accepted-edit undo contract before finalizing the schema. A concise
audit log is not full revision history, and restoring a whole database backup is
not a convenient per-entity Undo action. If bounded metadata edit history is
required, specify its limits and protect any object versions it promises to
restore. This is distinct from the already planned deleted-record undo period.

Database recovery and file recovery form one promise. Git preserves authored
source only when committed; it does not protect unsaved/uncommitted notebooks,
the live Turso database, or all B2 versions.

1. Create a consistent database snapshot/export using the selected provider's
   verified mechanism. Coordinate backup construction with GC so required versions
   are protected before the backup becomes eligible for use.
2. Store an immutable backup manifest containing snapshot identity/schema,
   workspace/source identity, and exact object keys/versions/digests required by
   that snapshot. Keep the protection inventory outside the database being
   restored. It must survive restoring that database to an earlier state.
3. Back up uncommitted authored source separately where recovery of local work is
   promised. Decide and document its schedule, encryption/access, and retention.
4. Verify access to every required payload. Record the backup as complete only
   when the snapshot and its object protection are durable.
5. Expire the backup and its pins according to policy. If provider PITR promises
   an additional window, retain enough object history to cover it too.

For restore: enter maintenance mode; stop and drain GC/workers; select a supported
backup/point; restore into an isolated environment first; check schema, all record
relationships, every required object digest, and source compatibility; build the
site; replace worker generations; reconcile storage; then resume writes and GC.
Prevent pre-restore workers from finalizing work against restored records.
Restore validation must never make a missing object disappear by deleting its
metadata. If a required version is absent, recover it from backup or fail the drill.

Start with a 30-day application backup policy. Establish and record actual recovery
point and recovery time objectives after the provider spike and a measured drill;
do not infer them from “hosted database.” Backups can share B2 as a provider but
need separated permissions and protection against ordinary application deletion.

## Day-to-day operation

| Situation | Expected behavior / operator action |
| --- | --- |
| Turso unavailable or save outcome unknown | Show failure/pending operation ID. Query receipt after reconnecting; do not retry a stale edit as new work. |
| B2 unavailable | Existing local preview may remain usable. New uploads/build hydration fail visibly; do not finalize missing bytes. |
| Pending source operation or divergent IDE file | Preserve source/preimage/proposed bytes and show their locations. Resolve explicitly before affected writes. |
| Missing live object | Flag integrity failure, identify owners/releases/backups, restore exact bytes. Pause unsafe collection. |
| Storage pressure | Show classified bytes and overdue cleanup. Evict unleased cache and eligible garbage; block new allocations before endangering live data. |
| Failed render | Keep current site and fallback, expose log/operation ID, retry after correcting inputs. |
| Stuck worker | Inspect lease/generation and operation evidence; reconcile before reclaiming work. Never infer safety solely from wall-clock age. |
| New schema version | Back up, apply ordered migration, verify compatible application versions, exercise restore. |

Provide documented commands for integrity audit, operation status/recovery,
storage accounting, GC dry-run/apply, backup verification, release inspection,
and configuration diagnostics. Each diagnostic must identify the environment and
workspace and redact credentials. Update README and agent instructions when
those commands actually exist.

GC runs during active local CLI/CMS use; no worker must stay online while the
laptop is closed. Verify startup/resume reconciliation and bounded cleanup of
objects whose retention expired during inactivity. Keep policy versions, logs,
credentials and failure handling in the maintained backend. Backup timing and
restore guarantees remain a separate decision; removing an always-on GC requirement
does not define the backup contract.

## Handover checklist

You should be able to answer and demonstrate:

- Which rows and files does each common action change?
- What does a stale save look like, and how do you recover submitted work?
- Which exact B2 version serves a file, and what protects it from deletion?
- How do you inspect and resolve a half-finished operation?
- Which inputs reproduce a production release without querying live CMS state?
- What data could be lost after a failure today, given the measured backup schedule?
- How do you prove storage growth is active content/intentional retention rather
  than abandoned work?

Keep these answers as short runbooks with actual source and command links as
implementation proceeds. The final system is incomplete if only its implementer
can operate it.
