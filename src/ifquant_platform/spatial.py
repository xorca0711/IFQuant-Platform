"""Processed spatial assays and explicit affine links to tissue regions.

An engineering interchange boundary, not a deconvolution or registration model.
No heavy spatial-omics package is required by this initial adapter.
"""
from __future__ import annotations

import csv
import html
import math
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path

from .canonical import ContractError, canonical_sha256, file_sha256, load_strict_json
from .histology import validate_regions
from .imaging import identifier, keys, require, validate_source, write_json
from .phase3_validation import _parse_polygon_geometry

MAX_OBSERVATIONS = 200_000
MAX_FEATURES = 100_000
MAX_COUNT_ROWS = 1_000_000


def finite(value, label):
    require(type(value) in (int, float) and math.isfinite(value), f'{label}: finite number required')
    return float(value)


def exact_id(value, label):
    identifier(value, label)
    require(value == value.strip(), f'{label}: leading/trailing whitespace is forbidden')
    return value


def file_record(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': file_sha256(path), 'size_bytes': path.stat().st_size}


def verify_file(record):
    keys(record, {'path', 'sha256', 'size_bytes'}, 'spatial input file')
    require(Path(record['path']).is_absolute(), 'input path must be absolute')
    require(file_record(record['path']) == record, 'spatial input bytes changed')


def csv_rows(path, columns, limit):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == columns, f'CSV columns must be exactly {columns}')
        for i, row in enumerate(reader):
            require(i < limit, f'CSV exceeds {limit} row engineering limit')
            require(set(row) == set(columns) and all(v is not None for v in row.values()),
                    'CSV row has missing/extra values')
            yield row


def _observations(path):
    rows, seen = [], set()
    for row in csv_rows(path, ['observation_id', 'x', 'y', 'assay_status'], MAX_OBSERVATIONS):
        oid = exact_id(row['observation_id'], 'observation_id')
        require(oid not in seen, 'duplicate observation ID')
        seen.add(oid)
        require(row['assay_status'] in ('measured', 'not_assayed', 'failed', 'not_reported'), 'invalid RNA assay status')
        try:
            x, y = float(row['x']), float(row['y'])
        except ValueError as exc:
            raise ContractError('invalid spatial coordinate') from exc
        finite(x, 'x')
        finite(y, 'y')
        rows.append({'observation_id': oid, 'x': x, 'y': y, 'assay_status': row['assay_status']})
    require(bool(rows), 'observations cannot be empty')
    return rows


def _features(path):
    rows, seen = [], set()
    for row in csv_rows(path, ['feature_id', 'feature_name'], MAX_FEATURES):
        fid = exact_id(row['feature_id'], 'feature_id')
        require(fid not in seen, 'duplicate feature ID; names may be duplicated but IDs may not')
        seen.add(fid)
        identifier(row['feature_name'], 'feature name')
        rows.append(row)
    require(bool(rows), 'features cannot be empty')
    return rows


def count_rows(assay):
    """Sparse raw integer counts; absence is zero only for a measured observation."""
    observations = {r['observation_id']: r for r in assay['observations']}
    features = {r['feature_id'] for r in assay['features']}
    seen = set()
    for row in csv_rows(assay['inputs']['counts']['path'],
                        ['observation_id', 'feature_id', 'count'], MAX_COUNT_ROWS):
        oid, fid = row['observation_id'], row['feature_id']
        require(oid in observations and fid in features, 'count contains an unknown observation/feature ID')
        require(observations[oid]['assay_status'] == 'measured', 'counts on unassayed/failed observation')
        require((oid, fid) not in seen, 'duplicate count coordinate')
        seen.add((oid, fid))
        require(row['count'].isascii() and row['count'].isdigit(), 'count must be a nonnegative integer')
        value = int(row['count'])
        require(value <= 2**53 - 1, 'count exceeds safe integer range')
        yield oid, fid, value


def _assay_metadata(doc):
    keys(doc['subject'], {'subject_id', 'species', 'specimen_id', 'section_id'}, 'spatial subject')
    for value in doc['subject'].values():
        exact_id(value, 'subject field')
    exact_id(doc['assay_id'], 'assay id')
    require(doc['entity_type'] in ('spot', 'nucleus', 'cell'), 'explicit spot/nucleus/cell entity required')
    frame = doc['coordinate_frame']
    keys(frame, {'frame_id', 'unit', 'axes', 'origin', 'y_direction'}, 'coordinate frame')
    exact_id(frame['frame_id'], 'frame id')
    require(frame['unit'] in ('pixel', 'um') and frame['axes'] == ['x', 'y'] and
            frame['origin'] == 'top_left' and frame['y_direction'] == 'down',
            'use explicit XY, top-left, downward coordinates; convert other conventions upstream')


