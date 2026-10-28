# Searchable Telemetry Archives

Status: enabled and checked on the Wazuh lab. This documents the current implementation, not a production retention policy.

## Goal and Data Flow

Corvus needs events that did not generate alerts, not just the SIEM's detection output.

```text
Windows event channels -> Wazuh agent -> Wazuh manager
                                              |
                          +-------------------+-------------------+
                          |                                       |
                     alerts.json                            archives.json
                          |                                       |
                       Filebeat                                Filebeat
                          |                                       |
                   wazuh-alerts-*                         wazuh-archives-*
                                                                  |
                                                      Discover / future Corvus tools
```

Archives contain events received and processed by Wazuh, including alerting and non-alerting events. They are not a copy of every native Windows EVTX record. Events excluded by Sysmon, agent queries, or collection gaps cannot be recovered here. Enabling this pipeline does not retroactively collect historical events that were never forwarded or retained.

## 1. Enable JSON Archiving on the Manager

Persistent source configuration on the host:

```text
/opt/wazuh-docker/single-node/config/wazuh_cluster/wazuh_manager.conf
```

Change:

```xml
<logall>no</logall>
<logall_json>yes</logall_json>
```

Plaintext all-event logging remains disabled to avoid an unnecessary additional representation. Existing alert logging stays enabled.

The Docker deployment stages this source configuration into the manager's `/var/ossec/etc/ossec.conf` at startup. The active JSON archive is `/var/ossec/logs/archives/archives.json`, stored in the existing `single-node_wazuh_logs` volume.

## 2. Enable Filebeat Archive Forwarding Persistently

Desired Filebeat module settings:

```yaml
filebeat.modules:
  - module: wazuh
    alerts:
      enabled: true
    archives:
      enabled: true
```

Wazuh Docker modifies Filebeat configuration during startup. Rather than bind-mounting its live file or making an undocumented one-off edit, the deployment mounts a small startup hook:

```yaml
- ./entrypoint-scripts/10-enable-archives.sh:/entrypoint-scripts/10-enable-archives.sh:ro
```

The official manager image runs `/entrypoint-scripts/*.sh` after its normal Filebeat initialization and before starting Wazuh. The hook enables exactly one archive setting, refuses to guess if the format changes, and runs `filebeat test config`.

Repository source: [`infra/wazuh/entrypoint/10-enable-archives.sh`](../infra/wazuh/entrypoint/10-enable-archives.sh).

The existing Wazuh index template already matches `wazuh-archives-4.x-*`; no replacement mappings were needed. Existing Filebeat TLS verification remains enabled.

Apply deployment configuration changes from the VM:

```bash
cd /opt/wazuh-docker/single-node
docker compose config --quiet
docker compose up -d --no-deps --force-recreate wazuh.manager
```

This briefly interrupts the manager; agents reconnect automatically. Do not use `down -v`.

## 3. Retain Archive Indices for Approximately Three Days

An OpenSearch Index State Management policy named `corvus-archives-retention` is installed with:

- Automatic attachment to new `wazuh-archives-*` indices.
- An initial `retain` state.
- A transition to deletion after `min_index_age: 3d`.
- No matching of `wazuh-alerts-*` or other data indices.

Policy source: [`infra/wazuh/archive-retention-policy.json`](../infra/wazuh/archive-retention-policy.json).

This is **index-age retention**, not an exact per-event 72-hour TTL. Daily index boundaries, first creation time, late events, and ISM scheduling affect the actual event window. Deletion after three days has not yet been observed over a full retention cycle; policy attachment and its enabled state were verified.

The installation helper creates the policy before archive indexing begins. It does not overwrite an existing policy or automatically retrofit arbitrary pre-existing indices.

Installed helper:

```bash
sudo python3 /opt/corvus/bin/configure-archive-index.py policy
sudo python3 /opt/corvus/bin/configure-archive-index.py verify
```

Repository source: [`infra/wazuh/configure-archive-index.py`](../infra/wazuh/configure-archive-index.py). It reads credentials from the existing protected host file, not from command-line arguments.

## 4. Retain Closed Manager Archive Files Separately

Deleting an index does not delete the manager's archive files. An hourly systemd timer handles those independently:

```text
corvus-archive-retention.timer
    -> corvus-archive-retention.service
    -> /opt/corvus/bin/prune-wazuh-archives.py --apply
```

The cleanup helper:

- Resolves only the fixed lab Docker volume `single-node_wazuh_logs`.
- Restricts discovery to recognized dated files under its `archives/YYYY/Mon/` directories.
- Selects closed files older than 72 hours by modification time.
- Excludes current-date files, active archive files by inode, symlinks, and unexpected filenames.
- Never traverses the sibling alert-log directory.
- Defaults to dry-run unless `--apply` is supplied.
- Logs a warning when filesystem utilization is at least 80%; it does not send external notifications.

