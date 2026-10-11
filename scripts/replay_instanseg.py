"""Pinned upstream model fixture and one calibrated public H&E ROI."""
import argparse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from replay_lung_example import acquire

from ifquant_platform.canonical import file_sha256, load_strict_json
from ifquant_platform.imaging import register_image, require, write_json
from ifquant_platform.instance_segmentation import match_instances, segment_instanseg


def replay(manifest_path, cache, output, download=False):
    import numpy as np
    import tifffile
    manifest = load_strict_json(manifest_path)
    cache, root = Path(cache).resolve(), Path(output).resolve()
    files = acquire(manifest, cache, download)
    root.mkdir(parents=True, exist_ok=False)
    # Extract only these flat, named members from the pinned archive.
    with zipfile.ZipFile(files['brightfield_nuclei.zip']) as archive:
        for name in ('instanseg.pt', 'test-input.npy', 'test-output_instance_segmentation.npy', 'rdf.yaml'):
            content = archive.read(name)
            target = cache/name
            if target.exists():
                require(target.read_bytes() == content, 'model cache drift')
            else:
                target.write_bytes(content)
    fixture = np.load(cache/'test-input.npy', allow_pickle=False)[0].transpose(1, 2, 0)
    require(np.isfinite(fixture).all() and (fixture == np.floor(fixture)).all() and
            (fixture >= 0).all() and (fixture <= 255).all(), 'fixture requires lossless uint8 RGB conversion')
    tifffile.imwrite(root/'fixture.tif', fixture.astype(np.uint8), photometric='rgb', tile=(256, 256))
    with tifffile.TiffFile(files['HE_example.tif']) as tif:
        pixels = ET.fromstring(tif.ome_metadata).find('.//{*}Pixels')
        require(pixels.attrib['PhysicalSizeXUnit'] == pixels.attrib['PhysicalSizeYUnit'] == 'µm', 'source units differ')
        sx, sy = (float(pixels.attrib[k]) for k in ('PhysicalSizeX', 'PhysicalSizeY'))
    results = {}
    for name, path, calibration, window in (
        ('fixture', root/'fixture.tif', (0.5, 0.5), [0, 0, 256, 256]),
        ('public_he', files['HE_example.tif'], (sx, sy), [256, 256, 512, 512])):
        register_image(path, root/f'{name}-source.json', subject_id=f'upstream-{name}', species='not_reported',
            specimen_id=f'upstream-{name}', section_id=f'upstream-{name}',
            pixel_size_x=calibration[0], pixel_size_y=calibration[1])
        write_json(root/f'{name}-plan.json', {'schema_version': 'ifquant.instanseg/1',
            'source': f'{name}-source.json', 'weights': str(cache/'instanseg.pt'), 'window_xywh': window, 'threads': 4})
        segment_instanseg(root/f'{name}-plan.json', root/name)
        results[name] = load_strict_json(root/name/'result.json')
    reference = np.load(cache/'test-output_instance_segmentation.npy', allow_pickle=False)[0, 0]
    comparison = match_instances(reference, np.load(root/'fixture/nuclei.npy', allow_pickle=False))
    comparison['reference_kind'] = 'upstream model test output; conformance reference, not independent expert annotation'
    report = {'schema_version': 'ifquant.public-instanseg-evidence/1',
        'manifest_sha256': file_sha256(manifest_path), 'scientific_validation': False,
        'fixture_comparison': comparison, 'public_calibration_um': [sx, sy],
        'calibration_sources': {'fixture': 'pinned model rdf.yaml input axis scale', 'public_he': 'pinned TIFF OME PhysicalSizeX/Y'},
        'runs': {name: {'objects': r['objects'], 'seconds': r['seconds'], 'engine': r['engine'],
                       'result_sha256': file_sha256(root/name/'result.json')} for name, r in results.items()}}
    write_json(root/'evidence.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', default='datasets/examples/instanseg-brightfield.json')
    parser.add_argument('--cache', default='validation/runtime-cache/instanseg')
    parser.add_argument('--output', required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    print(replay(args.manifest, args.cache, args.output, args.download))