def _statistics(doc):
    totals = {r['observation_id']: 0 if r['assay_status'] == 'measured' else None
              for r in doc['observations']}
    nnz, rows = 0, 0
    for oid, _, count in count_rows(doc):
        rows += 1
        nnz += int(count > 0)
        totals[oid] += count
        require(totals[oid] <= 2**53 - 1, 'library count exceeds safe integer range')
    return {'count_rows': rows, 'nonzero_rows': nnz,
            'libraries': [{'observation_id': oid, 'total_counts': total} for oid, total in totals.items()]}


def import_assay(config_path, output):
    config = load_strict_json(config_path)
    keys(config, {'schema_version', 'assay_id', 'subject', 'entity_type', 'coordinate_frame',
                  'observations_csv', 'features_csv', 'counts_csv'}, 'spatial import config')
    require(config['schema_version'] == 'ifquant.spatial-import/1', 'unsupported spatial import')
    _assay_metadata(config)
    inputs = {key: file_record(Path(config_path).resolve().parent / config[key + '_csv'])
              for key in ('observations', 'features', 'counts')}
    doc = {key: config[key] for key in ('assay_id', 'subject', 'entity_type', 'coordinate_frame')}
    doc.update(schema_version='ifquant.spatial-assay/1', inputs=inputs,
               observations=_observations(inputs['observations']['path']),
               features=_features(inputs['features']['path']),
               matrix_semantics='raw_rna_counts_sparse_zero_for_measured_observations_only',
               scientific_validation=False)
    doc['statistics'] = _statistics(doc)
    validate_assay(doc)
    write_json(output, doc)
    return {'output': str(output), 'assay_sha256': canonical_sha256(doc),
            'observations': len(doc['observations']), 'features': len(doc['features'])}


def validate_assay(doc):
    keys(doc, {'schema_version', 'assay_id', 'subject', 'entity_type', 'coordinate_frame', 'inputs',
               'observations', 'features', 'statistics', 'matrix_semantics', 'scientific_validation'}, 'spatial assay')
    require(doc['schema_version'] == 'ifquant.spatial-assay/1' and doc['scientific_validation'] is False and
            doc['matrix_semantics'] == 'raw_rna_counts_sparse_zero_for_measured_observations_only',
            'unsupported assay or unauthorized claims')
    _assay_metadata(doc)
    keys(doc['inputs'], {'observations', 'features', 'counts'}, 'assay inputs')
    for record in doc['inputs'].values():
        verify_file(record)
    require(doc['observations'] == _observations(doc['inputs']['observations']['path']),
            'observation snapshot differs from source table')
    require(doc['features'] == _features(doc['inputs']['features']['path']), 'feature snapshot mismatch')
    require(doc['statistics'] == _statistics(doc), 'assay statistics mismatch')
    return doc


def apply_affine(matrix, point):
    x, y = point
    return [matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
            matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]]


def inverse_affine(matrix):
    a, b, tx = matrix[0]
    c, d, ty = matrix[1]
    determinant = a * d - b * c
    scale = max(abs(a), abs(b), abs(c), abs(d))
    require(scale > 0 and math.isfinite(determinant) and abs(determinant) > 1e-12 * scale**2,
            'singular or ill-conditioned affine matrix')
    return [[d / determinant, -b / determinant, (b * ty - d * tx) / determinant],
            [-c / determinant, a / determinant, (c * tx - a * ty) / determinant], [0, 0, 1]]


