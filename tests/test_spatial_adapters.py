"""Native adapter identity, sparse storage, exclusions and coordinate regression tests."""

import pytest

ad = pytest.importorskip('anndata')
import h5py
import numpy as np
import pandas as pd
from scipy import sparse

from ifquant_platform.canonical import ContractError, load_strict_json
from ifquant_platform.imaging import write_json
from ifquant_platform.spatial import count_rows, validate_assay
from ifquant_platform.spatial_adapters import STATUS, export_anndata, import_native


def metadata():
    return {'assay_id': 'synthetic-visium',
            'subject': {'subject_id': 'm1', 'species': 'synthetic', 'specimen_id': 'lung', 'section_id': 's1'},
            'entity_type': 'spot', 'coordinate_frame': {'frame_id': 'assay-pixels', 'unit': 'pixel',
            'axes': ['x', 'y'], 'origin': 'top_left', 'y_direction': 'down'}}


@pytest.fixture
def visium(tmp_path):
    with h5py.File(tmp_path/'matrix.h5', 'w') as handle:
        g = handle.create_group('matrix')
        for key, value in {'shape': [3, 2], 'data': [4, 9, 2], 'indices': [0, 2, 1],
                           'indptr': [0, 2, 3], 'barcodes': [b'001-1', b'abc-1']}.items():
            g.create_dataset(key, data=value)
        f = g.create_group('features')
        for key, value in {'id': [b'f1', b'f2', b'f3'], 'name': [b'dup', b'dup', b'other'],
                           'feature_type': [b'Gene Expression']*3}.items():
            f.create_dataset(key, data=value)
    (tmp_path/'positions.csv').write_text('outside-1,0,2,0,300,500\nabc-1,1,1,0,100,200\n001-1,1,0,0,20,40\n')
    write_json(tmp_path/'scales.json', {'tissue_hires_scalef': .1, 'tissue_lowres_scalef': .03})
    config = dict(metadata(), schema_version='ifquant.native-spatial-import/1', format='visium_h5',
                  inputs={'matrix_h5': 'matrix.h5', 'positions': 'positions.csv', 'scalefactors': 'scales.json'},
                  options={'positions_profile': 'legacy_headerless', 'matrix_scope': 'filtered',
                           'target_image': 'hires', 'feature_ids': None})
    return tmp_path, config


def run_import(root, config, name='native'):
    config_path = root/(name+'.json')
    write_json(config_path, config)
    import_native(config_path, root/name)
    return validate_assay(load_strict_json(root/name/'assay.json'))


def test_visium_coordinates_exclusions_and_duplicate_symbols(visium):
    root, config = visium
    doc = run_import(root, config)
    assert [r['observation_id'] for r in doc['observations']] == ['001-1', 'abc-1', 'outside-1']
    assert [(r['x'], r['y']) for r in doc['observations']] == [(4., 2.), (20., 10.), (50., 30.)]
    assert doc['observations'][-1]['assay_status'] == 'not_reported'
    assert doc['statistics']['libraries'][-1]['total_counts'] is None
    assert [r['feature_name'] for r in doc['features']] == ['dup', 'dup', 'other']
    assert list(count_rows(doc)) == [('001-1', 'f1', 4), ('001-1', 'f3', 9), ('abc-1', 'f2', 2)]


def test_ann_roundtrip_preserves_metadata_and_raw_counts(visium):
    root, config = visium
    original = run_import(root, config)
    export_anndata(root/'native/assay.json', root/'roundtrip.h5ad')
    exported = ad.read_h5ad(root/'roundtrip.h5ad')
    assert sparse.issparse(exported.X)
    assert list(exported.obs['in_tissue']) == [1, 1, 0]
    assert list(exported.obs[STATUS]) == ['measured', 'measured', 'not_reported']
    config.update(format='anndata', inputs={'h5ad': 'roundtrip.h5ad'}, options={
        'counts_layer': 'X', 'coordinates_key': 'spatial', 'feature_name_column': 'feature_name',
        'status_column': STATUS, 'default_status': 'measured', 'feature_ids': None})
    restored = run_import(root, config, 'restored')
    for key in ('subject', 'coordinate_frame', 'observations', 'features', 'statistics'):
        assert restored[key] == original[key]
    assert sorted(count_rows(restored)) == sorted(count_rows(original))


