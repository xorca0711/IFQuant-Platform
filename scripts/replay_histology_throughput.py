"""Complete real-image pipeline at a declared pyramid level; throughput only."""
import argparse
import threading
import time
from pathlib import Path

from replay_public_qualification import acquire

from ifquant_platform.canonical import canonical_sha256, load_strict_json
from ifquant_platform.histology import fit_model
from ifquant_platform.imaging import register_image, write_json
from ifquant_platform.tissue_workflow import run_histology, validate_histology


def replay(cache, output, download=False):
    import psutil
    manifest = load_strict_json('datasets/examples/public-qualification.json')
    record = next(r for r in manifest['files'] if r['role'] == 'wsi')
    path = acquire(record, Path(cache).resolve(), download)
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    plan = {'source': record, 'fit_level': 2, 'run_level': 1, 'tile_size': 512,
            'clusters': 3, 'seed': 42, 'max_samples': 30000, 'pixel_size_um': .499,
            'scope': 'same-image unsupervised appearance fit and complete selected-level execution; no held-out model accuracy or lung identity'}
    write_json(root/'plan.json', plan)
    for name, level in (('fit', 2), ('analysis', 1)):
        register_image(path, root/f'{name}-source.json', subject_id='CMU-1-source-proxy', species='not_reported',
            specimen_id='CMU-1', section_id='CMU-1-section', pixel_size_x=.499, pixel_size_y=.499, level=level)
    source = load_strict_json(root/'analysis-source.json')
    width, height = source['grid']['base_width'], source['grid']['base_height']
    write_json(root/'regions.json', {'schema_version': 'ifquant.regions/1', 'source_sha256': canonical_sha256(source),
        'coordinate_frame': 'base_image_pixels', 'parent': None, 'regions': [{
            'region_id': 'image-footprint', 'role': 'reference', 'anatomy': 'unresolved', 'label': 'unreviewed image bounds',
            'wkt': f'POLYGON ((0 0, {width} 0, {width} {height}, 0 {height}, 0 0))',
            'review': {'status': 'pending', 'reviewer': None, 'at': None, 'reason': 'image footprint only; no tissue/pathology annotation'}}]})
    peak, stopped = [psutil.Process().memory_info().rss], threading.Event()
    def sample():
        while not stopped.wait(.1):
            peak[0] = max(peak[0], psutil.Process().memory_info().rss)
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    start = time.perf_counter()
    try:
        fit_model(root/'fit-source.json', root/'model.json', clusters=3, seed=42, max_samples=30000)
        fit_seconds = time.perf_counter()-start
        run_start = time.perf_counter()
        run_histology(root/'analysis-source.json', root/'model.json', root/'regions.json', root/'run')
        run_seconds = time.perf_counter()-run_start
        check = validate_histology(root/'run')
    finally:
        stopped.set()
        sampler.join()
    report = {'schema_version': 'ifquant.histology-throughput/1', 'plan': plan, 'grid': source['grid'],
        'fit_seconds': fit_seconds, 'run_seconds': run_seconds, 'sampled_peak_rss_bytes': peak[0],
        'package_validation': check, 'scientific_validation': False}
    write_json(root/'evidence.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', default='validation/runtime-cache')
    parser.add_argument('--output', required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    print(replay(args.cache, args.output, args.download))