def validate_transform(doc, assay, source):
    keys(doc, {'schema_version', 'assay_sha256', 'source_sha256', 'from_frame', 'to_frame',
               'section_relation', 'matrix', 'method', 'landmarks'}, 'spatial transform')
    require(doc['schema_version'] == 'ifquant.affine-transform/1' and
            doc['assay_sha256'] == canonical_sha256(assay) and
            doc['source_sha256'] == canonical_sha256(source), 'transform input identity mismatch')
    require(doc['from_frame'] == assay['coordinate_frame']['frame_id'] and
            doc['to_frame'] == 'base_image_pixels' and doc['method'] == 'provided_affine',
            'transform frame/method mismatch')
    require(doc['section_relation'] in ('same_section', 'serial_section'), 'explicit section relation required')
    for key in ('subject_id', 'species', 'specimen_id'):
        require(assay['subject'][key] == source['subject'][key], 'cross-subject/specimen transform forbidden')
    same = assay['subject']['section_id'] == source['subject']['section_id']
    require(same == (doc['section_relation'] == 'same_section'), 'section relation contradicts identities')
    matrix = doc['matrix']
    require(isinstance(matrix, list) and len(matrix) == 3 and
            all(isinstance(r, list) and len(r) == 3 for r in matrix), '3x3 affine matrix required')
    for row in matrix:
        for value in row:
            finite(value, 'matrix coefficient')
    require(matrix[2] == [0, 0, 1], 'perspective transforms are unsupported')
    inverse_affine(matrix)
    require(isinstance(doc['landmarks'], list), 'landmark list required')
    ids, points, errors = set(), set(), {'fit': [], 'evaluation': []}
    sx = source['grid']['pixel_size_x_um'] / source['grid']['scale_x']
    sy = source['grid']['pixel_size_y_um'] / source['grid']['scale_y']
    for row in doc['landmarks']:
        keys(row, {'landmark_id', 'role', 'from', 'to'}, 'landmark')
        exact_id(row['landmark_id'], 'landmark id')
        require(row['landmark_id'] not in ids and row['role'] in errors, 'duplicate/invalid landmark')
        ids.add(row['landmark_id'])
        for key in ('from', 'to'):
            require(isinstance(row[key], list) and len(row[key]) == 2, 'landmark requires XY pair')
            for value in row[key]:
                finite(value, 'landmark coordinate')
        pair = tuple(row['from'])
        require(pair not in points, 'landmark reused across fit/evaluation or duplicated')
        points.add(pair)
        require(0 <= row['to'][0] <= source['grid']['base_width'] and
                0 <= row['to'][1] <= source['grid']['base_height'], 'target landmark outside image')
        x, y = apply_affine(matrix, row['from'])
        errors[row['role']].append(math.hypot((x-row['to'][0])*sx, (y-row['to'][1])*sy))
    return {role: {'count': len(values), 'rmse_um': math.sqrt(sum(v*v for v in values)/len(values)) if values else None,
                   'max_um': max(values) if values else None} for role, values in errors.items()}


def _point_relation(rings, x, y, sx, sy):
    """Even/odd polygon inclusion and nearest boundary distance in calibrated micrometers."""
    inside, distance = False, math.inf
    for ring in rings:
        points = [(float(a), float(b)) for a, b in ring]
        for (ax, ay), (bx, by) in pairwise(points):
            if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
                inside = not inside
            dx, dy = (bx-ax)*sx, (by-ay)*sy
            px, py = (x-ax)*sx, (y-ay)*sy
            length = dx*dx + dy*dy
            t = min(1, max(0, (px*dx+py*dy)/length)) if length else 0
            distance = min(distance, math.hypot(px-t*dx, py-t*dy))
    return inside, distance


def _link(assay, source, regions, transform, uncertainty_um):
    uncertainty_um = finite(uncertainty_um, 'boundary uncertainty')
    require(uncertainty_um >= 0, 'boundary uncertainty must be nonnegative')
    sx = source['grid']['pixel_size_x_um'] / source['grid']['scale_x']
    sy = source['grid']['pixel_size_y_um'] / source['grid']['scale_y']
    active = [r for r in regions['regions'] if r['role'] in ('reference', 'artifact') and r['review']['status'] != 'rejected']
    geometry = [(r, _parse_polygon_geometry('POLYGON', r['wkt'], 'region').polygons[0]) for r in active]
    require(len(active)*len(assay['observations']) <= 10_000_000, 'point-region comparison limit exceeded')
    require(sum(len(ring) for _, rings in geometry for ring in rings)*len(assay['observations']) <= 50_000_000,
            'point-edge comparison limit exceeded; subset regions or observations')
    rows = []
    for obs in assay['observations']:
        x, y = apply_affine(transform['matrix'], [obs['x'], obs['y']])
        finite(x, 'mapped x')
        finite(y, 'mapped y')
        candidates, artifact, boundary = [], False, False
        within = 0 <= x < source['grid']['base_width'] and 0 <= y < source['grid']['base_height']
        if within:
            for region, rings in geometry:
                inside, distance = _point_relation(rings, x, y, sx, sy)
                boundary |= distance <= max(uncertainty_um, 1e-9)
                if inside and region['role'] == 'artifact':
                    artifact = True
                elif inside and region['role'] == 'reference':
                    candidates.append(region)
        status = ('outside_image' if not within else 'artifact' if artifact else 'boundary_ambiguous' if boundary
                  else 'overlapping_references' if len(candidates) > 1 else 'outside_reference' if not candidates else 'linked')
        row = {'observation_id': obs['observation_id'], 'entity_type': assay['entity_type'],
               'assay_status': obs['assay_status'], 'x_base_px': x, 'y_base_px': y,
               'x_um': x*sx, 'y_um': y*sy, 'link_status': status,
               'region_id': candidates[0]['region_id'] if status == 'linked' else None,
               'reference_review': candidates[0]['review']['status'] if status == 'linked' else None}
        rows.append(row)
    return rows


