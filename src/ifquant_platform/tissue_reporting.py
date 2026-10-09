"""Explicit ordinal review, specimen pooling, and within-image cell neighborhoods.

Reports are descriptive candidates. They cannot approve methods or infer lineage.
"""
from __future__ import annotations

import csv
import html
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .canonical import (
    ContractError,
    canonical_sha256,
    file_sha256,
    load_strict_json,
    parse_strict_json,
)
from .imaging import identifier, integer, keys, number, require, write_json
from .tissue_workflow import validate_histology


def validate_rubric(doc):
    keys(doc, {'schema_version', 'rubric_id', 'description', 'reference', 'endpoints'}, 'rubric')
    require(doc['schema_version'] == 'ifquant.ordinal-rubric/1', 'unsupported rubric')
    for name in ('rubric_id', 'description', 'reference'):
        identifier(doc[name], name)
    require(isinstance(doc['endpoints'], list) and bool(doc['endpoints']), 'endpoints required')
    ids = set()
    for item in doc['endpoints']:
        keys(item, {'endpoint_id', 'anatomies', 'levels'}, 'ordinal endpoint')
        identifier(item['endpoint_id'], 'endpoint id')
        require(item['endpoint_id'] not in ids, 'duplicate endpoint')
        ids.add(item['endpoint_id'])
        from .histology import ANATOMY
        require(isinstance(item['anatomies'], list) and bool(item['anatomies']) and
                len(set(item['anatomies'])) == len(item['anatomies']) and
                set(item['anatomies']) <= ANATOMY, 'invalid endpoint anatomy')
        require(isinstance(item['levels'], list) and len(item['levels']) >= 2, 'ordinal levels required')
        scores = []
        for level in item['levels']:
            keys(level, {'score', 'label', 'definition'}, 'ordinal level')
            integer(level['score'], 'ordinal score', minimum=0)
            identifier(level['label'], 'ordinal label')
            identifier(level['definition'], 'ordinal definition')
            scores.append(level['score'])
        require(scores == sorted(set(scores)), 'ordinal scores must be unique and increasing')
    return doc


def review_template(package_path, rubric_path, output):
    root = Path(package_path)
    validated = validate_histology(root)
    rubric = validate_rubric(load_strict_json(rubric_path))
    regions = load_strict_json(root / 'measurements.json')['regions']
    rows = [{'region_id': r['region_id'], 'endpoint_id': e['endpoint_id'], 'status': 'pending',
             'score': None, 'reviewer': None, 'at': None, 'reason': ''}
            for r in regions for e in rubric['endpoints'] if r['anatomy'] in e['anatomies']]
    require(bool(rows), 'no rubric endpoints apply to this package')
    form = {'schema_version': 'ifquant.ordinal-review/1',
            'package_sha256': validated['package_sha256'], 'rubric': rubric, 'rows': rows}
    write_json(output, form)
    return {'output': str(output), 'pending': len(rows)}


def validate_review(form, package_hash, regions):
    keys(form, {'schema_version', 'package_sha256', 'rubric', 'rows'}, 'ordinal review')
    require(form['schema_version'] == 'ifquant.ordinal-review/1' and
            form['package_sha256'] == package_hash, 'review package mismatch')
    rubric = validate_rubric(form['rubric'])
    expected = {(r['region_id'], e['endpoint_id']): e
                for r in regions for e in rubric['endpoints'] if r['anatomy'] in e['anatomies']}
    require(isinstance(form['rows'], list), 'review rows must be a list')
    seen = set()
    for row in form['rows']:
        keys(row, {'region_id', 'endpoint_id', 'status', 'score', 'reviewer', 'at', 'reason'}, 'review row')
        pair = (row['region_id'], row['endpoint_id'])
        require(pair in expected and pair not in seen, 'unexpected/duplicate review row')
        seen.add(pair)
        require(row['status'] in ('pending', 'accepted', 'uncertain', 'not_applicable'), 'invalid status')
        if row['status'] == 'accepted':
            integer(row['score'], 'score', minimum=0)
            require(row['score'] in [v['score'] for v in expected[pair]['levels']], 'score outside rubric')
        else:
            require(row['score'] is None, 'unaccepted review cannot carry a score')
        require(isinstance(row['reason'], str), 'review reason must be text')
        if row['status'] == 'pending':
            require(row['reviewer'] is row['at'] is None, 'pending row cannot claim a reviewer/time')
        else:
            identifier(row['reviewer'], 'reviewer')
            identifier(row['reason'], 'review reason')
            require(isinstance(row['at'], str) and row['at'].endswith('Z'), 'UTC review time required')
            try:
                datetime.fromisoformat(row['at'])
            except ValueError as exc:
                raise ContractError('invalid review timestamp') from exc
    require(seen == set(expected), 'review form is incomplete; retain pending rows explicitly')
    return form


