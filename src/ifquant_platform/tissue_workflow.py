"""Resumable H&E candidate runs, immutable review inputs and inspectable reports."""
from __future__ import annotations

import csv
import html
import importlib.metadata
import math
import os
import platform
import time
from pathlib import Path

from .canonical import canonical_sha256, file_sha256, load_strict_json
from .histology import (
    assign,
    default_profile,
    export_geojson,
    features,
    fit_model,
    region_mask,
    validate_model,
    validate_regions,
)
from .imaging import (
    iter_tiles,
    keys,
    open_source,
    register_image,
    require,
    tile_plan,
    validate_source,
    write_json,
)

REPORT_COLUMNS = ['region_id', 'anatomy', 'reference_review', 'eligible_reference_area_um2',
                  'tissue_material_area_um2', 'dense_candidate_fraction_of_tissue',
                  'airspace_candidate_fraction', 'annotated_lesion_fraction_of_tissue']


def _peak_memory_bytes():
    """Process high-water resident memory, including earlier work in this process."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        class MemoryCounters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]

        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        query = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        if query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.PeakWorkingSetSize
        return None
    import resource
    import sys
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == 'darwin' else peak * 1024


def producer_identity():
    modules = ('canonical.py', 'imaging.py', 'histology.py', 'tissue_workflow.py',
               'phase3_validation.py', 'package_validation.py')
    return {'python': platform.python_version(), 'platform': platform.platform(),
            'code': {name: file_sha256(Path(__file__).parent / name) for name in modules},
            'dependencies': {name: importlib.metadata.version(name)
                             for name in ('numpy', 'Pillow', 'tifffile', 'zarr')}}


def _active(regions, role):
    return [r for r in regions['regions'] if r['role'] == role and
            r['review']['status'] != 'rejected']


def _masks(source, regions, core):
    import numpy as np

    shape = (core[3], core[2])
    owner = np.zeros(shape, dtype=np.int32)
    reference = _active(regions, 'reference')
    for i, region in enumerate(reference, 1):
        mask = region_mask(region, source, core)
        require(not np.any(mask & (owner > 0)), 'reference regions overlap on the analysis grid')
        owner[mask] = i
    artifact = np.zeros(shape, dtype=bool)
    lesion = np.zeros(shape, dtype=bool)
    for region in _active(regions, 'artifact'):
        artifact |= region_mask(region, source, core)
    for region in _active(regions, 'lesion'):
        if region['review']['status'] == 'accepted':
            lesion |= region_mask(region, source, core)
    return owner, artifact, lesion


def _counts(labels, owner, lesion, regions, class_count):
    import numpy as np

    rows = []
    for i, region in enumerate(_active(regions, 'reference'), 1):
        selected = owner == i
        counts = np.bincount(labels[selected], minlength=class_count + 3).tolist()
        require(counts[0] == 0, 'reference pixels cannot be unassigned')
        rows.append({'region_id': region['region_id'], 'reference_pixels': int(selected.sum()),
                     'artifact_pixels': counts[2], 'airspace_candidate_pixels': counts[1],
                     'tissue_pixels': sum(counts[3:]), 'class_pixels': counts[3:],
                     'reviewed_lesion_tissue_pixels': int((selected & lesion & (labels >= 3)).sum())})
    return rows


def _save_array(path, labels):
    import numpy as np

    partial = path.with_name(path.name + '.partial')
    with partial.open('wb') as stream:
        np.save(stream, labels, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(partial, path)


def _overlay(rgb, labels):
    import numpy as np

    palette = np.asarray([[40, 40, 40], [225, 245, 255], [255, 180, 0]] +
                         [[(37 + i * 71) % 256, (130 + i * 97) % 256, (230 + i * 43) % 256]
                          for i in range(16)], dtype=np.uint8)
    overlay = ((rgb.astype(float) * 0.6 + palette[labels] * 0.4).clip(0, 255)).astype('uint8')
    overlay[labels == 2] = palette[2]
    return overlay


def _verify_tile(root, tile, source, regions, model):
    import numpy as np

    path = root / 'tiles' / (tile['tile_id'] + '.json')
    record = load_strict_json(path)
    keys(record, {'tile', 'mask_sha256', 'overlay_sha256', 'measurements'}, 'tile record')
    require(record['tile'] == tile, 'tile coordinates/ownership changed')
    mask_path = path.with_suffix('.npy')
    require(file_sha256(mask_path) == record['mask_sha256'] and
            file_sha256(path.with_suffix('.png')) == record['overlay_sha256'], 'tile artifact changed')
    labels = np.load(mask_path, allow_pickle=False)
    require(labels.dtype == np.uint8 and labels.shape == (tile['core'][3], tile['core'][2]) and
            labels.max(initial=0) < len(model['centers']) + 3, 'invalid tile mask')
    owner, artifact, lesion = _masks(source, regions, tile['core'])
    require(np.array_equal(labels == 0, owner == 0), 'mask reference space mismatch')
    require(np.array_equal(labels == 2, artifact & (owner > 0)), 'artifact mask mismatch')
    require(_counts(labels, owner, lesion, regions, len(model['centers'])) == record['measurements'],
            'mask counts do not reconcile')
    return record


def _summaries(root, source, regions, model, plan, dense_classes):
    reference = _active(regions, 'reference')
    totals = {r['region_id']: {'reference_pixels': 0, 'artifact_pixels': 0,
                              'airspace_candidate_pixels': 0, 'tissue_pixels': 0,
                              'class_pixels': [0] * len(model['centers']),
                              'reviewed_lesion_tissue_pixels': 0} for r in reference}
    for tile in iter_tiles(plan):
        record = _verify_tile(root, tile, source, regions, model)
        for row in record['measurements']:
            target = totals[row['region_id']]
            for key in target:
                if key == 'class_pixels':
                    target[key] = [a + b for a, b in zip(target[key], row[key])]
                else:
                    target[key] += row[key]
    area = source['grid']['pixel_size_x_um'] * source['grid']['pixel_size_y_um']
    results = []
    for region in reference:
        raw = totals[region['region_id']]
        eligible = raw['reference_pixels'] - raw['artifact_pixels']
        require(eligible == raw['tissue_pixels'] + raw['airspace_candidate_pixels'],
                'denominator reconciliation failed')
        dense = sum(raw['class_pixels'][model['class_names'].index(c)] for c in dense_classes)
        lesion_review_present = bool([r for r in _active(regions, 'lesion')
                                      if r['review']['status'] == 'accepted'])
        results.append({'region_id': region['region_id'], 'anatomy': region['anatomy'],
                        'reference_review': region['review']['status'], **raw,
                        'eligible_reference_area_um2': eligible * area,
                        'tissue_material_area_um2': raw['tissue_pixels'] * area,
                        'dense_candidate_area_um2': dense * area if dense_classes else None,
                        'dense_candidate_fraction_of_tissue': dense / raw['tissue_pixels']
                        if dense_classes and raw['tissue_pixels'] else None,
                        'airspace_candidate_fraction': raw['airspace_candidate_pixels'] / eligible
                        if region['anatomy'] == 'alveolar_parenchyma' and eligible else None,
                        'annotated_lesion_fraction_of_tissue':
                        raw['reviewed_lesion_tissue_pixels'] / raw['tissue_pixels']
                        if lesion_review_present and region['review']['status'] == 'accepted' and
                        raw['tissue_pixels'] else None,
                        'severity_score': None,
                        'scientific_validation': False})
    return results


def _report(root, summary, source, model):
    from PIL import Image

    columns = REPORT_COLUMNS
    with (root / 'measurements.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({k: row[k] for k in columns} for row in summary)
    g = source['grid']
    ratio = min(1, 1536 / max(g['width'], g['height']))
    overview = Image.new('RGB', (max(1, math.ceil(g['width'] * ratio)),
                                 max(1, math.ceil(g['height'] * ratio))), 'white')
    for tile in iter_tiles(load_strict_json(root / 'tile-plan.json')):
        x, y, w, h = tile['core']
        left, top = round(x * ratio), round(y * ratio)
        right, bottom = round((x + w) * ratio), round((y + h) * ratio)
        if right > left and bottom > top:
            with Image.open(root / 'tiles' / (tile['tile_id'] + '.png')) as image:
                overview.paste(image.resize((right - left, bottom - top)), (left, top))
    overview.save(root / 'overview.png')
    esc = lambda value: html.escape(str(value))
    legend = ' '.join('<span style="display:inline-block;margin:6px"><i style="display:inline-block;'
                     f'width:14px;height:14px;background:rgb({(37 + i * 71) % 256},'
                     f'{(130 + i * 97) % 256},{(230 + i * 43) % 256})"></i> {esc(name)}</span>'
                     for i, name in enumerate(model['class_names']))
    rows = ''.join('<tr>' + ''.join('<td>' + esc(row[k] if row[k] is not None else 'Not evaluated')
                                  + '</td>' for k in columns) + '</tr>' for row in summary)
    body = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>IFQuant H&amp;E region report</title><style>
body{{font:16px system-ui;margin:2rem auto;max-width:1200px;padding:0 1rem;color:#183044}}
img{{max-width:100%}}table{{border-collapse:collapse;font-size:13px}}td,th{{padding:8px;border:1px solid #cad4dd}}
.scroll{{overflow:auto}}.note{{background:#fff3ce;padding:1rem}}code{{overflow-wrap:anywhere}}
</style><h1>H&amp;E region report</h1>
<p>Specimen: {esc(source['subject']['specimen_id'])}; section: {esc(source['subject']['section_id'])}</p>
<p class="note">Engineering candidate measurements. Scientific accuracy and pathology severity are not established.
Missing values remain unevaluated. Colors identify appearance clusters, not injury grades.
White-looking regions are airspace candidates only inside a declared alveolar reference region.</p>
<img src="overview.png" alt="Downsampled overview of candidate cluster and artifact overlays">
<p>Full-resolution tiles and region annotations are retained in this package.
<a href="regions.geojson">QuPath region annotations</a> · <a href="measurements.csv">Measurements CSV</a></p>
<p>{legend}</p><p>Class colors blend with native pixels. Solid orange marks supplied artifact exclusions.</p>
<div class="scroll"><table><thead><tr>{''.join('<th>'+esc(k)+'</th>' for k in columns)}</tr></thead>
<tbody>{rows}</tbody></table></div>
<p>Reference area includes tissue material and airspace candidates, after artifact exclusion.
Tissue-denominated fractions use tissue material only. Annotated lesion fractions describe supplied accepted
lesion polygons; annotation completeness is not established. Region masks and review status define interpretation.</p>
<p>Model identity: <code>{canonical_sha256(model)}</code></p></html>'''
    (root / 'report.html').write_text(body, encoding='utf-8')


def run_histology(source_path, model_path, regions_path, output, *, tile_size=512,
                  dense_classes=(), resume=False, max_tiles=None):
    import numpy as np
    from PIL import Image

    start = time.monotonic()
    require(type(tile_size) is int and 0 < tile_size <= 512,
            'H&E working-memory limit requires tile_size between 1 and 512')
    source = validate_source(load_strict_json(source_path))
    model = validate_model(load_strict_json(model_path))
    regions = validate_regions(load_strict_json(regions_path), source)
    require(source['modality'] == 'he', 'H&E source required')
    require(len(set(dense_classes)) == len(dense_classes) and
            set(dense_classes) <= set(model['class_names']), 'invalid dense candidate class selection')
    require(max_tiles is None or type(max_tiles) is int and max_tiles > 0, 'max_tiles must be positive')
    plan = tile_plan(source, tile_size=tile_size)
    binding = {'source_sha256': canonical_sha256(source), 'model_sha256': canonical_sha256(model),
               'regions_sha256': canonical_sha256(regions), 'plan_sha256': canonical_sha256(plan),
               'dense_candidate_classes': list(dense_classes), 'producer': producer_identity()}
    root = Path(output).resolve()
    if resume:
        state = load_strict_json(root / 'run-state.json')
        require(state['binding'] == binding, 'resume inputs, code or environment changed')
        require(not (root / 'package.json').exists(), 'completed package cannot be resumed/overwritten')
    else:
        root.mkdir(parents=True, exist_ok=False)
    lock = root / 'run.lock'
    with lock.open('x', encoding='ascii') as stream:
        stream.write(str(os.getpid()))
    done = 0
    try:
        if not resume:
            (root / 'tiles').mkdir()
            for filename, data in [('source.json', source), ('model.json', model),
                                   ('regions.json', regions), ('tile-plan.json', plan)]:
                write_json(root / filename, data)
            write_json(root / 'regions.geojson', export_geojson(source, regions))
        state = {'schema_version': 'ifquant.histology-run-state/1', 'binding': binding,
                 'status': 'running', 'completed_tiles': 0, 'error': None}
        write_json(root / 'run-state.json', state, replace=True)
        with open_source(source) as image:
            for tile in iter_tiles(plan):
                record_path = root / 'tiles' / (tile['tile_id'] + '.json')
                if record_path.exists():
                    _verify_tile(root, tile, source, regions, model)
                else:
                    rgb = image.read(*tile['core'])
                    lab, _, tissue = features(rgb, model['profile'])
                    owner, artifacts, lesions = _masks(source, regions, tile['core'])
                    labels = assign(lab[..., 1:3], model['centers']).astype(np.uint8) + 3
                    labels[~tissue] = 1
                    labels[artifacts] = 2
                    labels[owner == 0] = 0
                    _save_array(record_path.with_suffix('.npy'), labels)
                    temporary = record_path.with_suffix('.png.partial')
                    Image.fromarray(_overlay(rgb, labels)).save(temporary, format='PNG')
                    os.replace(temporary, record_path.with_suffix('.png'))
                    record = {'tile': tile, 'mask_sha256': file_sha256(record_path.with_suffix('.npy')),
                              'overlay_sha256': file_sha256(record_path.with_suffix('.png')),
                              'measurements': _counts(labels, owner, lesions, regions, len(model['centers']))}
                    write_json(record_path, record)
                done += 1
                state.update(completed_tiles=done)
                write_json(root / 'run-state.json', state, replace=True)
                if max_tiles is not None and done >= max_tiles:
                    state['status'] = 'paused'
                    write_json(root / 'run-state.json', state, replace=True)
                    return {'status': 'paused', 'completed_tiles': done, 'output': str(root)}
        validate_source(source)
        validate_regions(regions, source)
        summary = _summaries(root, source, regions, model, plan, dense_classes)
        # These derived files may exist after an interrupted finalization; regenerate from verified tiles.
        write_json(root / 'measurements.json', {'regions': summary}, replace=True)
        _report(root, summary, source, model)
        elapsed = time.monotonic() - start
        write_json(root / 'runtime.json', {'schema_version': 'ifquant.run-metrics/1',
                   'invocation_elapsed_seconds': elapsed, 'total_verified_tiles': done,
                   'verified_tiles_per_second': done / elapsed,
                   'process_peak_resident_bytes': _peak_memory_bytes(),
                   'scope': 'process high-water memory; resume elapsed covers only this invocation'},
                   replace=True)
        state.update(status='complete', elapsed_seconds=time.monotonic() - start)
        write_json(root / 'run-state.json', state, replace=True)
        files = [{'path': p.relative_to(root).as_posix(), 'sha256': file_sha256(p)}
                 for p in sorted(root.rglob('*')) if p.is_file() and
                 p.name not in ('run.lock', 'run-state.json', 'package.json') and
                 not p.name.endswith('.partial')]
        package = {'schema_version': 'ifquant.histology-package/1', 'binding': binding,
                   'files': files, 'completed_tiles': done,
                   'status': 'engineering_complete', 'scientific_validation': False,
                   'severity_authorized': False}
        write_json(root / 'package.json', package)
        return {'status': 'engineering_complete', 'output': str(root), 'tiles': done,
                'regions': len(summary), 'scientific_validation': False,
                'package_sha256': canonical_sha256(package)}
    except BaseException as exc:
        if not (root / 'package.json').exists():
            write_json(root / 'run-state.json', {'schema_version': 'ifquant.histology-run-state/1',
                       'binding': binding, 'status': 'cancelled' if isinstance(exc, KeyboardInterrupt)
                       else 'failed', 'completed_tiles': done, 'error': str(exc)}, replace=True)
        raise
    finally:
        lock.unlink(missing_ok=True)


def validate_histology(output):
    root = Path(output).resolve()
    package = load_strict_json(root / 'package.json')
    keys(package, {'schema_version', 'binding', 'files', 'completed_tiles', 'status',
                   'scientific_validation', 'severity_authorized'}, 'histology package')
    require(package['schema_version'] == 'ifquant.histology-package/1' and
            package['status'] == 'engineering_complete' and
            package['scientific_validation'] is package['severity_authorized'] is False,
            'unsupported package or unauthorized claims')
    files = set()
    for artifact in package['files']:
        keys(artifact, {'path', 'sha256'}, 'artifact')
        path = (root / artifact['path']).resolve()
        require(path.is_relative_to(root) and artifact['path'] not in files, 'unsafe/duplicate artifact')
        require(file_sha256(path) == artifact['sha256'], f'changed artifact: {artifact["path"]}')
        files.add(artifact['path'])
    require({'source.json', 'model.json', 'regions.json', 'tile-plan.json', 'measurements.json',
             'report.html', 'overview.png', 'measurements.csv', 'regions.geojson', 'runtime.json'} <= files,
            'missing required artifacts')
    source = validate_source(load_strict_json(root / 'source.json'))
    model = validate_model(load_strict_json(root / 'model.json'))
    regions = validate_regions(load_strict_json(root / 'regions.json'), source)
    plan = load_strict_json(root / 'tile-plan.json')
    binding = package['binding']
    keys(binding, {'source_sha256', 'model_sha256', 'regions_sha256', 'plan_sha256',
                   'dense_candidate_classes', 'producer'}, 'run binding')
    producer = binding['producer']
    keys(producer, {'python', 'platform', 'code', 'dependencies'}, 'producer')
    keys(producer['code'], {'canonical.py', 'imaging.py', 'histology.py', 'tissue_workflow.py',
                            'phase3_validation.py', 'package_validation.py'}, 'producer code')
    keys(producer['dependencies'], {'numpy', 'Pillow', 'tifffile', 'zarr'}, 'producer dependencies')
    require(all(isinstance(v, str) and len(v) == 64 and all(c in '0123456789abcdef' for c in v)
                for v in producer['code'].values()), 'invalid producer hash')
    require(all(isinstance(v, str) and v.strip() for v in
                [producer['python'], producer['platform'], *producer['dependencies'].values()]),
            'invalid producer version')
    require(isinstance(binding['dense_candidate_classes'], list) and
            len(set(binding['dense_candidate_classes'])) == len(binding['dense_candidate_classes']) and
            set(binding['dense_candidate_classes']) <= set(model['class_names']), 'invalid dense classes')
    for name, doc in [('source', source), ('model', model), ('regions', regions), ('plan', plan)]:
        require(binding[name + '_sha256'] == canonical_sha256(doc), f'{name} identity mismatch')
    require(plan == tile_plan(source, tile_size=plan['tile_size']), 'plan differs from source coverage')
    count = 0
    for tile in iter_tiles(plan):
        prefix = 'tiles/' + tile['tile_id']
        require(all(prefix + ext in files for ext in ('.json', '.npy', '.png')), 'missing tile artifact')
        count += 1
    require(count == package['completed_tiles'], 'incomplete tile coverage')
    summary = _summaries(root, source, regions, model, plan, binding['dense_candidate_classes'])
    require(load_strict_json(root / 'measurements.json') == {'regions': summary}, 'summary mismatch')
    with (root / 'measurements.csv').open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        require(reader.fieldnames == REPORT_COLUMNS,
                'invalid measurement CSV fields')
        expected = [{k: '' if row[k] is None else str(row[k]) for k in reader.fieldnames}
                    for row in summary]
        require(rows == expected, 'measurement CSV differs from derived summary')
    require(load_strict_json(root / 'regions.geojson') == export_geojson(source, regions),
            'QuPath annotation export mismatch')
    return {'status': 'valid', 'tiles': count, 'regions': len(summary),
            'package_sha256': canonical_sha256(package), 'scientific_validation': False}


def demo_histology(output):
    """Entirely synthetic, documented fixture; no biological review is simulated."""
    import numpy as np
    import tifffile

    from .phase3_validation import _canonical_wkt

    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    yy, xx = np.indices((768, 1024))
    rgb = np.full((768, 1024, 3), 250, dtype=np.uint8)
    tissue = ((xx % 80 < 25) | (yy % 80 < 20))
    rgb[tissue] = [218, 159, 193]
    rgb[(xx > 530) & (yy > 230) & (yy < 640)] = [116, 66, 128]
    rgb[((xx - 280)**2 + (yy - 350)**2 < 100**2)] = [175, 105, 155]
    rgb[:20, :] = [20, 60, 160]
    tifffile.imwrite(root / 'synthetic-he.tif', rgb, photometric='rgb', tile=(128, 128))
    register_image(root / 'synthetic-he.tif', root / 'source.json', subject_id='synthetic-subject',
                   species='synthetic', specimen_id='synthetic-specimen', section_id='section-1',
                   pixel_size_x=0.5, pixel_size_y=0.5)
    source = load_strict_json(root / 'source.json')
    review = {'status': 'pending', 'reviewer': None, 'at': None,
              'reason': 'Synthetic geometry; no biological review'}
    region = lambda rid, role, wkt: {'region_id': rid, 'role': role,
                                    'anatomy': 'alveolar_parenchyma' if role == 'reference' else 'unresolved',
                                    'label': rid, 'wkt': _canonical_wkt('POLYGON', wkt, rid),
                                    'review': dict(review)}
    regions = {'schema_version': 'ifquant.regions/1', 'source_sha256': canonical_sha256(source),
               'coordinate_frame': 'base_image_pixels', 'parent': None,
               'regions': [region('synthetic-reference', 'reference',
                                  'POLYGON ((0 0, 1024 0, 1024 768, 0 768, 0 0))'),
                           region('synthetic-artifact', 'artifact',
                                  'POLYGON ((0 0, 1024 0, 1024 20, 0 20, 0 0))')]}
    write_json(root / 'regions.json', regions)
    write_json(root / 'profile.json', default_profile())
    fit_model(root / 'source.json', root / 'model.json', regions_path=root / 'regions.json', clusters=3)
    result = run_histology(root / 'source.json', root / 'model.json', root / 'regions.json', root / 'run')
    validate_histology(root / 'run')
    return result
