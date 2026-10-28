# Wazuh Lab: Current Deployment

Status: Wazuh infrastructure, Windows collection, and searchable non-alert archives are configured and initially validated. The [read-only collector](read-only-cli.md) and a separate [advisory model baseline](investigation-reports.md) are implemented. Model testing used synthetic fixtures only; response execution and a persistent Corvus service are not implemented.

This is an operational record of the current lab, not a production deployment guide. Full runtime configuration and secrets reside on the VM. Selected archive configuration helpers are versioned under `infra/wazuh/`; see [searchable telemetry archives](telemetry-archives.md).

## Deployment Summary

| Item | Current configuration |
| --- | --- |
| Administrative access | `ssh wazuh`, user `ubuntu` |
| Host OS | Ubuntu 26.04.1 LTS, x86_64 |
| Host resources | 4 vCPUs, 16 GiB RAM, 100 GB disk (resized and verified) |
| Deployment directory | `/opt/wazuh-docker/single-node` |
| Upstream repository | `https://github.com/wazuh/wazuh-docker` |
| Upstream tag | `v4.14.9` |
| Upstream commit | `56ece955b1107b7b62823afae5b7057e1dab9d98` |
| Wazuh manager, indexer, dashboard | Official images, version `4.14.9` |
| Reverse proxy | `caddy:2.11.7` |
| Dashboard | `https://wazuh.tusharr.xyz` |
| Current public IPv4 | `98.80.223.229` |
| Private IPv4 at setup | `172.31.38.214` |

The host OS is newer than the Ubuntu versions listed in the native Wazuh quickstart. This deployment uses container images instead of native Wazuh packages. Successful lab checks do not establish full upstream support for this host combination.

After resizing, SSH host keys were matched against the original host and all four containers restarted successfully. The private IP remained unchanged. Monitor memory, load, and query latency as the application and telemetry volume grow.

## Windows Endpoint

- Agent: `windy`, ID `001`, Wazuh `4.14.9`, verified active.
- SSH access: `ssh windy`. OpenSSH's default shell is Windows PowerShell `5.1`, configured through `HKLM:\SOFTWARE\OpenSSH` (`DefaultShell` and `DefaultShellCommandOption`). A fresh session was verified.
- Sysmon version independently verified over SSH: `15.22`; Sysmon and Wazuh services are running.
- Pinned Sysmon Modular Balanced profile targeting 15.21, release `configs-a45dedb13a43`, schema `4.91`. Sysmon event 16 and the XML file both report SHA-256 `64bec37ba849c5f2934a55d2a29e7ddfae46a30d56f7f2908d1f8a454898797e`.
- Active agent collector configuration includes Sysmon, Windows PowerShell, Security, System, and Application channels.
- Sysmon process creation and file creation, plus PowerShell script-block events, were observed in indexed alerts.
- Windows events were also found in archive indices without matching alert documents.

## Host Preparation

- Updated package metadata and applied available upgrades through `apt-get upgrade`.
- Installed Ubuntu-packaged Docker Engine and the Compose v2 plugin.
- Added `ubuntu` to the `docker` group and verified Docker access in a fresh SSH session without sudo.
- Enabled Docker to start at boot.
- Persisted `vm.max_map_count=1048576`, the host's existing value, above Wazuh's required minimum.
- Configured Docker JSON log rotation: 10 MB per file, three files per container.
- No reboot was requested after the upgrades.

Two cloud-init packages were still listed as upgradable after the standard upgrade; do not assume all phased or held updates were applied.

Docker group membership is effectively root-level access. Do not grant it to untrusted users.

## Networking

| Host binding | Purpose | Exposure |
| --- | --- | --- |
| `80/tcp` | Caddy HTTP redirect and possible ACME validation | Published; externally unreachable during checks |
| `443/tcp` | Caddy HTTPS dashboard | Published; external HTTPS verified |
| `172.31.38.214:1514/tcp` | Agent event transport | Private address only |
| `172.31.38.214:1515/tcp` | Agent enrollment | Private address only |
| `127.0.0.1:8443/tcp` | Direct dashboard access | Host loopback only |
| `127.0.0.1:9200/tcp` | Indexer API | Host loopback only |
| `127.0.0.1:55000/tcp` | Wazuh manager API | Host loopback only |

The host's UFW firewall was inactive when inspected. AWS security-group rules were not changed or audited by this deployment. Docker publishes ports through its own networking rules; do not rely solely on UFW to restrict them.

Recommended AWS controls:

