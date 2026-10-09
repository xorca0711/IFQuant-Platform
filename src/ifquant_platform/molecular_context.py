"""Exact-ID attachment of processed molecular observations with explicit missingness."""
from __future__ import annotations

from collections import Counter

from .canonical import canonical_sha256, file_sha256, load_strict_json
from .imaging import require, write_json
from .spatial import csv_rows, exact_id, file_record, validate_assay, verify_file


def attach_context(assay_path, calls_path, output):
    assay = validate_assay(load_strict_json(assay_path))
    source = file_record(calls_path)
    ids = {r['observation_id'] for r in assay['observations']}
    calls, targets = {}, set()
    columns = ['observation_id', 'modality', 'target_id', 'status', 'value', 'coverage']
    for row in csv_rows(calls_path, columns, 500_000):
        oid, modality, target = row['observation_id'], row['modality'], row['target_id']
        require(oid in ids, 'molecular context contains an unknown observation ID; no fuzzy joins')
        require(modality in ('transcript_genotype', 'tcr'), 'only processed transcript genotype/TCR supported')
        exact_id(target, 'molecular target')
        key = (oid, modality, target)
        require(key not in calls, 'duplicate molecular observation/target')
        targets.add((modality, target))
        status = row['status']
        require(status in ('measured', 'not_assayed', 'failed', 'ambiguous'), 'invalid molecular status')
        coverage = None
        if row['coverage']:
            require(row['coverage'].isascii() and row['coverage'].isdigit(), 'coverage must be an integer')
            coverage = int(row['coverage'])
            require(coverage <= 2**53 - 1, 'coverage exceeds safe integer range')
        if status == 'measured':
            exact_id(row['value'], 'measured molecular value')
            require(coverage is not None and coverage > 0, 'measured call requires positive observed coverage')
            if modality == 'transcript_genotype':
                require(row['value'] in ('alternate_detected', 'reference_only', 'mixed'),
                        'invalid transcript genotype; do not substitute DNA genotype labels')
        else:
            require(row['value'] == '', 'unresolved molecular status cannot carry a definitive value')
            if status == 'not_assayed':
                require(coverage is None, 'unassayed molecular targets cannot claim coverage')
        calls[key] = {'observation_id': oid, 'modality': modality, 'target_id': target,
                      'status': status, 'value': row['value'] or None, 'coverage': coverage}
    require(bool(targets), 'at least one declared molecular target required')
    require(len(ids)*len(targets) <= 1_000_000, 'molecular output expansion exceeds engineering limit')
    rows = []
    for observation in assay['observations']:
        for modality, target in sorted(targets):
            oid = observation['observation_id']
            rows.append(calls.get((oid, modality, target), {
                'observation_id': oid, 'modality': modality, 'target_id': target,
                'status': 'not_reported', 'value': None, 'coverage': None}))
    verify_file(source)
    doc = {'schema_version': 'ifquant.molecular-context/1', 'assay_sha256': canonical_sha256(assay),
           'entity_type': assay['entity_type'], 'input': source,
           'targets': [{'modality': m, 'target_id': t} for m, t in sorted(targets)], 'observations': rows,
           'status_counts': [{'status': key, 'count': value} for key, value in sorted(Counter(r['status'] for r in rows).items())],
           'join_semantics': 'exact observation ID within one assay; no coordinate-nearest or cross-section cell matching',
           'interpretation': 'RNA reference-only is not DNA wild type; clonotype presence does not establish antigen specificity',
           'scientific_validation': False, 'producer_sha256': file_sha256(__file__)}
    write_json(output, doc)
    return {'output': str(output), 'observations': len(ids), 'targets': len(targets),
            'status_counts': doc['status_counts'], 'scientific_validation': False}
