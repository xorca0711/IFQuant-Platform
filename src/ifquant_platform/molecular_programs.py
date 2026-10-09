"""Versioned measured-RNA program summaries with an explicit normalization basis."""
from __future__ import annotations

import csv
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import keys, require, write_json
from .spatial import exact_id, file_record, validate_assay
from .spatial_adapters import assay_to_anndata


def score_programs(config_path, output):
    import numpy as np
    from scipy import sparse
    config = load_strict_json(config_path)
    keys(config, {'schema_version', 'assay', 'programs', 'normalization_basis', 'library_totals_csv',
                  'min_library_counts', 'min_detected_features'}, 'RNA program config')
    require(config['schema_version'] == 'ifquant.rna-program-analysis/1', 'unsupported program analysis')
    require(config['normalization_basis'] in ('selected_features', 'external_full_library'), 'explicit normalization basis required')
    require(type(config['min_library_counts']) is int and config['min_library_counts'] >= 0 and
            type(config['min_detected_features']) is int and config['min_detected_features'] >= 0, 'invalid filtering threshold')
    base = Path(config_path).resolve().parent
    assay_path = base/config['assay']
    assay = validate_assay(load_strict_json(assay_path))
    data = assay_to_anndata(assay_path)
    registry_path = base/config['programs']
    registry = load_strict_json(registry_path)
    keys(registry, {'schema_version', 'registry_id', 'species', 'feature_id_namespace', 'programs'}, 'gene program registry')
    require(registry['schema_version'] == 'ifquant.gene-programs/1', 'unsupported gene registry')
    require(registry['species'] == assay['subject']['species'], 'gene registry species mismatch')
    exact_id(registry['registry_id'], 'registry ID')
    exact_id(registry['feature_id_namespace'], 'feature namespace; no automatic conversion')
    require(isinstance(registry['programs'], list) and 0 < len(registry['programs']) <= 100, '1..100 programs required')
    indices = {fid: i for i, fid in enumerate(data.var_names)}
    available, names, coverage = [], set(), []
    for program in registry['programs']:
        keys(program, {'program_id', 'feature_ids', 'reference', 'min_coverage_fraction', 'interpretation'}, 'gene program')
        exact_id(program['program_id'], 'program ID')
        require(program['program_id'] not in names, 'duplicate gene program')
        names.add(program['program_id'])
        for field in ('reference', 'interpretation'):
            exact_id(program[field], field)
        genes = program['feature_ids']
        require(isinstance(genes, list) and genes and len(genes) == len(set(genes)), 'unique nonempty program genes required')
        for gene in genes:
            exact_id(gene, 'program gene')
        threshold = program['min_coverage_fraction']
        require(type(threshold) in (float, int) and 0 < threshold <= 1, 'invalid program coverage threshold')
        found = [indices[g] for g in genes if g in indices]
        fraction = len(found)/len(genes)
        available.append(found if fraction >= threshold and found else None)
        coverage.append({'program_id': program['program_id'], 'available_genes': len(found),
                         'total_genes': len(genes), 'fraction': fraction,
                         'missing_feature_ids': [g for g in genes if g not in indices],
                         'status': 'eligible' if available[-1] else 'insufficient_gene_coverage'})
    matrix = data.X.astype(float).tocsr()
    matrix.eliminate_zeros()
    selected_totals = np.asarray(matrix.sum(axis=1)).ravel()
    libraries, external = selected_totals.copy(), None
    if config['normalization_basis'] == 'external_full_library':
        require(config['library_totals_csv'] is not None, 'full-library totals required')
        path = base/config['library_totals_csv']
        external = file_record(path)
        records = {}
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == ['observation_id', 'total_counts'], 'invalid full-library table')
            for row in reader:
                oid = row['observation_id']
                require(oid in data.obs_names and oid not in records, 'unknown/duplicate full-library observation')
                require(row['total_counts'].isascii() and row['total_counts'].isdigit(), 'integer library total required')
                records[oid] = int(row['total_counts'])
        require(set(records) == set(data.obs_names), 'complete full-library table required')
        libraries = np.array([records[oid] for oid in data.obs_names], dtype=float)
        require(np.isfinite(libraries).all() and np.all(libraries <= 2**53-1) and
                np.all(libraries >= selected_totals), 'full library cannot be smaller than selected counts')
    else:
        require(config['library_totals_csv'] is None, 'selected-feature normalization cannot carry full-library input')
    factors = np.divide(10000., libraries, out=np.zeros_like(libraries), where=libraries > 0)
    normalized = sparse.diags(factors) @ matrix
    normalized.data = np.log1p(normalized.data)
    detected = np.diff(matrix.indptr)
    scores = [np.asarray(normalized[:, found].mean(axis=1)).ravel() if found else None for found in available]
    rows = []
    for i, observation in enumerate(assay['observations']):
        reason = ('rna_not_measured' if observation['assay_status'] != 'measured' else 'zero_library' if libraries[i] == 0 else
                  'low_library' if libraries[i] < config['min_library_counts'] else
                  'low_detected_features' if detected[i] < config['min_detected_features'] else None)
        for program, cov, values in zip(registry['programs'], coverage, scores):
            rows.append({'observation_id': observation['observation_id'], 'program_id': program['program_id'],
                         'status': reason or cov['status'],
                         'mean_log1p_cp10k': None if reason or values is None else float(values[i])})
    report = {'schema_version': 'ifquant.rna-program-results/1', 'assay_sha256': canonical_sha256(assay),
              'plan': config, 'registry': registry, 'registry_input': file_record(registry_path),
              'external_library_input': external, 'coverage': coverage, 'observations': rows,
              'normalization': 'log1p(10000 * raw_count / explicitly declared library total)',
              'scientific_validation': False,
              'interpretation': 'measured RNA summary; selected-feature totals are panel-relative, not whole-transcriptome normalization; no cell type or lineage inference'}
    write_json(output, report)
    return {'output': str(output), 'programs': len(coverage), 'observations': data.n_obs,
            'eligible_programs': sum(v is not None for v in available), 'scientific_validation': False}
