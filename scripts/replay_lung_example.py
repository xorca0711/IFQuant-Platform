"""Replay a pinned public lung sample without fabricating calibration or pathology labels.

Run with the [imaging,spatialdata] extras. Downloads are opt-in and stay outside Git.
The region summaries use deposited in_tissue flags and an explicitly unreviewed
image-footprint region; they do not claim anatomical segmentation.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import html
import json
import threading
import time
import urllib.request
from collections import Counter
from pathlib import Path

from ifquant_platform.canonical import file_sha256, load_strict_json
from ifquant_platform.imaging import require, write_json
from ifquant_platform.spatial import count_rows
from ifquant_platform.spatial_adapters import STATUS, export_anndata, import_native
from ifquant_platform.spatial_exchange import export_spatialdata, import_spatialdata


def acquire(manifest, cache, download):
    cache.mkdir(parents=True, exist_ok=True)
    files = {}
    for record in manifest['files']:
        path = cache/record['name']
        if not path.exists():
            require(download, 'missing cached data; supply --download to retrieve pinned public files')
            temporary = path.with_suffix(path.suffix+'.partial')
            with urllib.request.urlopen(record['url'], timeout=90) as response, temporary.open('wb') as stream:
                copied = 0
                while block := response.read(1024*1024):
                    copied += len(block)
                    require(copied <= record['size_bytes'], 'download larger than pinned input')
                    stream.write(block)
            require(file_sha256(temporary) == record['sha256'], 'download digest mismatch')
            temporary.rename(path)
        require(path.stat().st_size == record['size_bytes'] and file_sha256(path) == record['sha256'],
                'cached source differs from pinned manifest')
        if path.suffix == '.gz':
            decoded = path.with_suffix('')
            content = gzip.decompress(path.read_bytes())
            if decoded.exists():
                require(decoded.read_bytes() == content, 'decompressed cache differs')
            else:
                decoded.write_bytes(content)
            files[record['name']] = decoded
        else:
            files[record['name']] = path
    return files


def replay(manifest_path, cache, output, download=False):
    import h5py
    import numpy as np
    import psutil
    from PIL import Image, ImageDraw

    manifest = load_strict_json(manifest_path)
    files = acquire(manifest, Path(cache).resolve(), download)
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    peak, stopped = [psutil.Process().memory_info().rss], threading.Event()
    def sample_memory():
        while not stopped.wait(.1):
            peak[0] = max(peak[0], psutil.Process().memory_info().rss)
    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    try:
        return _replay(manifest, files, root, np, h5py, Image, ImageDraw, start, peak)
    finally:
        stopped.set()
        sampler.join()


def _replay(manifest, files, root, np, h5py, Image, ImageDraw, start, peak):
    prefix = manifest['sample']+'_Day3_Young_'
    image_path = files[prefix+'tissue_hires_image.png.gz']
    matrix_path = files[prefix+'filtered_feature_bc_matrix.h5']
    subject = {'subject_id': manifest['sample']+'-library-proxy', 'species': 'Mus musculus',
               'specimen_id': manifest['sample'], 'section_id': manifest['sample']+'-deposited-section'}
    metadata = {'assay_id': manifest['sample']+'-five-gene-panel', 'subject': subject, 'entity_type': 'spot',
                'coordinate_frame': {'frame_id': manifest['sample']+'-hires-pixels', 'unit': 'pixel',
                'axes': ['x', 'y'], 'origin': 'top_left', 'y_direction': 'down'}}
    config = dict(metadata, schema_version='ifquant.native-spatial-import/1', format='visium_h5',
                  inputs={'matrix_h5': str(matrix_path),
                  'positions': str(files[prefix+'tissue_positions_list.csv.gz']),
                  'scalefactors': str(files[prefix+'scalefactors_json.json.gz'])},
                  options={'positions_profile': 'legacy_headerless', 'matrix_scope': 'filtered',
                           'target_image': 'hires', 'feature_ids': [g['feature_id'] for g in manifest['genes']]})
    write_json(root/'native-import.json', config)
    import_native(root/'native-import.json', root/'native')
    assay_path = root/'native/assay.json'
    assay = load_strict_json(assay_path)
    observed = dict.fromkeys(config['options']['feature_ids'], 0)
    for _, fid, value in count_rows(assay):
        observed[fid] += value
    # Independent source computation, without the adapter's row iterator or CSVs.
    expected, source_total = {}, 0
    with h5py.File(matrix_path, 'r') as h:
        matrix = h['matrix']
        feature_ids = list(matrix['features/id'].asstr()[:])
        feature_names = list(matrix['features/name'].asstr()[:])
        indices, values = matrix['indices'][:], matrix['data'][:]
        source_total = int(values.sum(dtype=np.int64))
        for gene in manifest['genes']:
            index = feature_ids.index(gene['feature_id'])
            require(feature_names[index] == gene['feature_name'], 'source feature identity differs')
            expected[gene['feature_id']] = int(values[indices == index].sum(dtype=np.int64))
        full_shape = matrix['shape'][:].tolist()
        source_nnz = len(values)
        del indices, values
    require(observed == expected, 'selected raw counts differ from deposited HDF5')
    export_anndata(assay_path, root/'rna.h5ad')
    ann_config = dict(metadata, schema_version='ifquant.native-spatial-import/1', format='anndata',
                      inputs={'h5ad': 'rna.h5ad'}, options={'counts_layer': 'X', 'coordinates_key': 'spatial',
                      'feature_name_column': 'feature_name', 'status_column': STATUS,
                      'default_status': 'measured', 'feature_ids': None})
    write_json(root/'ann-import.json', ann_config)
    import_native(root/'ann-import.json', root/'ann-roundtrip')
    with Image.open(image_path) as image:
        width, height = image.size
        overlay = image.convert('RGBA')
    # A footprint is a context region, explicitly not a tissue/lesion annotation.
    write_json(root/'regions.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': 'image-footprint', 'properties': {'review_status': 'pending',
         'role': 'image_context', 'interpretation': 'unreviewed image bounds; not anatomical tissue'},
         'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [width, 0], [width, height], [0, height], [0, 0]]]}}]})
    write_json(root/'scene.json', {'frame_id': manifest['sample']+'-image-pixels', 'image': str(image_path),
               'assay_to_image': [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 'regions_geojson': 'regions.geojson',
               'scale_factors': [2, 2]})
    export_spatialdata(assay_path, root/'scene.zarr', scene_path=root/'scene.json')
    restored = import_spatialdata(root/'scene.zarr', root/'spatialdata-roundtrip')
    for path in (root/'ann-roundtrip/assay.json', Path(restored['output'])):
        other = load_strict_json(path)
        require(all(other[k] == assay[k] for k in ('subject', 'coordinate_frame', 'observations', 'features', 'statistics')),
                'round-trip semantic mismatch')
        require(sorted(count_rows(other)) == sorted(count_rows(assay)), 'round-trip raw counts differ')
    import anndata as ad
    annotations = ad.read_h5ad(root/'native/annotations.h5ad').obs
    layer = Image.new('RGBA', overlay.size)
    draw = ImageDraw.Draw(layer)
    spots, regions = [], Counter()
    for obs in assay['observations']:
        oid, x, y = obs['observation_id'], obs['x'], obs['y']
        inside = 0 <= x < width and 0 <= y < height
        in_tissue = int(annotations.loc[oid, 'in_tissue'])
        measured = obs['assay_status'] == 'measured'
        if inside:
            color = (0, 150, 150, 150) if measured else (100, 100, 100, 90)
            draw.ellipse((x-2, y-2, x+2, y+2), fill=color)
        label = 'image-footprint' if inside else 'outside-image'
        regions[(label, str(in_tissue), obs['assay_status'])] += 1
        spots.append({'observation_id': oid, 'x_hires_px': x, 'y_hires_px': y,
                      'source_in_tissue': in_tissue, 'assay_status': obs['assay_status'], 'context_region': label})
    Image.alpha_composite(overlay, layer).convert('RGB').save(root/'overlay.png')
    with (root/'spots.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(spots[0]))
        writer.writeheader(); writer.writerows(spots)
    sums = [{**g, 'raw_count_sum': observed[g['feature_id']], 'source_raw_count_sum': expected[g['feature_id']]}
            for g in manifest['genes']]
    report = {'schema_version': 'ifquant.lung-replay/1', 'sample': manifest['sample'],
              'source_files': manifest['files'], 'image_dimensions': [width, height],
              'full_source_matrix_features_by_spots': full_shape, 'source_nonzero_counts': source_nnz,
              'full_source_raw_count_sum': source_total, 'selected_panel_statistics': assay['statistics'] | {'libraries': 'see native/assay.json'},
              'observation_status_counts': dict(Counter(o['assay_status'] for o in assay['observations'])),
              'context_region_counts': [{'region': k[0], 'source_in_tissue': int(k[1]), 'assay_status': k[2], 'spots': v}
                                        for k, v in sorted(regions.items())],
              'gene_sums': sums, 'anndata_roundtrip': 'passed', 'spatialdata_roundtrip': 'passed',
              'source_raw_count_reconciliation': 'passed', 'physical_calibration': 'unavailable',
              'registration': 'deposited image scaling only; no independent landmarks',
              'pathology_review': 'not supplied; image footprint is not anatomical annotation',
              'scientific_validation': False, 'elapsed_seconds': round(time.perf_counter()-start, 3),
              'sampled_peak_rss_bytes': peak[0]}
    write_json(root/'report.json', report)
    rows = ''.join('<tr><td>'+html.escape(r['feature_name'])+'</td><td>'+str(r['raw_count_sum'])+'</td></tr>' for r in sums)
    body = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Lung spatial replay</title><style>'
    body += 'body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}img{max-width:100%}td,th{padding:.4rem 1rem;text-align:left}p{line-height:1.5}</style>'
    body += '<h1>Day 3 young lung: image and RNA intake</h1><p>'+html.escape(manifest['scope'])+'</p>'
    body += '<p>'+html.escape(manifest['identity_limit'])+'</p><p>'+html.escape(manifest['image_limit'])+'</p>'
    body += '<p>Teal: counts available. Gray: absent from the supplied filtered matrix. Coordinates use the deposited hires scale once. '
    body += 'Neither color indicates injury, cell identity or pathology review. No physical calibration is assumed.</p><img src="overlay.png" alt="Deposited H&E derivative with spot centers">'
    body += '<h2>Raw counts in the declared five-gene panel</h2><p>Each total exactly matches a separate calculation from the deposited HDF5. '
    body += 'These are unnormalized counts, not cell abundance or expression comparisons.</p><table><tr><th>Gene</th><th>Raw count sum</th></tr>'+rows+'</table>'
    body += '<p>AnnData and SpatialData round trips preserve IDs, coordinates, status and raw counts. '
    body += 'The SpatialData store includes the image pyramid and an unreviewed image-footprint polygon.</p>'
    body += '<p><a href="spots.csv">Spot context table</a> · <a href="report.json">Checks and provenance</a> · '
    body += '<a href="'+html.escape(manifest['paper_url'])+'">Source study</a></p><p>'+html.escape(manifest['terms'])+'</p></html>'
    (root/'report.html').write_text(body, encoding='utf-8')
    return {k: report[k] for k in ('sample', 'observation_status_counts', 'gene_sums', 'anndata_roundtrip',
                                  'spatialdata_roundtrip', 'elapsed_seconds', 'sampled_peak_rss_bytes')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='datasets/examples/kasmani-day3-young.json')
    parser.add_argument('--cache', default='validation/runtime-cache/kasmani/GSM6108348')
    parser.add_argument('--output', required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    print(json.dumps(replay(args.manifest, args.cache, args.output, args.download), indent=2))
