"""Bounded native RNA interchange. Heavy dependencies are optional and lazy.

Only explicitly selected raw counts and XY coordinates enter the common assay.
Metadata tables are retained separately; no implicit barcode/gene normalization.
"""
from __future__ import annotations

import csv
import gzip
import math
from contextlib import contextmanager
from pathlib import Path

from .canonical import ContractError, canonical_sha256, load_strict_json
from .imaging import keys, require, write_json
from .spatial import (
    MAX_COUNT_ROWS,
    MAX_FEATURES,
    MAX_OBSERVATIONS,
    _assay_metadata,
    count_rows,
    exact_id,
    file_record,
    import_assay,
    validate_assay,
    verify_file,
)

MAX_INPUT_NNZ = 100_000_000
MAX_SLICE_NNZ = 1_000_000
MAX_METADATA_CELLS = 5_000_000
MAX_INPUT_BYTES = 8 * 1024**3
STATUS = 'ifquant_assay_status'


def libraries():
    try:
        import anndata as ad
        import h5py
        import numpy as np
        import pandas as pd
        from scipy import sparse
    except ImportError as exc:
        raise ContractError('native RNA adapters require the optional [spatial] extra') from exc
    return ad, h5py, np, pd, sparse


@contextmanager
def text_input(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        yield stream


def _ids(values, label, limit):
    result = list(values)
    require(0 < len(result) <= limit, f'{label}: empty or capacity limit exceeded')
    for value in result:
        exact_id(value, label)
    require(len(set(result)) == len(result), f'duplicate {label}')
    return result


def _selection(ids, selected):
    if selected is None:
        return list(range(len(ids)))
    _ids(selected, 'selected feature IDs', MAX_FEATURES)
    lookup = {value: i for i, value in enumerate(ids)}
    require(set(selected) <= lookup.keys(), 'selected feature ID absent from input')
    return [lookup[value] for value in selected]


def _raw_count(value):
    number = float(value)
    require(math.isfinite(number) and number.is_integer() and 0 <= number <= 2**53-1,
            'raw counts must be finite nonnegative safe integers')
    return int(value)


def _metadata_bounds(obs, var):
    require(obs.size + var.size <= MAX_METADATA_CELLS, 'metadata cell limit exceeded')
    _ids(obs.index, 'observation IDs', MAX_OBSERVATIONS)
    _ids(var.index, 'feature IDs', MAX_FEATURES)


def _finish(root, config, records, obs, var, xy, statuses, rows, details):
    ad, _, np, _, _ = libraries()
    _metadata_bounds(obs, var)
    require(xy.shape == (len(obs), 2) and np.isfinite(xy).all(), 'finite N x 2 coordinates required')
    require(len(statuses) == len(obs) and set(statuses) <= {'measured', 'not_assayed', 'failed', 'not_reported'},
            'invalid RNA assay status')
    require('feature_name' in var, 'explicit feature names required')
    with (root/'observations.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['observation_id', 'x', 'y', 'assay_status'])
        writer.writerows((oid, float(point[0]), float(point[1]), status)
                         for oid, point, status in zip(obs.index, xy, statuses))
    with (root/'features.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['feature_id', 'feature_name'])
        writer.writerows(zip(var.index, var['feature_name']))
    n = 0
    with (root/'counts.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['observation_id', 'feature_id', 'count'])
        for i, j, value in rows:
            value = _raw_count(value)
            if value:
                require(statuses[i] == 'measured', 'nonzero counts on unresolved RNA observation')
                n += 1
                require(n <= MAX_COUNT_ROWS, 'selected counts exceed output row capacity; select fewer features')
                writer.writerow([obs.index[i], var.index[j], value])
    # No matrix is stored in this sidecar, only supported obs/var metadata.
    ad.AnnData(obs=obs.copy(), var=var.copy()).write_h5ad(root/'annotations.h5ad')
    common = {k: config[k] for k in ('assay_id', 'subject', 'entity_type', 'coordinate_frame')}
    common.update(schema_version='ifquant.spatial-import/1', observations_csv='observations.csv',
                  features_csv='features.csv', counts_csv='counts.csv')
    write_json(root/'import.json', common)
    for record in records.values():
        verify_file(record)
    result = import_assay(root/'import.json', root/'assay.json')
    manifest = {'schema_version': 'ifquant.native-spatial-adapter/1', 'format': config['format'],
                'inputs': records, 'options': config['options'], 'details': details,
                'assay_sha256': result['assay_sha256'],
                'annotations': file_record(root/'annotations.h5ad'), 'scientific_validation': False}
    write_json(root/'adapter.json', manifest)
    return {**result, 'adapter': str(root/'adapter.json'), 'count_rows': n}


def import_native(config_path, output):
    config = load_strict_json(config_path)
    keys(config, {'schema_version', 'format', 'assay_id', 'subject', 'entity_type',
                  'coordinate_frame', 'inputs', 'options'}, 'native spatial config')
    require(config['schema_version'] == 'ifquant.native-spatial-import/1', 'unsupported native config')
    _assay_metadata(config)
    require(config['format'] in ('anndata', 'visium_h5', 'visium_mtx'), 'unsupported native format')
    base = Path(config_path).resolve().parent
    paths = {key: base / value for key, value in config['inputs'].items()}
    records = {key: file_record(path) for key, path in paths.items()}
    records['config'] = file_record(config_path)
    require(all(r['size_bytes'] <= MAX_INPUT_BYTES for r in records.values()), 'native input byte limit exceeded')
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    if config['format'] == 'anndata':
        return _anndata(root, config, paths, records)
    return _visium(root, config, paths, records)


def _anndata(root, config, paths, records):
    ad, h5py, np, _, sparse = libraries()
    keys(paths, {'h5ad'}, 'AnnData inputs')
    options = config['options']
    keys(options, {'counts_layer', 'coordinates_key', 'feature_name_column', 'status_column',
                   'default_status', 'feature_ids'}, 'AnnData options')
    layer = options['counts_layer']
    require(isinstance(layer, str) and bool(layer), 'explicit raw counts layer required')
    element = 'X' if layer == 'X' else 'raw/X' if layer == 'raw.X' else 'layers/' + layer
    with h5py.File(paths['h5ad'], 'r') as handle:
        require(element in handle, 'selected count layer is absent')
        var_key = 'raw/var' if layer == 'raw.X' else 'var'
        data = handle[element]
        require(isinstance(data, h5py.Group) and data.attrs.get('encoding-type') in ('csr_matrix', 'csc_matrix'),
                'bounded native adapter requires sparse CSR/CSC counts; dense arrays are unsupported')
        shape = tuple(data.attrs['shape'])
        require(len(shape) == 2 and 0 < shape[0] <= MAX_OBSERVATIONS and 0 < shape[1] <= MAX_FEATURES,
                'AnnData dimensions exceed capacity')
        require(shape[0]*len(handle['obs']) + shape[1]*len(handle[var_key]) <= MAX_METADATA_CELLS,
                'metadata cell limit exceeded')
        obs, var = ad.io.read_elem(handle['obs']), ad.io.read_elem(handle[var_key])
        _metadata_bounds(obs, var)
        require(shape == (len(obs), len(var)), 'count dimensions differ from metadata')
        if 'uns/ifquant_metadata_json' in handle:
            import json
            embedded = json.loads(ad.io.read_elem(handle['uns/ifquant_metadata_json']))
            require(all(embedded[k] == config[k] for k in
                        ('subject', 'entity_type', 'coordinate_frame')), 'embedded spatial metadata conflicts with config')
        selected = _selection(list(var.index), options['feature_ids'])
        var = var.iloc[selected].copy()
        name_col = options['feature_name_column']
        require(name_col in var, 'feature name column absent')
        var['feature_name'] = var[name_col]
        coordinate_key = 'obsm/' + options['coordinates_key']
        require(coordinate_key in handle, 'selected coordinates absent')
        xy = np.asarray(ad.io.read_elem(handle[coordinate_key]))
        require(xy.shape == (len(obs), 2), 'AnnData coordinates must be N x 2')
        status_col = options['status_column']
        require(status_col is None or status_col in obs, 'status column absent')
        statuses = list(obs[status_col]) if status_col else [options['default_status']]*len(obs)
        if STATUS in obs and status_col != STATUS:
            require(list(obs[STATUS]) == statuses, 'stored assay status conflicts with import options')
        require(len(data['data']) <= MAX_INPUT_NNZ, 'input sparse matrix exceeds capacity')
        matrix = ad.io.sparse_dataset(data)
        def rows():
            # A single row is bounded by the declared feature count. No dense N x G array.
            for i in range(len(obs)):
                row = matrix[i:i+1, :].tocsr()
                require(row.nnz <= MAX_SLICE_NNZ and row.has_canonical_format,
                        'oversized or duplicate sparse coordinates')
                require(sparse.issparse(row), 'matrix must remain sparse')
                row = row[:, selected].tocoo()
                yield from ((i, int(j), v) for j, v in zip(row.col, row.data))
        return _finish(root, config, records, obs, var, xy, statuses, rows(),
                       {'count_element': element, 'input_observations': len(obs),
                        'input_features': int(matrix.shape[1]), 'selected_features': len(var),
                        'metadata_scope': 'obs and selected var; selected XY only; other uns/obsm not copied'})


def _positions(path, profile):
    columns = ['barcode', 'in_tissue', 'array_row', 'array_col', 'pxl_row_in_fullres', 'pxl_col_in_fullres']
    require(profile in ('legacy_headerless', 'headered'), 'explicit positions profile required')
    result = []
    with text_input(path) as stream:
        reader = csv.reader(stream)
        if profile == 'headered':
            require(next(reader, None) == columns, 'unsupported Visium positions header')
        for row in reader:
            require(len(result) < MAX_OBSERVATIONS and len(row) == 6, 'invalid/oversized positions table')
            require(row[1] in ('0', '1'), 'in_tissue must be 0 or 1')
            try:
                parsed = [row[0], int(row[1]), int(row[2]), int(row[3]), float(row[4]), float(row[5])]
            except ValueError as exc:
                raise ContractError('invalid Visium position') from exc
            require(parsed[2] >= 0 and parsed[3] >= 0 and all(math.isfinite(v) for v in parsed[4:]),
                    'invalid Visium coordinate')
            result.append(parsed)
    _ids([r[0] for r in result], 'position barcodes', MAX_OBSERVATIONS)
    return result, columns


def _tsv(path, width, limit):
    rows = []
    with text_input(path) as stream:
        for row in csv.reader(stream, delimiter='\t'):
            require(len(row) == width and len(rows) < limit, 'invalid/oversized 10x table')
            rows.append(row)
    return rows


def _visium(root, config, paths, records):
    _, h5py, _, pd, _ = libraries()
    options = config['options']
    keys(options, {'positions_profile', 'matrix_scope', 'target_image', 'feature_ids'}, 'Visium options')
    require(options['matrix_scope'] in ('filtered', 'raw'), 'declare matrix scope')
    require(options['target_image'] in ('fullres', 'hires', 'lowres'), 'explicit image resolution required')
    require(config['entity_type'] == 'spot' and config['coordinate_frame']['unit'] == 'pixel',
            'Visium adapter requires spot entities and a pixel frame')
    matrix_keys = {'matrix_h5'} if config['format'] == 'visium_h5' else {'matrix_mtx', 'barcodes', 'features'}
    keys(paths, matrix_keys | {'positions', 'scalefactors'}, 'Visium inputs')
    positions, columns = _positions(paths['positions'], options['positions_profile'])
    scales = load_strict_json(paths['scalefactors'])
    scale = 1 if options['target_image'] == 'fullres' else scales.get('tissue_'+options['target_image']+'_scalef')
    require(type(scale) in (int, float) and math.isfinite(scale) and 0 < scale <= 1, 'invalid image scale factor')
    if config['format'] == 'visium_h5':
        with h5py.File(paths['matrix_h5'], 'r') as handle:
            require('matrix' in handle, 'only 10x v3 matrix HDF5 supported')
            group = handle['matrix']
            require(len(group['barcodes']) <= MAX_OBSERVATIONS and
                    len(group['features/id']) <= MAX_FEATURES, '10x metadata dimensions exceed capacity')
            barcodes = list(group['barcodes'].asstr()[:])
            f = group['features']
            features = list(zip(f['id'].asstr()[:], f['name'].asstr()[:], f['feature_type'].asstr()[:]))
        rows_factory = lambda selected: _h5_rows(paths['matrix_h5'], len(features), len(barcodes), selected)
    else:
        barcodes = [row[0] for row in _tsv(paths['barcodes'], 1, MAX_OBSERVATIONS)]
        features = _tsv(paths['features'], 3, MAX_FEATURES)
        rows_factory = lambda selected: _mtx_rows(paths['matrix_mtx'], len(features), len(barcodes), selected)
    _ids(barcodes, 'matrix barcodes', MAX_OBSERVATIONS)
    feature_ids = _ids([r[0] for r in features], 'feature IDs', MAX_FEATURES)
    selected = _selection(feature_ids, options['feature_ids'])
    require(all(features[i][2] == 'Gene Expression' for i in selected), 'selected non-RNA feature')
    position_index = {row[0]: row for row in positions}
    require(set(barcodes) <= position_index.keys(), 'matrix barcode absent from positions')
    # Preserve matrix order, then source positions missing from a filtered matrix.
    # Their counts are NOT asserted to be zero or unassayed; only unavailable here.
    barcode_set = set(barcodes)
    missing = [r[0] for r in positions if r[0] not in barcode_set]
    ordered = barcodes + missing
    obs = pd.DataFrame([position_index[oid][1:] for oid in ordered], columns=columns[1:],
                       index=pd.Index(ordered, name='observation_id'))
    obs['matrix_available'] = [True]*len(barcodes) + [False]*len(missing)
    obs['exclusion_reason'] = ['']*len(barcodes) + ['absent_from_supplied_matrix']*len(missing)
    statuses = ['measured']*len(barcodes) + ['not_reported']*len(missing)
    var = pd.DataFrame([features[i][1:] for i in selected], columns=['feature_name', 'feature_type'],
                       index=pd.Index([feature_ids[i] for i in selected], name='feature_id'))
    xy = obs[['pxl_col_in_fullres', 'pxl_row_in_fullres']].to_numpy(dtype=float)*scale
    details = {'matrix_scope': options['matrix_scope'], 'target_image': options['target_image'],
               'applied_scale': scale, 'input_features': len(features), 'selected_features': len(selected),
               'matrix_observations': len(barcodes), 'positions_without_matrix': len(missing),
               'missing_matrix_status': 'not_reported; unavailable in supplied matrix, not zero or assay failure',
               'scalefactors': scales, 'physical_calibration': 'not supplied by this adapter'}
    return _finish(root, config, records, obs, var, xy, statuses, rows_factory(selected), details)


def _h5_rows(path, nfeatures, nobs, selected):
    _, h5py, np, _, _ = libraries()
    lookup = {j: i for i, j in enumerate(selected)}
    with h5py.File(path, 'r') as handle:
        matrix = handle['matrix']
        require(list(matrix['shape'][:]) == [nfeatures, nobs], '10x matrix dimensions disagree')
        ptr = matrix['indptr'][:]
        require(len(ptr) == nobs+1 and ptr[0] == 0 and np.all(ptr[1:] >= ptr[:-1]), 'invalid CSC pointers')
        require(ptr[-1] == len(matrix['data']) == len(matrix['indices']) <= MAX_INPUT_NNZ,
                'invalid/oversized CSC matrix')
        for i in range(nobs):
            lo, hi = int(ptr[i]), int(ptr[i+1])
            require(hi-lo <= MAX_SLICE_NNZ, 'CSC column exceeds capacity')
            indices, values = matrix['indices'][lo:hi], matrix['data'][lo:hi]
            require(np.issubdtype(indices.dtype, np.integer) and len(set(indices)) == len(indices) and
                    np.all((indices >= 0) & (indices < nfeatures)), 'duplicate/out-of-range sparse coordinate')
            for j, value in zip(indices, values):
                value = _raw_count(value)
                if j in lookup:
                    yield i, lookup[j], value


def _mtx_rows(path, nfeatures, nobs, selected):
    lookup = {j: i for i, j in enumerate(selected)}
    seen = set()
    with text_input(path) as stream:
        require(stream.readline().strip().lower() == '%%matrixmarket matrix coordinate integer general',
                'only integer general coordinate Matrix Market supported')
        line = stream.readline()
        while line.startswith('%'):
            line = stream.readline()
        try:
            nf, no, entries = map(int, line.split())
        except ValueError as exc:
            raise ContractError('invalid Matrix Market dimensions') from exc
        require((nf, no) == (nfeatures, nobs) and 0 <= entries <= MAX_INPUT_NNZ, 'invalid/oversized matrix shape')
        for _ in range(entries):
            fields = stream.readline().split()
            require(len(fields) == 3, 'truncated/invalid matrix entry')
            try:
                j, i, value = map(int, fields)
            except ValueError as exc:
                raise ContractError('integer matrix entry required') from exc
            require(1 <= i <= nobs and 1 <= j <= nfeatures, 'out-of-range matrix coordinate')
            _raw_count(value)
            if j-1 in lookup:
                key = (i-1, j-1)
                require(key not in seen, 'duplicate selected matrix coordinate')
                require(len(seen) < MAX_COUNT_ROWS, 'selected matrix coordinates exceed capacity')
                seen.add(key)
                yield i-1, lookup[j-1], value
        require(not stream.read(1), 'extra Matrix Market content')


def assay_to_anndata(assay_path):
    ad, _, np, pd, sparse = libraries()
    assay = validate_assay(load_strict_json(assay_path))
    oids = [r['observation_id'] for r in assay['observations']]
    fids = [r['feature_id'] for r in assay['features']]
    obs = pd.DataFrame(index=oids)
    var = pd.DataFrame({'feature_name': [r['feature_name'] for r in assay['features']]}, index=fids)
    adapter_path = Path(assay_path).parent/'adapter.json'
    if adapter_path.exists():
        adapter = load_strict_json(adapter_path)
        require(adapter['assay_sha256'] == canonical_sha256(assay), 'adapter assay identity mismatch')
        for record in adapter['inputs'].values():
            verify_file(record)
        verify_file(adapter['annotations'])
        annotations = ad.read_h5ad(adapter['annotations']['path'])
        require(list(annotations.obs_names) == oids and list(annotations.var_names) == fids,
                'adapter metadata identity mismatch')
        obs, var = annotations.obs.copy(), annotations.var.copy()
    oi, fi = {v: i for i, v in enumerate(oids)}, {v: i for i, v in enumerate(fids)}
    ii, jj, data = [], [], []
    for oid, fid, value in count_rows(assay):
        if value:
            ii.append(oi[oid]); jj.append(fi[fid]); data.append(value)
    matrix = sparse.coo_matrix((np.asarray(data, dtype=np.int64), (ii, jj)),
                               shape=(len(oids), len(fids))).tocsr()
    obs[STATUS] = [r['assay_status'] for r in assay['observations']]
    result = ad.AnnData(X=matrix, obs=obs, var=var)
    result.obsm['spatial'] = np.array([[r['x'], r['y']] for r in assay['observations']])
    # String JSON avoids AnnData's heterogeneous-list coercion and preserves exact metadata.
    import json
    result.uns['ifquant_metadata_json'] = json.dumps({k: assay[k] for k in
        ('assay_id', 'subject', 'entity_type', 'coordinate_frame', 'matrix_semantics', 'scientific_validation')})
    return result


def export_anndata(assay_path, output):
    require(not Path(output).exists(), 'refusing to overwrite AnnData output')
    data = assay_to_anndata(assay_path)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    data.write_h5ad(output)
    return {'output': str(output), 'observations': data.n_obs, 'features': data.n_vars,
            'matrix': 'sparse CSR raw counts; unresolved rows carry explicit status'}