- Restrict SSH and dashboard access to the operator's IP or a VPN.
- Allow 1514 and 1515 only from the Windows endpoint security group.
- Never expose 9200, 55000, or 8443 publicly.
- Keep an ACME validation path reachable. Caddy obtained the certificate through HTTPS with port 80 externally blocked. Restricting 443 may require allowing port 80 for HTTP validation or deliberately configuring DNS validation.
- Use an Elastic IP if the domain must survive instance stops and starts without a DNS update.

## TLS and Authentication

Caddy terminates public HTTPS and proxies to the dashboard over TLS using the generated Wazuh CA. Upstream certificate verification is enabled; it is not configured to skip verification.

A Let's Encrypt certificate was issued successfully. Caddy manages renewal and persists certificate state in a Docker volume. Renewal still depends on working DNS and reachable validation ports.

Generated credentials replace the indexer administrator, dashboard service-account, and dashboard-to-manager API defaults. Extra indexer demo accounts were removed. The built-in manager API administrator password was also rotated and its login verified.

Credentials are stored on the VM at:

```text
/home/ubuntu/.config/corvus/wazuh-credentials.json
```

The file is owned by `ubuntu` with mode `0600`; its immediate directory has mode `0700`. The deployment's `.env` also contains service secrets and has mode `0600`. Configuration files and private keys are protected by the deployment parent directory's mode `0700` and their individual permissions.

To retrieve credentials privately in your own terminal:

```bash
ssh wazuh 'python3 -m json.tool ~/.config/corvus/wazuh-credentials.json'
```

Use `dashboard_username` and `dashboard_password` for browser login. Do not paste the file into issues, commits, screenshots, or shared logs. Editing this JSON file alone does not rotate service passwords.

Corvus uses a separate `corvus-reader` account restricted to reading alert and archive indices. Reader credentials are in `~ubuntu/.config/corvus/wazuh-reader.json`; a private local CLI config uses that account through an SSH tunnel. The application does not use manager API or administrator credentials. See [CLI access and TLS configuration](read-only-cli.md).

## Operations

Run these on the VM as `ubuntu`:

```bash
cd /opt/wazuh-docker/single-node

docker compose ps
docker compose logs --tail=50 wazuh.indexer
docker compose logs --tail=50 wazuh.manager
docker compose logs --tail=50 wazuh.dashboard
docker compose logs --tail=50 caddy
docker stats --no-stream
```

To start services or apply a deliberately reviewed configuration change:

```bash
docker compose up -d
```

To pause services while retaining containers and volumes:

```bash
docker compose stop
```

Do not use `docker compose down -v` unless intentionally destroying the lab's persistent data. Do not blindly pull a newer Wazuh release; upgrades require compatibility checks and backups.

Configuration, credentials, certificates, and named volumes all need a backup strategy. Docker log rotation does not set retention for indexed events or Wazuh's internal file logs. Three-day archive index retention and a separate closed-archive-file cleanup timer are now configured; alert retention was not changed. See [archive operations and rollback](telemetry-archives.md). EBS storage continues to incur charges while EC2 is stopped.

## Verification Completed

- Docker commands work without sudo for `ubuntu` in a fresh SSH session.
- Manager, indexer, dashboard, and Caddy containers are running.
- Core manager daemons are running.
- Manager API authentication succeeds with generated credentials.
- Alert and archive data indices are green. The cluster is currently yellow because the protected ISM configuration index has one unassignable replica on this single-node lab; archive primaries are assigned.
- Wazuh alert documents are being indexed from both manager and Windows activity.
- Non-alert Windows evidence is searchable in `wazuh-archives-*`; the archive deletion policy and cleanup timer are enabled.
- Public dashboard login page returns HTTP 200 over publicly trusted HTTPS.
- Browser-login API accepts the generated dashboard credentials and returns a session cookie.

These are initial collection and search checks, not complete detection-coverage validation. Response actions, recovery after a host reboot, and deletion over a full three-day retention cycle have not been tested.

## Next Steps

1. Review AWS security groups and restrict administrative access.
2. Repeat Windows marker tests after baseline changes and measure event volume.
3. Define a safe, repeatable investigation scenario with both malicious and benign variants.
4. Observe a complete archive retention cycle and monitor policy/timer failures.
5. Define backups, alert-data retention, and external disk/cost alerts.
6. Expand the read-only adapter's scenario coverage before adding model reasoning.

## References

- [Wazuh Docker deployment](https://documentation.wazuh.com/current/deployment-options/docker/wazuh-container.html)
- [Changing default Docker deployment passwords](https://documentation.wazuh.com/current/deployment-options/docker/changing-default-password.html)
- [Corvus architecture](architecture.md)
