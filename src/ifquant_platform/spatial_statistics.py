"""Declared spatial mixing hypotheses, conditioned nulls and sensitivity.

The normalized mixing statistic follows the Slide-GoTags analysis definition.
Our nulls are specimen/region/coverage conditioned, use a finite-sample correction
and abstain for undefined or degenerate distributions. This is a documented
revision, not a claim to reproduce the authors' permutation implementation.
"""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import integer, keys, require, write_json
from .spatial import exact_id, file_record, validate_assay


def radius_edges(xy, radius, limit=2_000_000):
    from scipy.spatial import cKDTree
    tree = cKDTree(xy)
    n = (tree.count_neighbors(tree, radius)-len(xy))//2
    require(n <= limit, 'spatial edge capacity exceeded; reduce radius or partition the analysis')
    return tree.query_pairs(radius, output_type='ndarray')


def mixing(edges, labels, reference, target):
    import numpy as np
    ref, tar = labels == reference, labels == target
    nr, nt = int(ref.sum()), int(tar.sum())
    rr = int(np.sum(ref[edges[:, 0]] & ref[edges[:, 1]]))
    rt = int(np.sum((ref[edges[:, 0]] & tar[edges[:, 1]]) | (tar[edges[:, 0]] & ref[edges[:, 1]])))
    value = .5*(rt/rr)*(nr-1)/nt if rr and nr > 1 and nt else None
    return {'normalized_mixing_score': value, 'reference_reference_edges': rr,
            'reference_target_edges': rt, 'reference_count': nr, 'target_count': nt}


def bh_adjust(values):
    """Keep abstentions in the declared family conservatively as p=1."""
    order = sorted(range(len(values)), key=lambda i: 1 if values[i] is None else values[i])
    result, running = [None]*len(values), 1.0
    for rank in range(len(order), 0, -1):
        i = order[rank-1]
        running = min(running, (1 if values[i] is None else values[i])*len(order)/rank)
        if values[i] is not None:
            result[i] = running
    return result


def _labels(path, assay):
    ids = {o['observation_id'] for o in assay['observations']}
    result = {}
    columns = ['observation_id', 'specimen_id', 'region_id', 'coverage_stratum', 'label', 'boundary_distance']
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == columns, 'invalid spatial label columns')
        for row in reader:
            require(set(row) == set(columns) and all(v is not None for v in row.values()), 'malformed label row')
            oid = row['observation_id']
            require(oid in ids and oid not in result, 'unknown/duplicate spatial label observation')
            for key in columns[:-1]:
                exact_id(row[key], key)
            # This assay represents one declared specimen; never fabricate independent units.
            require(row['specimen_id'] == assay['subject']['specimen_id'], 'label specimen conflicts with assay')
            if row['boundary_distance'] != '':
                distance = float(row['boundary_distance'])
                require(math.isfinite(distance) and distance >= 0, 'invalid boundary distance')
                row['boundary_distance'] = distance
            else:
                row['boundary_distance'] = None
            result[oid] = row
    return result