@pytest.mark.parametrize('profile', ['legacy_headerless', 'headered'])
def test_matrix_market_matches_hdf5_and_feature_order(visium, profile):
    root, config = visium
    config['options']['feature_ids'] = ['f3', 'f1']
    hdf = run_import(root, config)
    (root/'matrix.mtx').write_text('%%MatrixMarket matrix coordinate integer general\n% counts\n3 2 3\n1 1 4\n3 1 9\n2 2 2\n')
    (root/'barcodes.tsv').write_text('001-1\nabc-1\n')
    (root/'features.tsv').write_text('f1\tdup\tGene Expression\nf2\tdup\tGene Expression\nf3\tother\tGene Expression\n')
    if profile == 'headered':
        p = root/'positions.csv'
        p.write_text('barcode,in_tissue,array_row,array_col,pxl_row_in_fullres,pxl_col_in_fullres\n'+p.read_text())
    config.update(format='visium_mtx', inputs={'matrix_mtx': 'matrix.mtx', 'barcodes': 'barcodes.tsv',
                                             'features': 'features.tsv', 'positions': 'positions.csv', 'scalefactors': 'scales.json'})
    config['options']['positions_profile'] = profile
    mtx = run_import(root, config, 'mtx')
    assert mtx['observations'] == hdf['observations'] and mtx['features'] == hdf['features']
    assert sorted(count_rows(mtx)) == sorted(count_rows(hdf))


@pytest.mark.parametrize('mutation,match', [('barcode', 'absent'), ('duplicate', 'duplicate'),
                                           ('fractional', 'integer'), ('negative', 'nonnegative'),
                                           ('pointer', 'pointers')])
def test_hdf5_rejects_incompatible_counts(visium, mutation, match):
    root, config = visium
    with h5py.File(root/'matrix.h5', 'a') as f:
        if mutation == 'barcode':
            f['matrix/barcodes'][0] = b'no-id'
        elif mutation == 'duplicate':
            f['matrix/indices'][1] = 0
        elif mutation == 'pointer':
            f['matrix/indptr'][0] = 1
        else:
            del f['matrix/data']
            f['matrix'].create_dataset('data', data=[.5 if mutation == 'fractional' else -1, 9, 2])
    with pytest.raises(ContractError, match=match):
        run_import(root, config)


@pytest.mark.parametrize('layer', ['counts', 'raw.X'])
def test_explicit_anndata_layer_and_feature_subset(tmp_path, layer, monkeypatch):
    matrix = sparse.csr_matrix(([2, 3], ([0, 2], [1, 499])), shape=(4, 500), dtype=np.int64)
    data = ad.AnnData(X=sparse.csr_matrix(matrix.shape), obs=pd.DataFrame(index=['a', 'b', 'c', 'd']),
                     var=pd.DataFrame({'feature_name': ['gene']*500}, index=[f'f{i}' for i in range(500)]))
    data.layers['counts'] = matrix
    data.obsm['spatial'] = np.array([[1, 2], [3, 4], [5, 6], [7, 8]])
    data.raw = ad.AnnData(X=matrix, var=data.var.copy())
    data.write_h5ad(tmp_path/'input.h5ad')
    def no_dense(*args, **kwargs):
        raise AssertionError('unexpected densification')
    monkeypatch.setattr(sparse.csr_matrix, 'toarray', no_dense)
    config = dict(metadata(), schema_version='ifquant.native-spatial-import/1', format='anndata',
                  inputs={'h5ad': 'input.h5ad'}, options={'counts_layer': layer, 'coordinates_key': 'spatial',
                  'feature_name_column': 'feature_name', 'status_column': None, 'default_status': 'measured',
                  'feature_ids': ['f499', 'f1']})
    doc = run_import(tmp_path, config)
    assert list(count_rows(doc)) == [('a', 'f1', 2), ('c', 'f499', 3)]
    assert [r['feature_id'] for r in doc['features']] == ['f499', 'f1']


def test_sparse_output_capacity_fails_before_publishing(visium, monkeypatch):
    root, config = visium
    monkeypatch.setattr('ifquant_platform.spatial_adapters.MAX_COUNT_ROWS', 1)
    with pytest.raises(ContractError, match='capacity'):
        run_import(root, config)
    assert not (root/'native/assay.json').exists()


