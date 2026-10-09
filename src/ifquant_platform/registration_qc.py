"""Portable VALIS point-result intake and independent landmark QC.

The adapter consumes full-resolution forward points, never a pickled registrar
or an undocumented affine approximation to a nonrigid transformation.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import keys, number, require, validate_source, write_json
from .spatial import csv_rows, exact_id, file_record


def export_valis_points(moving_slide, fixed_slide, input_csv, output, *, non_rigid=True):
    """Call on live trusted VALIS Slide objects; all input/output pixels are level 0.

    Input includes observation, fit, independent evaluation, and rectangular probe
    points. No registrar pickle is loaded by IFQuant.
    """
    import numpy as np
    require(type(non_rigid) is bool, 'non_rigid must be boolean')
    columns = ['point_id', 'role', 'source_x', 'source_y', 'target_x', 'target_y']
    record = file_record(input_csv)
    rows = list(csv_rows(input_csv, columns, 200_000))
    require(rows, 'VALIS point input is empty')
    xy = np.array([[float(r['source_x']), float(r['source_y'])] for r in rows])
    require(np.isfinite(xy).all(), 'nonfinite VALIS input')
    warped = np.asarray(moving_slide.warp_xy_from_to(xy, fixed_slide, src_slide_level=0,
                        src_pt_level=0, dst_slide_level=0, non_rigid=non_rigid))
    require(warped.shape == xy.shape and np.isfinite(warped).all(), 'invalid VALIS point result')
    require(file_record(input_csv) == record, 'VALIS input changed during warp')
    with Path(output).open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns[:4]+['warped_x', 'warped_y']+columns[4:])
        for row, point in zip(rows, warped):
            writer.writerow([row[c] for c in columns[:4]]+point.tolist()+[row[c] for c in columns[4:]])
    return {'input': record, 'output': file_record(output), 'frame': 'moving_level0_pixels_to_fixed_level0_pixels', 'non_rigid': non_rigid}


def evaluate_registration(config_path, output):
    import numpy as np
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'moving_source', 'fixed_source', 'points_csv', 'points_sha256',
               'section_relation', 'method', 'method_version', 'run_reference', 'heldout_reference',
               'max_local_distance_um', 'probe_grid_xy'}, 'registration QC')
    require(cfg['schema_version'] == 'ifquant.registration-points/1', 'unsupported registration result')
    require(cfg['method'] in ('VALIS', 'synthetic'), 'explicit VALIS or synthetic result required')
    for key in ('method_version', 'run_reference', 'heldout_reference'):
        exact_id(cfg[key], key)
    number(cfg['max_local_distance_um'], 'local landmark support distance')
    base = Path(config_path).resolve().parent
    moving = validate_source(load_strict_json(base/cfg['moving_source']))
    fixed = validate_source(load_strict_json(base/cfg['fixed_source']))
    for key in ('subject_id', 'specimen_id', 'species'):
        require(moving['subject'][key] == fixed['subject'][key], 'registration subject/specimen mismatch')
    same = moving['subject']['section_id'] == fixed['subject']['section_id']
    require(cfg['section_relation'] in ('same_section', 'serial_section') and
            same == (cfg['section_relation'] == 'same_section'), 'registration section relation mismatch')
    path = base/cfg['points_csv']
    record = file_record(path)
    require(record['sha256'] == cfg['points_sha256'], 'registration point binding differs')
    columns = ['point_id', 'role', 'source_x', 'source_y', 'warped_x', 'warped_y', 'target_x', 'target_y']
    points, seen, landmark_origins = [], set(), set()
    errors = defaultdict(list)
    sx = fixed['grid']['pixel_size_x_um']/fixed['grid']['scale_x']
    sy = fixed['grid']['pixel_size_y_um']/fixed['grid']['scale_y']
    for row in csv_rows(path, columns, 200_000):
        pid = exact_id(row['point_id'], 'registration point ID')
        require(pid not in seen and row['role'] in ('observation', 'fit', 'evaluation', 'probe'), 'duplicate point ID or invalid role')
        seen.add(pid)
        values = {key: float(row[key]) if row[key] != '' else None for key in columns[2:]}
        require(all(v is None or math.isfinite(v) for v in values.values()), 'nonfinite registration point')
        require(all(values[k] is not None for k in columns[2:6]), 'source/warped coordinates required')
        require(0 <= values['source_x'] < moving['grid']['base_width'] and
                0 <= values['source_y'] < moving['grid']['base_height'], 'moving point outside source')
        if row['role'] in ('fit', 'evaluation'):
            xy = (values['source_x'], values['source_y'])
            require(xy not in landmark_origins, 'landmark reused across fit/evaluation')
            landmark_origins.add(xy)
            require(values['target_x'] is not None and values['target_y'] is not None and
                    0 <= values['target_x'] < fixed['grid']['base_width'] and
                    0 <= values['target_y'] < fixed['grid']['base_height'], 'heldout/fit target missing or out of bounds')
            values['error_um'] = math.hypot((values['warped_x']-values['target_x'])*sx,
                                           (values['warped_y']-values['target_y'])*sy)
            errors[row['role']].append(values['error_um'])
        else:
            require(values['target_x'] is None and values['target_y'] is None, 'non-landmark cannot carry reference target')
        values['outside_fixed_image'] = not (0 <= values['warped_x'] < fixed['grid']['base_width'] and
                                             0 <= values['warped_y'] < fixed['grid']['base_height'])
        points.append({'point_id': pid, 'role': row['role'], **values})
    require(bool(points), 'registration points cannot be empty')
    heldout = [p for p in points if p['role'] == 'evaluation']
    for point in points:
        if point['role'] != 'observation':
            continue
        distances = [(math.hypot((point['warped_x']-p['warped_x'])*sx,
                                (point['warped_y']-p['warped_y'])*sy), p) for p in heldout]
        distance, nearest = min(distances, key=lambda v: v[0]) if distances else (None, None)
        supported = distance is not None and distance <= cfg['max_local_distance_um']
        point['nearest_evaluation_distance_um'] = distance
        point['local_error_proxy_um'] = nearest['error_um'] if supported else None
        point['local_support'] = 'near_heldout_landmark' if supported else 'unsupported'
    probes = [p for p in points if p['role'] == 'probe']
    deformation = {'status': 'not_supplied', 'folded_triangles': None, 'minimum_area_ratio': None}
    grid = cfg['probe_grid_xy']
    if grid is not None:
        require(isinstance(grid, list) and len(grid) == 2 and all(type(v) is int and v >= 2 for v in grid), 'invalid probe grid')
        nx, ny = grid
        require(len(probes) == nx*ny, 'probe count differs from grid')
        probes.sort(key=lambda p: (p['source_y'], p['source_x']))
        source = np.array([[p['source_x'], p['source_y']] for p in probes]).reshape(ny, nx, 2)
        warped = np.array([[p['warped_x'], p['warped_y']] for p in probes]).reshape(ny, nx, 2)
        require(np.all(source[:, :, 0] == source[0, :, 0]) and np.all(source[:, :, 1] == source[:, 0, 1, None]) and
                np.all(np.diff(source[0, :, 0]) > 0) and np.all(np.diff(source[:, 0, 1]) > 0), 'probes must form an ordered rectangular grid')
        def area(a, b, c):
            u, v = b-a, c-a
            return u[0]*v[1]-u[1]*v[0]
        ratios = []
        for y in range(ny-1):
            for x in range(nx-1):
                for vertices in (((y, x), (y, x+1), (y+1, x+1)), ((y, x), (y+1, x+1), (y+1, x))):
                    ratios.append(float(area(*(warped[v] for v in vertices))/area(*(source[v] for v in vertices))))
        deformation = {'status': 'sampled', 'folded_triangles': sum(v <= 0 for v in ratios),
                       'minimum_area_ratio': min(ratios), 'maximum_area_ratio': max(ratios),
                       'interpretation': 'finite-grid orientation/area check; not a proof of global diffeomorphism'}
    else:
        require(not probes, 'probe grid dimensions required')
    summaries = {role: {'count': len(errors[role]), 'rmse_um': float(np.sqrt(np.mean(np.square(errors[role])))) if errors[role] else None,
                        'max_um': max(errors[role]) if errors[role] else None} for role in ('fit', 'evaluation')}
    require(file_record(path) == record, 'registration points changed during evaluation')
    write_json(output, {'schema_version': 'ifquant.registration-qc/1', 'plan': cfg, 'input': record,
        'moving_source_sha256': canonical_sha256(moving), 'fixed_source_sha256': canonical_sha256(fixed),
        'landmark_errors': summaries, 'deformation': deformation, 'points': points, 'scientific_validation': False,
        'interpretation': 'local landmark residuals are error proxies, not confidence bounds; serial sections do not establish cell identity'})
    return {'output': str(output), 'landmark_errors': summaries, 'deformation': deformation, 'scientific_validation': False}
