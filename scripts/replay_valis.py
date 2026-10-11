"""Live public IHC pair plus a controlled-transform coordinate qualification."""
import argparse
import csv
from pathlib import Path

from replay_lung_example import acquire

from ifquant_platform.canonical import file_sha256, load_strict_json
from ifquant_platform.imaging import register_image, require, write_json
from ifquant_platform.valis_execution import run_valis_pair


def replay(cache, output, download=False):
    import cv2
    import numpy as np
    import pyvips
    import tifffile
    from ome_types import from_xml
    from PIL import Image
    cache, root = Path(cache).resolve(), Path(output).resolve()
    manifest = load_strict_json('datasets/examples/valis-ihc-pair.json')
    files = acquire(manifest, cache, download)
    root.mkdir(parents=True, exist_ok=False)
    arrays, scales = [], []
    for i, filename in enumerate(('ihc_1.ome.tiff', 'ihc_2.ome.tiff')):
        path = files[filename]
        with tifffile.TiffFile(path) as f:
            pixels = from_xml(f.ome_metadata).images[0].pixels
            require(pixels.physical_size_x_unit.value == pixels.physical_size_y_unit.value == 'µm', 'OME micrometer calibration required')
            scale = [pixels.physical_size_x, pixels.physical_size_y]
        image = pyvips.Image.new_from_file(str(path))
        require(image.format == 'uchar' and image.bands == 3, 'uint8 RGB TIFF required')
        data = np.frombuffer(image.write_to_memory(), dtype=np.uint8).reshape(image.height, image.width, 3)
        require(data.dtype == np.uint8 and data.ndim == 3 and data.shape[2] == 3, 'RGB public image expected')
        Image.fromarray(data).save(root/f'ihc-{i}.png')
        register_image(root/f'ihc-{i}.png', root/f'ihc-{i}-source.json', subject_id='VALIS-IHC-series-proxy', species='not_reported',
            specimen_id='VALIS-IHC-series-proxy', section_id=f'example-{i}', modality='brightfield', reader='pillow',
            pixel_size_x=scale[0], pixel_size_y=scale[1], members=[path])
        arrays.append(data); scales.append(scale)
    angle = np.deg2rad(3)
    truth = np.array([[np.cos(angle), -np.sin(angle), 45], [np.sin(angle), np.cos(angle), -35], [0, 0, 1]])
    height, width = arrays[0].shape[:2]
    controlled = cv2.warpAffine(arrays[0], truth[:2], (width, height),
        flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=(255, 255, 255))
    Image.fromarray(controlled).save(root/'controlled.png')
    write_json(root/'controlled-transform.json', {'moving_to_fixed_pixels': truth.tolist(),
        'generation': 'cv2 warpAffine with WARP_INVERSE_MAP; source image sampled at truth @ moving coordinate',
        'reference_kind': 'known image resampling transform; not independent biological landmark annotations'})
    register_image(root/'controlled.png', root/'controlled-source.json', subject_id='VALIS-IHC-series-proxy', species='not_reported',
        specimen_id='VALIS-IHC-series-proxy', section_id='example-0', modality='brightfield', reader='pillow',
        pixel_size_x=scales[0][0], pixel_size_y=scales[0][1], members=[root/'controlled-transform.json'])
    results = {}
    for name, source_name, transform, nonrigid in (('controlled', 'controlled-source.json', truth, False),
                                                ('public_pair', 'ihc-1-source.json', None, True)):
        source = load_strict_json(root/source_name)
        width, height = (source['grid'][k] for k in ('width', 'height'))
        with (root/f'{name}-points.csv').open('x', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['point_id', 'role', 'source_x', 'source_y', 'target_x', 'target_y'])
            for i, (y, x) in enumerate((y, x) for y in np.linspace(.2*height, .8*height, 4) for x in np.linspace(.2*width, .8*width, 4)):
                writer.writerow([f'p{i}', 'probe', x, y, '', ''])
                if transform is not None:
                    target = transform @ [x+3, y+5, 1]
                    writer.writerow([f'e{i}', 'evaluation', x+3, y+5, *target[:2]])
            writer.writerow(['o0', 'observation', width/2, height/2, '', ''])
        cfg = {'schema_version': 'ifquant.valis-pair/1', 'moving_source': source_name,
            'fixed_source': 'ihc-0-source.json', 'points_csv': f'{name}-points.csv',
            'section_relation': 'same_section' if transform is not None else 'unknown',
            'heldout_reference': 'controlled-transform.json; not supplied to registration' if transform is not None else 'not_available; no independent landmark accuracy claim',
            'non_rigid': nonrigid, 'processed_size': 1024, 'seed': 20261011,
            'model_cache': str(cache/'torch'), 'probe_grid_xy': [4, 4], 'max_local_distance_um': 3000}
        write_json(root/f'{name}-plan.json', cfg)
        results[name] = run_valis_pair(root/f'{name}-plan.json', root/name)
    report = {'schema_version': 'ifquant.public-valis-evidence/1', 'manifest_sha256': file_sha256('datasets/examples/valis-ihc-pair.json'),
        'runs': {name: {'seconds': r['seconds'], 'qc': r['qc'], 'runtime': r['runtime'],
                       'result_sha256': file_sha256(root/name/'result.json')} for name, r in results.items()},
        'scientific_validation': False, 'independent_public_pair_landmarks': False}
    write_json(root/'evidence.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', default='validation/runtime-cache/valis')
    parser.add_argument('--output', required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    print(replay(args.cache, args.output, args.download))