The timer runs hourly with up to five minutes of randomized delay and is persistent across downtime. This is retention, not a hard byte quota. Active files, rapid event growth, failed cleanup, or delayed shipping can still require operator intervention. Files removed after the retention window are not preserved indefinitely for a failed shipper.

Commands:

```bash
# Preview eligible files without deleting them.
sudo python3 /opt/corvus/bin/prune-wazuh-archives.py

# Inspect scheduling and previous runs.
systemctl list-timers corvus-archive-retention.timer
sudo journalctl -u corvus-archive-retention.service -n 20 --no-pager
```

Sources:

- [`infra/wazuh/prune-archives.py`](../infra/wazuh/prune-archives.py)
- [`infra/wazuh/systemd/`](../infra/wazuh/systemd/)
- [`tests/test_archive_retention.py`](../tests/test_archive_retention.py)

## 5. Make Archives Available in Discover

An index pattern was created in the dashboard's default context through the saved-object API:

```text
ID: corvus-wazuh-archives
Pattern: wazuh-archives-*
Time field: timestamp
```

To recreate it if absent:

```bash
sudo python3 /opt/corvus/bin/configure-archive-index.py dashboard
```

Dashboard multitenancy is disabled in this deployment. The helper deliberately omits the `securitytenant` header and does not replace the default alert index pattern. It checks the saved-object listing, not just a direct object GET, to verify UI visibility.

An initial explicit tenant header put the archive pattern outside the normal UI context. This was corrected by creating the pattern without that header and verifying it appears alongside `wazuh-alerts-*` in the listing. The erroneous saved-object copy was removed without deleting event data.

In the browser, open **Discover**, select `wazuh-archives-*`, and choose a recent time range. If the page was already open, refresh it to reload available patterns. Filter by:

```text
agent.name:"windy"
```

All-event evidence is intended for Discover and future investigation tools; the Wazuh alert views remain focused on alerts.

## Verification Completed

- Filebeat configuration test: `Config OK`.
- Filebeat output test: connection and TLS certificate-chain verification succeeded.
- Archive index created: `wazuh-archives-4.x-2026.10.28`.
- Archive index health: green.
- Archive index pattern appears in the same dashboard listing as the normal alert pattern.
- Three-day retention policy attached and enabled for the archive index.
- Windows events from `windy` were indexed, including Sysmon, Security, and System events.
- A Windows Sysmon event 11, record ID `3955`, was found in archives without a rule ID. No matching alert document existed for the same agent, channel, and event record ID at verification time.
- The cleanup timer is enabled; its first run completed successfully with zero expired files to delete.
- Six local safety tests passed for the cleanup selector, covering age filtering, active hardlinks, invalid dates, symlinks, and exclusion of alert logs.

The cluster became yellow because the newly created, protected `.opendistro-ism-config` system index requests a replica that cannot be assigned on one node. Archive primaries are assigned and their index is green. An ordinary administrator request to change that protected index was denied; its settings were left unchanged. Do not treat this as an archive-ingestion failure or bypass the protection merely to change a status indicator.

A useful additional Windows-origin test is:

```powershell
powershell.exe -NoProfile -Command "Write-Output 'CORVUS-ARCHIVE-TEST-20261028'"
```

Then search the archive index in Discover:

```text
agent.name:"windy" AND data.win.eventdata.commandLine:*CORVUS-ARCHIVE-TEST-20261028*
```

The test may also trigger a PowerShell detection. It validates marker delivery, not non-alert status; the separate record comparison above demonstrated non-alert evidence availability.

## Backup and Rollback

Pre-change configuration was backed up on the host:

```text
/opt/wazuh-docker/backups/archive-20261028T051244Z/
```

It contains the original Compose file, manager source configuration, and live Filebeat configuration. The Filebeat backup contains credentials and must remain private.

To disable new archive collection and forwarding safely:

1. Restore the backed-up manager source configuration, returning `logall_json` to `no`.
2. Remove the archive hook mount from Compose so it no longer forces forwarding on.
3. Recreate the manager and restore `archives.enabled: false` in its live Filebeat configuration, then restart it. The Filebeat named volume preserves prior edits, so removing the hook alone does not turn forwarding off.
4. Verify alert forwarding remains operational.

Disabling collection does not delete previously stored evidence. Existing archive indices remain subject to their attached deletion policy. If preserving them for an investigation, explicitly address both ISM retention and the cleanup timer before their retention windows expire.

## Remaining Work

- Observe a complete retention cycle and monitor cleanup/ISM failures.
- Measure event volume and storage growth under actual scenarios.
- Add external disk-usage and pipeline-failure alerting; current cleanup warnings are journal-only.
- Define backups, privacy controls, and longer-term retention requirements.
- Build Corvus's read-only evidence adapter against this verified data plane.
