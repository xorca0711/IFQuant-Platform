"""Whole-grid public H&E stitching, pause/resume and reconstruction qualification."""
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from replay_lung_example import acquire

from ifquant_platform.canonical import canonical_sha256, file_sha256, load_strict_json
from ifquant_platform.imaging import register_image, require, write_json
from ifquant_platform.instance_segmentation import match_instances, segment_instanseg
from ifquant_platform.spatial import file_record
from ifquant_platform.whole_slide_instances import run_tiled_instanseg, validate_tiled_instanseg


def replay(cache, output, download=False):
    import zipfile

    import tifffile
    manifest = load_strict_json('datasets/examples/instanseg-brightfield.json')
    cache, root = Path(cache).resolve(), Path(output).resolve()
    files = acquire(manifest, cache, download)
    weights = cache/'instanseg.pt'
    with zipfile.ZipFile(files['brightfield_nuclei.zip']) as archive:
        content = archive.read('instanseg.pt')
        if not weights.exists():
            weights.write_bytes(content)
    root.mkdir(parents=True, exist_ok=False)
    with tifffile.TiffFile(files['HE_example.tif']) as t:
        px = ET.fromstring(t.ome_metadata).find('.//{*}Pixels')
        sx, sy = (float(px.attrib[k]) for k in ('PhysicalSizeX', 'PhysicalSizeY'))
    register_image(files['HE_example.tif'], root/'source.json', subject_id='public-HE-example', species='not_reported',
        specimen_id='public-HE-example', section_id='public-HE-example', pixel_size_x=sx, pixel_size_y=sy)
    plan = {'schema_version': 'ifquant.instanseg-slide/1', 'source': 'source.json', 'weights': str(weights),
        'tile_size': 512, 'halo': 64, 'threads': 4, 'overlap_iou': .5, 'minimum_overlap_pixels': 16, 'maximum_objects': 100000}
    write_json(root/'plan.json', plan)
    paused = run_tiled_instanseg(root/'plan.json', root/'run', max_tiles=2)
    write_json(root/'pause.json', paused)
    run_tiled_instanseg(root/'plan.json', root/'run', resume=True)
    write_json(root/'roi-plan.json', {'schema_version': 'ifquant.instanseg/1', 'source': 'source.json',
        'weights': str(weights), 'window_xywh': [128, 128, 768, 768], 'threads': 4})
    segment_instanseg(root/'roi-plan.json', root/'roi')
    return summarize(root)


def summarize(root):
    """Recover reporting without rerunning committed inference after a report failure."""
    import numpy as np
    import tifffile
    root = Path(root).resolve()
    checked = validate_tiled_instanseg(root/'run')
    source = load_strict_json(root/'source.json')
    roi = load_strict_json(root/'roi/result.json')
    require(roi['source_sha256'] == canonical_sha256(source) and roi['plan']['window_xywh'] == [128, 128, 768, 768],
            'ROI comparison source/grid differs')
    require(all(file_record(r['path']) == r for r in roi['artifacts']), 'ROI bytes changed')
    package = load_strict_json(root/'run/package.json')
    stitched = tifffile.imread(root/'run'/package['product']/'instances.tif')[128:640, 128:640]
    comparison = match_instances(np.load(root/'roi/nuclei.npy', allow_pickle=False)[:512, :512], stitched)
    comparison['reference_kind'] = 'single-window prediction on the same pixels; tiling sensitivity, not independent annotation'
    evidence = {'schema_version': 'ifquant.public-tiled-instanseg/1', 'plan': load_strict_json(root/'plan.json'),
        'source_image_sha256': source['files'][0]['sha256'], 'source_grid': source['grid'],
        'pause_record': load_strict_json(root/'pause.json') if (root/'pause.json').exists() else None,
        'result': package['summary'], 'validation': checked, 'comparison_window_xywh': [128, 128, 512, 512],
        'tiling_comparison': comparison, 'package_sha256': file_sha256(root/'run/package.json'),
        'scientific_validation': False,
        'scope': 'all pixels of a native-resolution public H&E field; whole-slide-capable streaming software, not a billion-pixel slide throughput benchmark'}
    write_json(root/'evidence.json', evidence)
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', default='validation/runtime-cache/instanseg')
    parser.add_argument('--output', required=True)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--summarize-existing', action='store_true')
    args = parser.parse_args()
    print(summarize(args.output) if args.summarize_existing else replay(args.cache, args.output, args.download))
