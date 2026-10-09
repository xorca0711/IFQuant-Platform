"""Bounded expression-only and graph-smoothed clustering baselines.

Cluster numbers are unlabeled exploratory groups, never cell types or injury
grades. Higher-complexity methods must be compared on the same declared inputs.
"""
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import integer, keys, number, require, write_json
from .spatial import validate_assay
from .spatial_adapters import assay_to_anndata
from .spatial_statistics import radius_edges


def domain_baselines(config_path, output):
    import numpy as np
    from scipy import sparse
    from scipy.cluster.vq import kmeans2
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'assay', 'normalization_basis', 'minimum_features', 'minimum_library',
               'components', 'clusters', 'seed', 'radius', 'coordinate_unit', 'smoothing_weight'}, 'domain plan')
    require(cfg['schema_version'] == 'ifquant.domain-baselines/1', 'unsupported domain plan')
    require(cfg['normalization_basis'] == 'selected_features', 'baseline uses explicitly selected-feature library totals')
    for key in ('minimum_features', 'components', 'clusters'):
        integer(cfg[key], key, minimum=2)
    for key in ('seed', 'minimum_library'):
        integer(cfg[key], key, minimum=0)
    number(cfg['radius'], 'domain radius')
    number(cfg['smoothing_weight'], 'smoothing weight', positive=False)
    require(cfg['smoothing_weight'] <= 1, 'smoothing weight exceeds 1')
    path = Path(config_path).resolve().parent/cfg['assay']
    assay = validate_assay(load_strict_json(path))
    require(cfg['coordinate_unit'] == assay['coordinate_frame']['unit'], 'domain coordinate units differ')
    data = assay_to_anndata(path)
    require(data.n_vars >= cfg['minimum_features'], 'insufficient features for the declared domain baseline')
    totals = np.asarray(data.X.sum(axis=1)).ravel()
    eligible = np.array([o['assay_status'] == 'measured' for o in assay['observations']]) & (totals > 0) & (totals >= cfg['minimum_library'])
    indices = np.flatnonzero(eligible)
    require(len(indices) > cfg['clusters'] and len(indices)*data.n_vars <= 10_000_000 and data.n_vars <= 2000,
            'domain baseline sample/dense workspace capacity exceeded; use a declared feature subset')
    values = data.X[indices].astype(float).tocsr()
    values = sparse.diags(10000/totals[indices]) @ values
    values.data = np.log1p(values.data)
    matrix = values.toarray()
    matrix -= matrix.mean(axis=0)
    nonconstant = np.std(matrix, axis=0) > 1e-12
    require(nonconstant.sum() >= cfg['components'] and len(indices) > cfg['components'], 'insufficient variable features/components')
    matrix = matrix[:, nonconstant]
    u, singular, _ = np.linalg.svd(matrix, full_matrices=False)
    pcs = u[:, :cfg['components']]*singular[:cfg['components']]
    require(np.linalg.matrix_rank(pcs) >= cfg['components'], 'degenerate expression components')
    xy = np.array([[assay['observations'][i]['x'], assay['observations'][i]['y']] for i in indices])
    edges = radius_edges(xy, cfg['radius'])
    src = np.concatenate([edges[:, 0], edges[:, 1], np.arange(len(indices))])
    dst = np.concatenate([edges[:, 1], edges[:, 0], np.arange(len(indices))])
    adjacency = sparse.csr_matrix((np.ones(len(src)), (src, dst)), shape=(len(indices), len(indices)))
    average = sparse.diags(1/np.asarray(adjacency.sum(axis=1)).ravel()) @ adjacency
    weight = cfg['smoothing_weight']
    smoothed = (1-weight)*pcs + weight*(average @ pcs)
    results = {}
    for name, features in (('expression_only', pcs), ('graph_smoothed', smoothed)):
        centers, labels = kmeans2(features, cfg['clusters'], iter=50, minit='++', missing='raise', seed=cfg['seed'])
        require(len(set(labels)) == cfg['clusters'], 'empty baseline cluster; revise the frozen plan')
        results[name] = {'labels': [{'observation_id': str(data.obs_names[i]), 'cluster': int(label)} for i, label in zip(indices, labels)],
            'inertia_in_own_feature_space': float(np.sum((features-centers[labels])**2)),
            'neighbor_same_cluster_fraction': float(np.mean(labels[edges[:, 0]] == labels[edges[:, 1]])) if len(edges) else None}
    write_json(output, {'schema_version': 'ifquant.domain-baseline-results/1', 'plan': cfg,
        'assay_sha256': canonical_sha256(assay), 'eligible_observations': len(indices), 'excluded_observations': data.n_obs-len(indices),
        'variable_features': int(nonconstant.sum()), 'graph_edges': len(edges), 'results': results,
        'scientific_validation': False, 'interpretation': 'exploratory clusters; spatial smoothness is not domain accuracy; inertia values from different feature spaces are not directly comparable'})
    return {'output': str(output), 'eligible_observations': len(indices), 'graph_edges': len(edges), 'scientific_validation': False}
