#!/usr/bin/env bash
# Wazuh Docker runs this hook after configuring Filebeat and before starting services.
# Keep the change reproducible even if the Filebeat configuration volume is replaced.
set -euo pipefail

/var/ossec/framework/python/bin/python3 - <<'PY'
from pathlib import Path
import re

path = Path('/etc/filebeat/filebeat.yml')
text = path.read_text()
pattern = r'(?m)^([ \t]+archives:[ \t]*\n[ \t]+enabled:[ \t]*)(?:false|true)([ \t]*(?:#.*)?)$'
updated, count = re.subn(pattern, r'\g<1>true\g<2>', text)
if count != 1:
    raise SystemExit('Expected exactly one Filebeat archives enabled setting; refusing to guess.')
if updated != text:
    path.write_text(updated)
print('Corvus lab: Filebeat archive forwarding enabled.')
PY

/usr/bin/filebeat test config -c /etc/filebeat/filebeat.yml
