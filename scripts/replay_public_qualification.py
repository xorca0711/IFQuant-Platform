"""Pinned WSI window benchmark and published Slide-GoTags table reconciliation."""
from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

from reconcile_gotags_source import reconcile

from ifquant_platform.canonical import file_sha256, load_strict_json
from ifquant_platform.imaging import register_image, require, write_json
from ifquant_platform.imaging_evaluation import benchmark_image


def acquire(record, cache, download):
    relative = Path(record['name'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe cache name')
    path = Path(cache)/relative
    if not path.exists():
        require(download, 'missing qualification input; explicitly supply --download')
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name+'.partial')
        expected = record['size_bytes']
        while not partial.exists() or partial.stat().st_size < expected:
            start = partial.stat().st_size if partial.exists() else 0
            end = min(start+4*1024**2, expected)-1
            request = urllib.request.Request(record['url'], headers={'Range': f'bytes={start}-{end}'})
            with urllib.request.urlopen(request, timeout=90) as response:
                if response.status == 206:
                    require(response.headers.get('Content-Range') == f'bytes {start}-{end}/{expected}', 'unexpected range response')
                    block = response.read(end-start+2)
                    require(len(block) == end-start+1, 'truncated or oversized range; retry without publishing')
                    with partial.open('ab') as stream:
                        stream.write(block)
                else:
                    require(start == 0 and response.status == 200, 'server did not honor continuation range')
                    copied = 0
                    with partial.open('wb') as stream:
                        while block := response.read(1024**2):
                            copied += len(block)
                            require(copied <= expected, 'download exceeds pinned size')
                            stream.write(block)
                    require(copied == expected, 'truncated full download; retry with retained partial')
        require(partial.stat().st_size == expected and file_sha256(partial) == record['sha256'], 'download integrity mismatch')
        partial.rename(path)
    require(path.stat().st_size == record['size_bytes'] and file_sha256(path) == record['sha256'], 'cached qualification bytes differ')
    return path


def replay(manifest_path, cache, output, download=False):
    manifest = load_strict_json(manifest_path)
    files = {record['role']: acquire(record, cache, download) for record in manifest['files']}
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    register_image(files['wsi'], root/'source.json', subject_id='CMU-1-source-proxy', species='not_reported',
                   specimen_id='CMU-1', section_id='CMU-1-section', pixel_size_x=.499, pixel_size_y=.499)
    benchmark = benchmark_image(root/'source.json', root/'benchmark.json', tiles=64, tile_size=512, seed=42)
    table = reconcile(files['supplement'], files['figure_source'], root/'published-table-check.json')
    result = {'schema_version': 'ifquant.public-qualification-replay/1', 'manifest': manifest,
              'image_benchmark': benchmark, 'published_table_check': table, 'scientific_validation': False}
    write_json(root/'report.json', result)
    return {'output': str(root), 'image_benchmark': benchmark, 'published_table_check': table}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', default='datasets/examples/public-qualification.json')
    p.add_argument('--cache', default='validation/runtime-cache')
    p.add_argument('--output', required=True)
    p.add_argument('--download', action='store_true')
    args = p.parse_args()
    print(replay(args.manifest, args.cache, args.output, args.download))
