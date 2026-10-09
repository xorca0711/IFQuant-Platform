"""Create a fresh, isolated QuPath smoke run from an existing configured pilot.

Never saves into the input project. Image bytes remain at their declared URI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--qupath', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(args.project.parent, root / 'project')
    project = root / 'project' / args.project.name
    project_doc = json.loads(project.read_text(encoding='utf-8'))
    project_doc['uri'] = project.as_uri()
    project.write_text(json.dumps(project_doc, indent=2), encoding='utf-8')
    script = Path(config['execution']['script_path']).resolve()
    script_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    now = datetime.now(UTC).isoformat().replace('+00:00', 'Z')
    attestation = {'qupath_path': str(args.qupath.resolve()),
                   'qupath_sha256': hashlib.sha256(args.qupath.read_bytes()).hexdigest(),
                   'code_revision': revision, 'exporter_sha256': script_hash,
                   'created_at': now, 'claims': 'engineering only'}
    payload = json.dumps(attestation, sort_keys=True, indent=2).encode()
    (root / 'runtime.json').write_bytes(payload)
    config['output_directory'] = (root / 'package').as_posix()
    config['package']['package_id'] = 'pkg_' + root.name.replace('-', '_')
    config['segmentation']['segmentation_run_id'] = 'seg_' + root.name.replace('-', '_')
    config['execution']['expected_script_sha256'] = script_hash
    config['provenance'].update(created_at=now, code_revision=revision)
    config['segmentation']['provenance'].update(
        created_at=now, code_revision=revision,
        runtime_sha256=hashlib.sha256(payload).hexdigest())
    for key, value in config['segmentation'].get('runtime_inputs', {}).items():
        if key.endswith('_path'):
            config['segmentation']['runtime_inputs'][key] = (
                args.config.parent / value).resolve().as_posix()
    output_config = root / 'run.json'
    output_config.write_text(json.dumps(config, indent=2), encoding='utf-8')
    command = [str(args.qupath.resolve()), 'script', '--project', str(project),
               '--image', config['image']['expected_server_name'],
               '--args', str(output_config), str(script)]
    with (root / 'qupath.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                check=False,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    print(json.dumps({'returncode': result.returncode, 'run': str(root),
                      'package_present': (root / 'package/package.json').is_file()}))
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