def spatial_hypotheses(config_path, output):
    import numpy as np
    config = load_strict_json(config_path)
    keys(config, {'schema_version', 'assay', 'assay_sha256', 'labels_csv', 'labels_sha256',
                  'coordinate_unit', 'pairs', 'radii', 'permutations', 'seed', 'edge_policy',
                  'excluded_labels', 'jitter_sd', 'uncertainty_basis', 'sensitivity_repeats'}, 'spatial hypothesis plan')
    require(config['schema_version'] == 'ifquant.spatial-hypotheses/1', 'unsupported hypothesis plan')
    base = Path(config_path).resolve().parent
    assay = validate_assay(load_strict_json(base/config['assay']))
    require(canonical_sha256(assay) == config['assay_sha256'], 'hypothesis assay binding differs')
    label_path = base/config['labels_csv']
    label_record = file_record(label_path)
    require(label_record['sha256'] == config['labels_sha256'], 'hypothesis labels binding differs')
    require(config['coordinate_unit'] == assay['coordinate_frame']['unit'], 'radius unit differs from assay')
    radii = config['radii']
    require(isinstance(radii, list) and 0 < len(radii) <= 20 and len(set(radii)) == len(radii) and
            all(type(r) in (int, float) and math.isfinite(r) and r > 0 for r in radii), 'invalid radii')
    require(config['edge_policy'] in ('exclude_boundary_observations', 'conditional_on_observed_window'), 'explicit edge policy required')
    integer(config['seed'], 'seed', minimum=0)
    integer(config['permutations'], 'permutations', minimum=19)
    integer(config['sensitivity_repeats'], 'sensitivity repeats', minimum=1)
    require(config['permutations'] <= 9999 and config['sensitivity_repeats'] <= 100, 'resampling capacity exceeded')
    require(type(config['jitter_sd']) in (int, float) and math.isfinite(config['jitter_sd']) and config['jitter_sd'] >= 0,
            'invalid coordinate jitter')
    exact_id(config['uncertainty_basis'], 'uncertainty basis; distinguish measured from scenario')
    require(isinstance(config['excluded_labels'], list) and all(isinstance(v, str) and v for v in config['excluded_labels']),
            'excluded labels must be a list of names')
    require(isinstance(config['pairs'], list) and 0 < len(config['pairs']) <= 25, '1..25 pairs required')
    seen = set()
    for pair in config['pairs']:
        keys(pair, {'test_id', 'reference', 'target'}, 'hypothesis pair')
        for value in pair.values():
            exact_id(value, 'hypothesis label')
        require(pair['reference'] != pair['target'] and pair['test_id'] not in seen, 'identical labels or duplicate test ID')
        seen.add(pair['test_id'])
    labels = _labels(label_path, assay)
    groups, excluded = defaultdict(list), Counter()
    cutoff = max(radii) + 3*config['jitter_sd']
    for observation in assay['observations']:
        row = labels.get(observation['observation_id'])
        reason = ('rna_not_measured' if observation['assay_status'] != 'measured' else
                  'label_not_reported' if row is None else 'excluded_label' if row['label'] in config['excluded_labels'] else None)
        if reason:
            excluded[reason] += 1
            continue
        if config['edge_policy'] == 'exclude_boundary_observations':
            require(row['boundary_distance'] is not None, 'boundary distances required by edge policy')
            if row['boundary_distance'] < cutoff:
                excluded['boundary_exclusion'] += 1
                continue
        groups[(row['specimen_id'], row['region_id'])].append((observation, row))
    results, work = [], 0
    require(len(groups)*len(radii)*len(config['pairs'])*config['permutations'] <= 2_000_000,
            'hypothesis/null output capacity exceeded; reduce the declared test family')
    rng = np.random.default_rng(config['seed'])
    for (specimen, region), items in sorted(groups.items()):
        xy = np.array([[o['x'], o['y']] for o, _ in items], dtype=float)
        values = np.array([r['label'] for _, r in items], dtype=object)
        strata = defaultdict(list)
        for i, (_, row) in enumerate(items):
            strata[row['coverage_stratum']].append(i)
        for radius in radii:
            edges = radius_edges(xy, radius)
            work += len(edges)*len(config['pairs'])*(config['permutations']+config['sensitivity_repeats'])
            require(work <= 100_000_000, 'resampling edge-work capacity exceeded')
            nulls = [[] for _ in config['pairs']]
            for _ in range(config['permutations']):
                permuted = values.copy()
                for indices in strata.values():
                    permuted[indices] = rng.permutation(values[indices])
                for j, pair in enumerate(config['pairs']):
                    nulls[j].append(mixing(edges, permuted, pair['reference'], pair['target'])['normalized_mixing_score'])
            for pair, null in zip(config['pairs'], nulls):
                observed = mixing(edges, values, pair['reference'], pair['target'])
                score = observed['normalized_mixing_score']
                valid = [v for v in null if v is not None]
                status = ('undefined_observed' if score is None else 'undefined_null_draws' if len(valid) != len(null)
                          else 'degenerate_null' if np.std(valid) == 0 else 'estimated')
                mean = float(np.mean(valid)) if valid else None
                p = (1+sum(v >= score for v in valid))/(1+len(valid)) if status == 'estimated' else None
                sensitivity = []
                for _ in range(config['sensitivity_repeats']):
                    perturbed = xy+rng.normal(0, config['jitter_sd'], xy.shape)
                    value = mixing(radius_edges(perturbed, radius), values, pair['reference'], pair['target'])['normalized_mixing_score']
                    sensitivity.append(value)
                finite = [v for v in sensitivity if v is not None]
                results.append({'test_id': pair['test_id'], 'specimen_id': specimen, 'region_id': region,
                                'radius': radius, **observed, 'status': status, 'p_enrichment': p,
                                'null_mean': mean, 'effect_over_null_mean': score-mean if score is not None and mean is not None else None,
                                'null_valid_draws': len(valid), 'null_distribution': null,
                                'sensitivity_min': min(finite) if finite else None, 'sensitivity_max': max(finite) if finite else None,
                                'sensitivity_undefined': len(sensitivity)-len(finite)})
    require(bool(results), 'no eligible spatial hypothesis units')
    for row, q in zip(results, bh_adjust([r['p_enrichment'] for r in results])):
        row['q_bh_declared_family'] = q
    report = {'schema_version': 'ifquant.spatial-hypothesis-results/1', 'plan': config,
              'plan_sha256': canonical_sha256(config), 'labels_input': label_record, 'results': results,
              'excluded_observations': dict(excluded), 'scientific_validation': False,
              'interpretation': 'conditional within-specimen spatial association; no independent replication, signaling or antigen specificity',
              'sensitivity_semantics': 'scenario/measurement-based perturbation range, not a confidence interval',
              'null_method': 'shuffle labels within specimen, region and declared coverage stratum; +1 correction; abstain on undefined/zero-variance null'}
    require(file_record(label_path) == label_record, 'label input changed during analysis')
    write_json(output, report)
    return {'output': str(output), 'tests': len(results), 'status_counts': dict(Counter(r['status'] for r in results)),
            'scientific_validation': False}