def link_spatial(assay_path, source_path, regions_path, transform_path, output, *, uncertainty_um=0):
    assay = validate_assay(load_strict_json(assay_path))
    source = validate_source(load_strict_json(source_path))
    regions = validate_regions(load_strict_json(regions_path), source)
    transform = load_strict_json(transform_path)
    doc = build_links(assay, source, regions, transform, uncertainty_um)
    validate_source(source)
    for record in assay['inputs'].values():
        verify_file(record)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    write_json(root/'links.json', doc)
    (root/'links.csv').write_text(links_csv(doc), encoding='utf-8', newline='')
    (root/'report.html').write_text(links_html(doc), encoding='utf-8')
    return {'output': str(root), 'observations': len(doc['links']),
            'status_counts': doc['status_counts'], 'scientific_validation': False}


def build_links(assay, source, regions, transform, uncertainty_um):
    """Recompute all scientific fields from validated inputs, without publishing files."""
    errors = validate_transform(transform, assay, source)
    links = _link(assay, source, regions, transform, uncertainty_um)
    inverse = inverse_affine(transform['matrix'])
    roundtrip = max(math.dist([o['x'], o['y']], apply_affine(inverse, [r['x_base_px'], r['y_base_px']]))
                    for o, r in zip(assay['observations'], links))
    require(roundtrip <= 1e-7 * max(1, max(abs(o[k]) for o in assay['observations'] for k in ('x', 'y'))),
            'coordinate round trip exceeds numeric tolerance')
    counts = defaultdict(int)
    measured = Counter(r['region_id'] for r in links if r['link_status'] == 'linked' and r['assay_status'] == 'measured')
    index = {r['observation_id']: r for r in links}
    for oid, fid, count in count_rows(assay):
        row = index[oid]
        if row['link_status'] == 'linked':
            counts[(row['region_id'], fid)] += count
            require(counts[(row['region_id'], fid)] <= 2**53-1, 'region count exceeds safe integer range')
    # Include measured zero totals; an unmeasured region has no numerical aggregate.
    require(len(measured)*len(assay['features']) <= MAX_COUNT_ROWS, 'region-feature output limit exceeded')
    aggregates = [{'region_id': region, 'feature_id': feature['feature_id'],
                   'raw_count_sum': counts[(region, feature['feature_id'])], 'measured_observations': n}
                  for region, n in sorted(measured.items()) for feature in assay['features']]
    doc = {'schema_version': 'ifquant.spatial-links/1', 'assay_sha256': canonical_sha256(assay),
           'source_sha256': canonical_sha256(source), 'regions_sha256': canonical_sha256(regions),
           'transform': transform, 'landmark_errors': errors, 'boundary_uncertainty_um': uncertainty_um,
           'numeric_roundtrip_max_input_units': roundtrip, 'links': links, 'region_rna_counts': aggregates,
           'status_counts': dict(Counter(r['link_status'] for r in links)),
           'registration_status': 'evaluation_landmarks_supplied' if errors['evaluation']['count'] else 'not_evaluated',
           'assignment_semantics': 'point_center_to_region_only; no cell identity or spot-area deconvolution',
           'scientific_validation': False, 'producer_sha256': file_sha256(__file__)}
    return doc


def links_csv(doc):
    import io
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(doc['links'][0]))
    writer.writeheader()
    writer.writerows(doc['links'])
    return stream.getvalue()


def links_html(doc):
    body = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Spatial region links</title>'
    body += '<style>body{font:16px system-ui;max-width:1050px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap}</style>'
    body += '<h1>Spatial RNA and tissue regions</h1><p>Engineering associations of point centers with supplied regions. '
    body += 'No cell identity, lesion severity, or causal molecular phenotype is inferred. Serial sections do not identify the same cells.</p>'
    body += '<p>Registration: '+html.escape(doc['registration_status'])+'. Boundary uncertainty: '+str(doc['boundary_uncertainty_um'])+' µm.</p>'
    body += '<pre>'+html.escape(str(doc['status_counts']))+'</pre><p><a href="links.csv">Observation links</a> · '
    body += '<a href="links.json">Counts, landmarks and provenance</a></p></html>'
    return body
