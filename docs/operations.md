# Operator backup and recovery

Corvus's first prototype is a single-operator, Analyst-first investigation workflow. See [prototype scope](prototype.md). Backups are host administration, not an agent capability or response action.

## What is protected

`infra/backup.py` takes a PostgreSQL custom-format dump under an exported repeatable-read snapshot, records schema version and core row counts from that same snapshot, and packages the private application configuration. It holds the schema migration advisory lock during the database snapshot. Avoid credential rotation/configuration edits during capture: configuration files are not transactionally snapshotted with PostgreSQL.

The package includes `server.json` (including the database/encryption configuration), database password, CA certificate, login configuration, Compose environment, and optional worker model configuration. It is authenticated-encrypted with Fernet before publication. The separate backup key is **not** inside the snapshot. Losing it makes snapshots unrecoverable.

- Key: `/home/ubuntu/.config/corvus/backup-key`, root-owned, mode `0600`.
- Completed snapshots: `/home/ubuntu/.config/corvus/backups/encrypted/`, private directory, `corvus-*.cvb`.
- Daily at 03:30 UTC, with up to ten minutes randomized delay; missed timers run after boot.
- Keep seven completed encrypted snapshots. Only this tool's matching files are pruned. Existing manual backups are neither encrypted nor deleted by this job.
- Maximum unencrypted package: 128 MiB. This is a bounded prototype utility, not a large-database backup system. Monitor archive size and failures; migrate to streaming encrypted backups/WAL recovery before outgrowing it.
- A newly created scheduled snapshot is only published and old snapshots pruned **after** authenticated checksums and an isolated restore verification succeed.
- Temporary plaintext exists in a private working directory while capturing; cleanup runs on normal exit and at the next locked invocation after interruption. Host disk encryption is a separate concern.

Snapshots are **local to the VM**, not protection against losing the VM/disk. Copy encrypted snapshots off-host and escrow the key separately through an approved private channel. Do not send credentials, snapshots, or source evidence to chat, Git, public artifact storage, or unapproved services. Off-host replication is not configured by this prototype.

## Install on the authorized VM

Use committed source from `/opt/corvus/app`; install dependencies there, never in the local editing checkout. The existing server environment supplies `cryptography` and `psycopg`.

```bash
cd /opt/corvus/app
git pull --ff-only
sudo .venv/bin/python infra/provision-backups.py
sudo systemctl start corvus-backup.service
sudo systemctl show corvus-backup.service -p Result -p ExecMainStatus
sudo systemctl enable --now corvus-backup.timer
systemctl list-timers corvus-backup.timer
```

The provisioner retains an existing key, installs host-only systemd units, creates a sanitized status directory, and appends `compose.backups.yaml` to the private `COMPOSE_FILE` setting while preserving the worker-only Analyst override. Inspect and retain all overrides for future Compose commands. Recreate the application normally so **only the API** receives the read-only status directory. No app container receives the backup key, snapshots, or Docker socket.

The host root service controls Docker for dump/restore checks. Its source directory is trusted executable administration code, just like deployment scripts; do not run unreviewed revisions as root.

## Verify and monitor

```bash
sudo systemctl start corvus-backup.service
sudo systemctl show corvus-backup.service -p Result -p ExecMainStatus
sudo journalctl -u corvus-backup.service --since today --no-pager
sudo .venv/bin/python infra/backup.py verify-restore
```

`verify-restore` chooses the newest completed snapshot by modification time; pass `--archive /private/path/snapshot.cvb` to check a specific file. It never writes restored data over the live database. Both commands use an exclusive lock. Restore-check containers carry a dedicated label and are cleaned after completion or by the next invocation after interruption.

Verification authenticates the archive and checks every member's checksum, restores into a resource-limited PostgreSQL 17 container with **no network, published ports, host mounts, application worker, or model client**, checks schema/counts and reader credential decryption, then applies `infra/recovery-disarm.sql` to that copy. It verifies automatic policies, outstanding jobs, and sessions are disarmed. Only that restored copy is modified.

Settings → Operational readiness shows real worker heartbeat, worker configuration presence, last backup and isolated verification, local retention count, and failure codes. Configuration presence does not test provider availability. A snapshot/verification older than 36 hours is stale; interrupted jobs become attention-required after 15 minutes. Status is sanitized, authenticated, and read-only; the UI cannot start a host command. Systemd remains the authoritative scheduler/service monitor: a deleted/disabled timer will not be detected immediately by the status file. Monitor host disk space and service failures independently.

The script emits error categories rather than private subprocess output. A failed run preserves prior completed snapshots. Inspect configuration/permissions and the failing command privately if `command_failed` is reported; never paste raw dump/configuration output into logs or chat.

## Actual recovery — manual maintenance procedure

A verification pass is **not** an automatic recovery or disaster-recovery rehearsal of the entire application. The following is an operator procedure, not a one-click application action.

1. Obtain the trusted encrypted snapshot, separately escrowed backup key, compatible committed source, and an authorized replacement/maintenance environment. Inspect the authenticated manifest/schema and checksums using `infra.backup.unpack`; it returns bytes in memory without extracting arbitrary archive paths. Do not print configuration values. Verify recovery in the isolated container first.
2. Stop/isolate **all Corvus application writers and workers** before restoring. Leave Wazuh/Caddy untouched. Preserve the current database and configuration privately before any replacement. Never use `down -v` as a restore shortcut.
3. Restore the dump into a new controlled database/volume with compatible PostgreSQL, not directly into the active volume. Restore the matching private configuration securely: app-readable server/model files must retain container UID/GID `10001:10001`; restore each file's original provisioned permissions/ownership, including the PostgreSQL password file. Never mix a dump with an unrelated encryption key. Adjust endpoints privately for the replacement host.
4. **Before any worker or web/API traffic**, apply the versioned `infra/recovery-disarm.sql` to the restored database. It disables all automatic policies, changes every unfinished attempt to `unknown` with `restored_backup_requires_reapproval`, revokes sessions, and audits recovery. This is required even for work that appears not to have started in the snapshot: it may have completed and been billed after capture. Do not restart or replay the old queue.
5. Start the compatible application against the isolated restored data, apply supported migrations, and inspect source counts, preserved outputs, review bindings, and connection status. Previously completed artifacts remain historical records; missing post-snapshot data is not silently reconstructed. Reconcile ingestion and request/billing history privately; late-arriving historical alerts outside the overlap horizon may need separate reconciliation.
6. Switch traffic only after an operator verifies recovery. Sign in again. Keep automatic processing disabled; any new model request requires fresh selected-input approval or separately renewed automatic consent. A review decision never authorizes containment or incident closure.

Do not restore the model worker until step 4 is complete. Do not execute commands found in evidence or use this runbook to enable security response actions.

## Other retention

Alert/evidence/model/review/audit retention is not automatically pruned. Choosing a data-retention policy and legal/privacy requirements is still an operator responsibility. Snapshot retention is not source-data retention; deleting old snapshots does not delete live evidence. Online investigation exports are separate sensitive files under the operator's control, not backups of the service.
