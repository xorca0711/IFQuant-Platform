"""Frozen broad-feature public replay; no reference labels or biological acceptance."""
import argparse
import csv
from pathlib import Path

from replay_lung_example import acquire

from ifquant_platform.canonical import file_sha256, load_strict_json
from ifquant_platform.imaging import require, write_json
from ifquant_platform.molecular_programs import score_programs
from ifquant_platform.spatial import count_rows
from ifquant_platform.spatial_adapters import import_native
from ifquant_platform.spatial_domains import domain_baselines


def select_features(matrix, names, ids, required, count, minimum, excluded):
    import numpy as np
    from scipy import sparse
    totals = np.asarray(matrix.sum(axis=1)).ravel()
    require((totals > 0).all(), 'zero source library')
    normalized = sparse.diags(10000/totals) @ matrix.astype(float)
    normalized.data = np.log1p(normalized.data)
    variance = np.asarray(normalized.power(2).mean(axis=0)).ravel()-np.asarray(normalized.mean(axis=0)).ravel()**2
    detected = np.asarray((matrix > 0).sum(axis=0)).ravel()
    candidates = [i for i, name in enumerate(names) if detected[i] >= minimum and
                  not any(name.startswith(prefix) for prefix in excluded)]
    require(len(candidates) >= count and set(required) <= set(ids), 'missing features for frozen selection')
    chosen = sorted(candidates, key=lambda i: (-variance[i], ids[i]))[:count]
    chosen += [ids.index(fid) for fid in required if ids.index(fid) not in chosen]
    return chosen, totals


def replay(plan_path, cache, output, download=False):
    import h5py
    import numpy as np
    from scipy import sparse
    plan_path = Path(plan_path).resolve()
    cfg = load_strict_json(plan_path)
    manifest = load_strict_json(plan_path.parent/cfg['source_manifest'])
    registry_path = (plan_path.parent/cfg['program_registry']).resolve()
    registry = load_strict_json(registry_path)
    required = sorted({fid for p in registry['programs'] for fid in p['feature_ids']})
    files = acquire(manifest, Path(cache).resolve(), download)
    prefix = manifest['sample']+'_Day3_Young_'
    source = files[prefix+'filtered_feature_bc_matrix.h5']
    with h5py.File(source) as handle:
        g = handle['matrix']
        ids, names, barcodes = (list(g[k].asstr()[:]) for k in ('features/id', 'features/name', 'barcodes'))
        matrix = sparse.csc_matrix((g['data'][:], g['indices'][:], g['indptr'][:]), shape=tuple(g['shape'][:])).T.tocsr()
    selected, totals = select_features(matrix, names, ids, required, cfg['variable_features'],
                                      cfg['minimum_detected_spots'], cfg['exclude_prefixes'])
    chosen_ids = [ids[i] for i in selected]
    require(matrix[:, selected].nnz <= 1_000_000, 'selected panel exceeds interchange capacity')
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root/'selection.json', {'plan': cfg, 'plan_sha256': file_sha256(plan_path),
        'source_sha256': file_sha256(source), 'registry_sha256': file_sha256(registry_path),
        'features': [{'feature_id': ids[i], 'feature_name': names[i]} for i in selected]})
    subject = {'subject_id': manifest['sample']+'-library-proxy', 'species': 'Mus musculus',
        'specimen_id': manifest['sample'], 'section_id': manifest['sample']+'-deposited-section'}
    native = {'schema_version': 'ifquant.native-spatial-import/1', 'assay_id': manifest['sample']+'-broad-panel',
        'subject': subject, 'entity_type': 'spot', 'format': 'visium_h5',
        'coordinate_frame': {'frame_id': manifest['sample']+'-hires-pixels', 'unit': 'pixel',
                            'axes': ['x', 'y'], 'origin': 'top_left', 'y_direction': 'down'},
        'inputs': {'matrix_h5': str(source), 'positions': str(files[prefix+'tissue_positions_list.csv.gz']),
                   'scalefactors': str(files[prefix+'scalefactors_json.json.gz'])},
        'options': {'positions_profile': 'legacy_headerless', 'matrix_scope': 'filtered', 'target_image': 'hires',
                    'feature_ids': chosen_ids}}
    write_json(root/'native-plan.json', native)
    import_native(root/'native-plan.json', root/'native')
    assay = load_strict_json(root/'native/assay.json')
    observed = dict.fromkeys(chosen_ids, 0)
    for _, fid, count in count_rows(assay):
        observed[fid] += count
    expected = dict(zip(chosen_ids, map(int, np.asarray(matrix[:, selected].sum(axis=0)).ravel())))
    require(observed == expected, 'source raw totals differ from imported panel')
    libraries = dict(zip(barcodes, map(int, totals)))
    with (root/'full-library.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['observation_id', 'total_counts'])
        writer.writerows((o['observation_id'], libraries.get(o['observation_id'], 0)) for o in assay['observations'])
    write_json(root/'program-plan.json', {'schema_version': 'ifquant.rna-program-analysis/1',
        'assay': 'native/assay.json', 'programs': str(registry_path), 'normalization_basis': 'external_full_library',
        'library_totals_csv': 'full-library.csv', 'min_library_counts': 1, 'min_detected_features': 1})
    score_programs(root/'program-plan.json', root/'program-results.json')
    write_json(root/'domain-plan.json', {'schema_version': 'ifquant.domain-baselines/2',
        'assay': 'native/assay.json', 'normalization_basis': 'external_full_library',
        'library_totals_csv': 'full-library.csv', 'minimum_features': 100, 'minimum_library': 1,
        'coordinate_unit': 'pixel', **cfg['domains']})
    domain_baselines(root/'domain-plan.json', root/'domain-results.json')
    report = {'schema_version': 'ifquant.public-rna-evidence/1', 'source_sample': manifest['sample'],
        'plan_sha256': file_sha256(plan_path), 'source_sha256': file_sha256(source),
        'selected_features': len(selected), 'selected_nonzero_counts': matrix[:, selected].nnz,
        'measured_observations': len(barcodes), 'positions': len(assay['observations']),
        'source_total_counts': int(totals.sum()), 'selected_total_counts': sum(observed.values()),
        'all_selected_gene_totals_reconciled': True, 'scientific_validation': False,
        'scope': cfg['scope'], 'artifacts': {name: file_sha256(root/name) for name in
            ('selection.json', 'program-results.json', 'domain-results.json', 'full-library.csv')}}
    write_json(root/'evidence.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', default='datasets/examples/lung-rna-development.json')
    parser.add_argument('--cache', default='validation/runtime-cache/kasmani/GSM6108348')
    parser.add_argument('--output', required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    print(replay(args.plan, args.cache, args.output, args.download))
