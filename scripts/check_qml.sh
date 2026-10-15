#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
shell_dir="${OMARCHY_PATH:-/usr/share/omarchy}/shell"
lint_bin="$(command -v qmllint || true)"
if [[ -z "$lint_bin" ]]; then lint_bin=/usr/lib/qt6/bin/qmllint; fi
if [[ ! -x "$lint_bin" || ! -d "$shell_dir/Ui" ]]; then
  echo 'QML checks require qt6-declarative and an installed Omarchy shell.' >&2
  exit 1
fi
lint_dir="$(mktemp -d)"
trap 'rm -rf "$lint_dir"' EXIT
ln -s "$shell_dir" "$lint_dir/qs"
"$lint_bin" -I "$lint_dir" -I "$shell_dir" BarWidget.qml Panel.qml PeekContent.qml Collector.qml Request.qml SummaryCard.qml
python3 - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path('manifest.json').read_text())
assert manifest['schemaVersion'] == 1
assert manifest['id'] == 'nachfq.peek' and manifest['version'] == '0.2.0'
assert manifest['license'] == 'MIT' and manifest['author'] == 'Nacho fq'
assert manifest['kinds'] == ['bar-widget']
assert Path(manifest['entryPoints']['barWidget']).is_file()
print('Manifest validated')
PY
