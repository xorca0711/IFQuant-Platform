"""Within-stratum associations aggregated at an explicit biological-unit level."""
import math
from collections import defaultdict
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import integer, keys, require, write_json
from .spatial import csv_rows, exact_id, file_record
from .spatial_statistics import bh_adjust


def specimen_associations(config_path, output):
    import numpy as np
    from scipy.stats import rankdata
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'csv', 'x_endpoint', 'y_endpoint', 'aggregation', 'sampling_reference',
               'permutations', 'seed'}, 'association plan')
    require(cfg['schema_version'] == 'ifquant.specimen-associations/1' and cfg['aggregation'] == 'paired_unit_mean', 'explicit paired-unit mean aggregation required')
    for key in ('x_endpoint', 'y_endpoint', 'sampling_reference'):
        exact_id(cfg[key], key)
    integer(cfg['seed'], 'association seed', minimum=0)
    integer(cfg['permutations'], 'association permutations', minimum=19)
    require(cfg['permutations'] <= 9999, 'association permutation capacity exceeded')
    path = Path(config_path).resolve().parent/cfg['csv']
    record = file_record(path)
    groups, seen, strata, missing = defaultdict(list), set(), {}, 0
    for row in csv_rows(path, ['biological_unit_id', 'stratum', 'sampling_unit_id', 'x', 'y'], 100_000):
        uid, stratum, sid = [exact_id(row[k], k) for k in ('biological_unit_id', 'stratum', 'sampling_unit_id')]
        require(uid not in strata or strata[uid] == stratum, 'biological unit occurs in multiple strata; longitudinal/repeated-group design requires a separate model')
        strata[uid] = stratum
        require((uid, sid) not in seen, 'duplicate sampling unit')
        seen.add((uid, sid))
        require(all(row[k] == '' or math.isfinite(float(row[k])) for k in ('x', 'y')), 'nonfinite association measurement')
        if row['x'] == '' or row['y'] == '':
            missing += 1
            continue
        groups[stratum, uid].append([float(row['x']), float(row['y'])])
    aggregated, by_stratum = [], defaultdict(list)
    for (stratum, uid), rows in sorted(groups.items()):
        mean = np.mean(rows, axis=0)
        aggregated.append({'biological_unit_id': uid, 'stratum': stratum, 'paired_sampling_units': len(rows), 'mean_x': float(mean[0]), 'mean_y': float(mean[1])})
        by_stratum[stratum].append(mean)
    rng, results = np.random.default_rng(cfg['seed']), []
    for stratum in sorted(set(strata.values())):
        rows = by_stratum[stratum]
        status, rho, p = 'insufficient_biological_units', None, None
        if len(rows) >= 3:
            matrix = np.array(rows)
            a, b = rankdata(matrix[:, 0]), rankdata(matrix[:, 1])
            a -= a.mean(); b -= b.mean()
            norm = np.linalg.norm(a)*np.linalg.norm(b)
            status = 'constant_endpoint' if norm == 0 else 'estimated'
            if norm:
                rho = float(a @ b / norm)
                null = [float(a @ rng.permutation(b)/norm) for _ in range(cfg['permutations'])]
                p = (1+sum(abs(v) >= abs(rho)-1e-12 for v in null))/(len(null)+1)
        results.append({'stratum': stratum, 'biological_units': len(rows), 'status': status, 'spearman_rho': rho, 'p_two_sided': p})
    require(results, 'empty association input')
    for row, q in zip(results, bh_adjust([r['p_two_sided'] for r in results])):
        row['q_bh_declared_strata'] = q
    require(file_record(path) == record, 'association input changed during analysis')
    write_json(output, {'schema_version': 'ifquant.specimen-association-results/1', 'plan': cfg,
        'plan_sha256': canonical_sha256(cfg), 'input': record, 'aggregated_units': aggregated, 'results': results,
        'excluded_incomplete_sampling_units': missing, 'scientific_validation': False,
        'interpretation': 'within-stratum association of paired-unit means; biological-unit IDs require an externally verified sampling manifest; no causal interpretation'})
    return {'output': str(output), 'biological_units': len(aggregated), 'strata': len(results)}
