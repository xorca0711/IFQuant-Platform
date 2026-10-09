"""Explicit processed MC38-OVA Slide-GoTags annotation adapter.

Published status columns are retained separately. Without observed read coverage,
an author status is not promoted to a measured IFQuant transcript-genotype call.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import keys, require, write_json
from .molecular_context import attach_context
from .spatial import exact_id, file_record, validate_assay


def import_gotags(config_path, output):
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'assay', 'annotations_csv', 'id_column', 'source_reference',
               'nanopore_value_map', 'nanopore_coverage_column', 'tcr_column', 'tcr_coverage_column'}, 'Slide-GoTags config')
    require(cfg['schema_version'] == 'ifquant.slide-gotags-mc38-ova/1', 'unsupported Slide-GoTags source profile')
    exact_id(cfg['source_reference'], 'source reference')
    mapping = cfg['nanopore_value_map']
    require(isinstance(mapping, dict) and mapping and all(isinstance(k, str) and k for k in mapping) and
            set(mapping.values()) <= {'alternate_detected', 'reference_only', 'mixed'}, 'explicit author-status mapping required')
    base = Path(config_path).resolve().parent
    assay_path = base/cfg['assay']
    assay = validate_assay(load_strict_json(assay_path))
    require(assay['entity_type'] in ('nucleus', 'cell'), 'Slide-GoTags source profile requires cell/nucleus IDs')
    path = base/cfg['annotations_csv']
    record = file_record(path)
    ids = {o['observation_id'] for o in assay['observations']}
    retained, calls, seen = [], [], set()
    expression, nanopore = 'SIINFEKL_WPRE_status', 'SIINFEKL_WPRE_nanopore_status'
    required = [cfg['id_column'], expression, nanopore]
    for key in ('nanopore_coverage_column', 'tcr_column', 'tcr_coverage_column'):
        if cfg[key] is not None:
            exact_id(cfg[key], key)
            required.append(cfg[key])
    require(cfg['tcr_column'] is not None or cfg['tcr_coverage_column'] is None, 'TCR coverage without TCR column')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames) and
                set(required) <= set(reader.fieldnames), 'source profile columns missing/duplicated')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'malformed GoTags source row')
            oid = exact_id(row[cfg['id_column']], 'GoTags observation ID')
            require(oid in ids and oid not in seen, 'unknown/duplicate GoTags observation; exact ID join required')
            seen.add(oid)
            retained.append({'observation_id': oid, 'expression_status': row[expression], 'nanopore_status': row[nanopore]})
            for modality, target, column, coverage_column in (
                ('transcript_genotype', 'SIINFEKL_WPRE', nanopore, cfg['nanopore_coverage_column']),
                ('tcr', 'clonotype', cfg['tcr_column'], cfg['tcr_coverage_column'])):
                if column is None:
                    continue
                raw = row[column]
                missing = raw in ('', 'NA', 'NaN')
                require(missing or modality == 'tcr' or raw in mapping, 'unmapped author nanopore status')
                coverage = row[coverage_column] if coverage_column is not None else ''
                require(coverage == '' or (coverage.isascii() and coverage.isdigit() and int(coverage) <= 2**53-1), 'invalid GoTags coverage')
                measured = not missing and coverage != '' and int(coverage) > 0
                value = (mapping[raw] if modality == 'transcript_genotype' else exact_id(raw, 'clonotype')) if measured else ''
                calls.append([oid, modality, target, 'measured' if measured else 'ambiguous', value, coverage])
    require(retained and file_record(path) == record, 'empty or changed GoTags source')
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    calls_path = destination/'molecular.csv'
    with calls_path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['observation_id', 'modality', 'target_id', 'status', 'value', 'coverage'])
        writer.writerows(calls)
    attach_context(assay_path, calls_path, destination/'context.json')
    report = {'schema_version': 'ifquant.slide-gotags-import-report/1', 'plan': cfg, 'input': record,
        'assay_sha256': canonical_sha256(assay), 'author_annotations': retained,
        'unreported_observations': sorted(ids-seen), 'call_status_counts': dict(Counter(r[3] for r in calls)),
        'scientific_validation': False, 'interpretation': 'author expression status retained separately; absent coverage remains ambiguous; RNA reference-only is not DNA wild type'}
    write_json(destination/'report.json', report)
    return {'output': str(destination), 'reported_observations': len(retained), 'unreported_observations': len(ids-seen),
            'call_status_counts': report['call_status_counts']}