def _write_report(root, title, body):
    (root / 'report.html').write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>' + html.escape(title) +
        '</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere}table{border-collapse:collapse}'
        'td,th{padding:8px;border:1px solid #ccc}</style><h1>' + html.escape(title) + '</h1>' +
        '<p>Descriptive engineering output; scientific accuracy is not established.</p>' + body +
        '<p><a href="summary.json">Full summary and provenance</a></p></html>', encoding='utf-8')


def specimen_report(packages, output, *, reviews=()):
    """Pool eligible physical areas within a method, anatomy, and reference-review stratum."""
    require(bool(packages), 'at least one package required')
    forms = {}
    for path in reviews:
        form = load_strict_json(path)
        require(form['package_sha256'] not in forms, 'multiple review forms for one package')
        forms[form['package_sha256']] = form
    groups, sections, seen, rubrics = {}, [], set(), {}
    for path in packages:
        root = Path(path)
        result = validate_histology(root)
        package = load_strict_json(root / 'package.json')
        source = load_strict_json(root / 'source.json')
        rows = load_strict_json(root / 'measurements.json')['regions']
        identity = source['subject']
        unit = tuple(identity[k] for k in ('species', 'subject_id', 'specimen_id', 'section_id'))
        require(unit not in seen, 'duplicate section: choose one run per biological section')
        seen.add(unit)
        form = forms.pop(result['package_sha256'], None)
        if form:
            validate_review(form, result['package_sha256'], rows)
            rubrics[canonical_sha256(form['rubric'])] = form['rubric']
        method = {'model_sha256': package['binding']['model_sha256'],
                  'dense_candidate_classes': package['binding']['dense_candidate_classes'],
                  'analysis_pixel_size_um': [source['grid']['pixel_size_x_um'],
                                             source['grid']['pixel_size_y_um']]}
        # Tile size is intentionally absent: pixel-local outputs must be tile invariant.
        for row in rows:
            section_row = {'subject': identity, 'package_sha256': result['package_sha256'],
                           'method': method, **row,
                           'ordinal_review': [r for r in form['rows'] if r['region_id'] == row['region_id']]
                           if form else None,
                           'rubric_sha256': canonical_sha256(form['rubric']) if form else None,
                           'review_sha256': canonical_sha256(form) if form else None}
            sections.append(section_row)
            key = canonical_sha256({'specimen': unit[:3], 'method': method,
                                    'anatomy': row['anatomy'], 'review': row['reference_review']})
            if key not in groups:
                groups[key] = {'subject': {k: identity[k] for k in identity if k != 'section_id'},
                               'method': method, 'anatomy': row['anatomy'],
                               'reference_review': row['reference_review'], 'section_ids': set(),
                               'eligible_reference_area_um2': 0, 'tissue_material_area_um2': 0,
                               'dense_candidate_area_um2': 0 if method['dense_candidate_classes'] else None,
                               'airspace_candidate_area_um2': 0, 'ordinal': {}, 'review_absent_regions': 0}
            group = groups[key]
            group['section_ids'].add(identity['section_id'])
            for name in ('eligible_reference_area_um2', 'tissue_material_area_um2', 'dense_candidate_area_um2'):
                if row[name] is not None:
                    group[name] += row[name]
            group['airspace_candidate_area_um2'] += row['eligible_reference_area_um2'] - row['tissue_material_area_um2']
            if form is None:
                group['review_absent_regions'] += 1
            else:
                for review in section_row['ordinal_review']:
                    ordinal_key = section_row['rubric_sha256'] + ':' + review['endpoint_id']
                    counts = group['ordinal'].setdefault(ordinal_key, {'accepted_score_counts': {},
                                                                     'status_counts': {}})
                    counts['status_counts'][review['status']] = counts['status_counts'].get(review['status'], 0) + 1
                    if review['status'] == 'accepted':
                        score = str(review['score'])
                        counts['accepted_score_counts'][score] = counts['accepted_score_counts'].get(score, 0) + 1
    require(not forms, 'review form does not match a supplied package')
    for group in groups.values():
        group['section_ids'] = sorted(group['section_ids'])
        tissue, eligible = group['tissue_material_area_um2'], group['eligible_reference_area_um2']
        dense = group['dense_candidate_area_um2']
        group['dense_candidate_fraction_of_tissue'] = dense / tissue if dense is not None and tissue else None
        group['airspace_candidate_fraction'] = group['airspace_candidate_area_um2'] / eligible if eligible and group['anatomy'] == 'alveolar_parenchyma' else None
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    summary = {'schema_version': 'ifquant.specimen-report/1', 'scientific_validation': False,
               'reporter_sha256': file_sha256(__file__), 'rubrics': rubrics,
               'aggregation': 'pooled_eligible_area_across_supplied_sections_within_method_anatomy_review',
               'sampling_inference': 'supplied regions only; not unbiased whole-lung burden or volume',
               'ordinal_aggregation': 'counts only; no arithmetic average or composite grade',
               'sections': sections, 'specimens': list(groups.values())}
    write_json(root / 'summary.json', summary)
    columns = ['species', 'subject_id', 'specimen_id', 'anatomy', 'reference_review',
               'section_count', 'eligible_reference_area_um2', 'tissue_material_area_um2',
               'dense_candidate_fraction_of_tissue', 'airspace_candidate_fraction']
    with (root / 'specimens.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for group in groups.values():
            flat = {**group, **group['subject'], 'section_count': len(group['section_ids'])}
            writer.writerow({k: flat[k] for k in columns})
    _write_report(root, 'IFQuant specimen report',
                  '<p>Area fractions pool eligible numerators and denominators across supplied sections. '
                  'Different methods, anatomy, or reference review states remain separate. Sections and '
                  'regions are subsamples, not independent subjects. Ordinal scores are retained as counts.</p>'
                  '<p><a href="specimens.csv">Specimen measurements CSV</a></p><pre>' +
                  html.escape(str(summary['specimens'])) + '</pre>')
    return {'output': str(root), 'sections': len(seen), 'specimen_strata': len(groups),
            'scientific_validation': False}


def radius_neighbors(points, groups, radius, *, max_comparisons=2_000_000):
    """Exact radius neighbors using spatial bins; never crosses supplied ROI groups."""
    number(radius, 'radius_um')
    require(len(points) == len(groups), 'point/group count mismatch')
    require(all(len(p) == 2 and all(math.isfinite(v) for v in p) for p in points), 'invalid coordinates')
    bins = defaultdict(list)
    neighbors = [[] for _ in points]
    comparisons = 0
    for i, ((x, y), group) in enumerate(zip(points, groups)):
        bx, by = math.floor(x / radius), math.floor(y / radius)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in bins[(group, bx + dx, by + dy)]:
                    comparisons += 1
                    require(comparisons <= max_comparisons, 'dense neighborhood exceeds comparison limit; reduce radius')
                    px, py = points[j]
                    if (x - px)**2 + (y - py)**2 <= radius**2:
                        neighbors[i].append(j)
                        neighbors[j].append(i)
        bins[(group, bx, by)].append(i)
    return neighbors


def cell_report(package_path, output, *, radius_um=25, thresholds_path=None):
    from .package_validation import validate_cell_package

    root = Path(package_path)
    package_file = root / 'package.json' if root.is_dir() else root
    validated = validate_cell_package(package_file)
    package = load_strict_json(package_file)
    threshold_doc = load_strict_json(thresholds_path) if thresholds_path else {
        'schema_version': 'ifquant.marker-thresholds/1', 'thresholds': []}
    keys(threshold_doc, {'schema_version', 'thresholds'}, 'thresholds')
    require(threshold_doc['schema_version'] == 'ifquant.marker-thresholds/1', 'invalid threshold schema')
    names = set()
    for rule in threshold_doc['thresholds']:
        keys(rule, {'name', 'measurement_id', 'unit', 'minimum_inclusive'}, 'marker rule')
        for key in ('name', 'measurement_id', 'unit'):
            identifier(rule[key], key)
        require(rule['name'] not in names, 'duplicate marker rule')
        names.add(rule['name'])
        number(rule['minimum_inclusive'], 'threshold', positive=False)
    objects = []
    with (package_file.parent / package['cell_objects_artifact']['relative_path']).open('rb') as stream:
        for line in stream:
            obj = parse_strict_json(line)
            objects.append(obj)
    number(radius_um, 'radius_um')
    require(len(objects) <= 500000, 'cell report limit is 500,000 objects; use separate ROI packages')
    cal = package['pixel_calibration']
    points, groups, rows = [], [], []
    for obj in objects:
        xy = (obj['centroids']['cell_x'] * cal['pixel_width_um'],
              obj['centroids']['cell_y'] * cal['pixel_height_um'])
        eligible = obj['qc']['status'] != 'fail' and obj['review']['state'] != 'rejected'
        measurements = {m['measurement_id']: m for m in obj['intensity_measurements']}
        phenotype = {}
        for rule in threshold_doc['thresholds']:
            measurement = measurements.get(rule['measurement_id'])
            require(measurement is None or measurement['unit'] == rule['unit'], 'threshold unit mismatch')
            phenotype[rule['name']] = None if measurement is None else measurement['value'] >= rule['minimum_inclusive']
        rows.append({'object_id': obj['object_id'], 'annotation_id': obj['annotation_id'],
                     'x_um': xy[0], 'y_um': xy[1], 'analysis_included': eligible,
                     'qc': obj['qc'], 'review': obj['review'], 'marker_phenotype': phenotype,
                     'morphology_measurements': obj['morphology_measurements'],
                     'intensity_measurements': obj['intensity_measurements']})
        if eligible:
            points.append(xy)
            groups.append(obj['annotation_id'])
    included = [r for r in rows if r['analysis_included']]
    neighbors = radius_neighbors(points, groups, radius_um)
    for row, adjacent in zip(included, neighbors):
        row['neighbor_count'] = len(adjacent)
        row['neighbor_marker_positive_counts'] = {
            name: sum(included[j]['marker_phenotype'][name] is True for j in adjacent) for name in names}
        row['neighbor_marker_measured_counts'] = {
            name: sum(included[j]['marker_phenotype'][name] is not None for j in adjacent) for name in names}
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    from .canonical import canonical_json_bytes
    with (out / 'cells.jsonl').open('wb') as stream:
        for row in rows:
            stream.write(canonical_json_bytes(row) + b'\n')
    summary = {'schema_version': 'ifquant.cell-report/1', 'scientific_validation': False,
               'reporter_sha256': file_sha256(__file__),
               'package_sha256': validated.package_canonical_sha256,
               'biological_unit': package['biological_unit'], 'thresholds': threshold_doc,
               'radius_um': radius_um, 'object_count': len(rows), 'included_count': len(included),
               'exclusion_rule': 'QC fail or review rejected; other objects remain engineering candidates',
               'neighborhood_scope': 'same image and supplied annotation only; edge effects uncorrected',
               'phenotype_meaning': 'user-thresholded measured signal; no lineage or functional state inference',
               'marker_counts': {name: {'positive': sum(r['marker_phenotype'][name] is True for r in included),
                                         'measured': sum(r['marker_phenotype'][name] is not None for r in included)}
                                 for name in sorted(names)},
               'qc_status_counts': dict(Counter(r['qc']['status'] for r in rows))}
    write_json(out / 'summary.json', summary)
    with (out / 'cells.csv').open('w', newline='', encoding='utf-8') as stream:
        columns = ['object_id', 'annotation_id', 'x_um', 'y_um', 'analysis_included', 'neighbor_count']
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({k: row.get(k) for k in columns} for row in rows)
    _write_report(out, 'IFQuant cell and neighborhood report', '<p>Neighbors use calibrated cell centroids '
                  'within the same supplied ROI. Counts exclude the cell itself. QC failures and rejected '
                  'objects are excluded; remaining cells retain their QC and review state. Unmeasured '
                  'markers stay missing. No edge correction or spatial enrichment test is applied.</p>'
                  '<p><a href="cells.csv">Cell CSV</a> · <a href="cells.jsonl">Features and marker states</a></p>'
                  '<pre>' + html.escape(str(summary)) + '</pre>')
    return {'output': str(out), 'objects': len(rows), 'included': len(included), 'scientific_validation': False}