def test_spatialdata_named_frames_scene_and_store_tampering(visium):
    pytest.importorskip('spatialdata')
    import spatialdata as sd
    from PIL import Image
    from spatialdata.transformations import get_transformation

    from ifquant_platform.spatial_exchange import export_spatialdata, import_spatialdata
    root, config = visium
    original = run_import(root, config)
    Image.new('RGB', (64, 40), 'pink').save(root/'image.png')
    write_json(root/'regions.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': 'r1', 'properties': {'review_status': 'pending'},
         'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [64, 0], [64, 40], [0, 40], [0, 0]]]}}]})
    affine = [[0, -2, 70], [.5, 0, 3], [0, 0, 1]]
    write_json(root/'scene.json', {'frame_id': 'image-pixels', 'image': 'image.png',
               'assay_to_image': affine, 'regions_geojson': 'regions.geojson', 'scale_factors': [2]})
    export_spatialdata(root/'native/assay.json', root/'exchange.zarr', scene_path=root/'scene.json')
    store = sd.read_zarr(root/'exchange.zarr')
    tr = get_transformation(store.points['observations'], to_coordinate_system='image-pixels')
    assert np.array_equal(tr.to_affine_matrix(('x', 'y'), ('x', 'y')), affine)
    assert json_properties(store.shapes['regions'].iloc[0]['properties_json']) == {'review_status': 'pending'}
    assert len(store.images['image'].children) == 2
    restored = import_spatialdata(root/'exchange.zarr', root/'restored')
    doc = load_strict_json(restored['output'])
    assert doc['observations'] == original['observations']
    assert sorted(count_rows(doc)) == sorted(count_rows(original))
    with (root/'exchange.zarr/extra-bytes').open('wb') as out:
        out.write(b'tamper')
    with pytest.raises(ContractError, match='bytes changed'):
        import_spatialdata(root/'exchange.zarr', root/'bad-restore')


def json_properties(value):
    import json
    return json.loads(value)


@pytest.mark.parametrize('encoding', ['csr', 'csc'])
def test_anndata_rejects_duplicate_backing_coordinates(tmp_path, encoding):
    ctor = sparse.csr_matrix if encoding == 'csr' else sparse.csc_matrix
    matrix = ctor(([2, 3], [0, 0], [0, 2, 2]), shape=(2, 2))
    data = ad.AnnData(X=matrix, obs=pd.DataFrame(index=['a', 'b']),
                     var=pd.DataFrame({'feature_name': ['A', 'B']}, index=['f1', 'f2']))
    data.obsm['spatial'] = np.array([[1., 2.], [3., 4.]])
    data.write_h5ad(tmp_path/'duplicate.h5ad')
    config = dict(metadata(), schema_version='ifquant.native-spatial-import/1', format='anndata',
                  inputs={'h5ad': 'duplicate.h5ad'}, options={'counts_layer': 'X', 'coordinates_key': 'spatial',
                  'feature_name_column': 'feature_name', 'status_column': None, 'default_status': 'measured', 'feature_ids': None})
    with pytest.raises(ContractError, match='duplicate'):
        run_import(tmp_path, config)


def test_spatialdata_profile_without_image_is_portable(visium):
    pytest.importorskip('spatialdata')
    import shutil

    from ifquant_platform.spatial_exchange import export_spatialdata, import_spatialdata
    root, config = visium
    original = run_import(root, config)
    export_spatialdata(root/'native/assay.json', root/'exchange.zarr')
    shutil.copytree(root/'exchange.zarr', root/'copied.zarr')
    shutil.copyfile(root/'exchange.zarr.ifquant.json', root/'copied.zarr.ifquant.json')
    restored = import_spatialdata(root/'copied.zarr', root/'restored')
    doc = load_strict_json(restored['output'])
    assert doc['observations'] == original['observations']
    assert sorted(count_rows(doc)) == sorted(count_rows(original))


def test_ann_import_rejects_implicit_rescaling_and_missingness_rewrite(visium):
    root, config = visium
    run_import(root, config)
    export_anndata(root/'native/assay.json', root/'export.h5ad')
    config.update(format='anndata', inputs={'h5ad': 'export.h5ad'}, options={
        'counts_layer': 'X', 'coordinates_key': 'spatial', 'feature_name_column': 'feature_name',
        'status_column': None, 'default_status': 'measured', 'feature_ids': None})
    with pytest.raises(ContractError, match='status conflicts'):
        run_import(root, config, 'bad-status')
    config['options']['status_column'] = STATUS
    config['coordinate_frame']['frame_id'] = 'other-resolution'
    with pytest.raises(ContractError, match='metadata conflicts'):
        run_import(root, config, 'bad-frame')


def test_dense_layer_is_rejected_without_loading_counts(tmp_path):
    data = ad.AnnData(X=np.array([[1, 2]]), obs=pd.DataFrame(index=['a']),
                     var=pd.DataFrame({'feature_name': ['A', 'B']}, index=['f1', 'f2']))
    data.obsm['spatial'] = np.array([[1., 2.]])
    data.write_h5ad(tmp_path/'dense.h5ad')
    config = dict(metadata(), schema_version='ifquant.native-spatial-import/1', format='anndata',
                  inputs={'h5ad': 'dense.h5ad'}, options={'counts_layer': 'X', 'coordinates_key': 'spatial',
                  'feature_name_column': 'feature_name', 'status_column': None, 'default_status': 'measured', 'feature_ids': None})
    with pytest.raises(ContractError, match='dense arrays are unsupported'):
        run_import(tmp_path, config)
