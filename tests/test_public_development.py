"""Independent matching, denominator, axis-selection and optional-engine checks."""
import csv
import sys
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('scipy')

from ifquant_platform.canonical import ContractError, load_strict_json
from ifquant_platform.imaging import write_json
from ifquant_platform.instance_segmentation import match_instances, segment_instanseg
from ifquant_platform.rna_normalization import library_totals


def test_instance_matching_labels_and_split():
    reference = np.array([[2, 2, 0, 9], [2, 2, 0, 9]])
    prediction = np.array([[4, 5, 0, 8], [4, 5, 0, 8]])
    result = match_instances(reference, prediction)
    assert (result['true_positive'], result['false_positive'], result['false_negative']) == (2, 1, 0)
    assert result['f1'] == .8 and result['mean_matched_iou'] == .75
    assert match_instances(reference, reference*100)['f1'] == 1
    assert match_instances(np.zeros((2, 2)), np.zeros((2, 2)))['f1'] is None
    with pytest.raises(ContractError, match='integer'):
        match_instances(reference, prediction+.1)
    with pytest.raises(ContractError, match='grids'):
        match_instances(reference, prediction[:, :2])


def test_library_denominators_are_complete_and_not_panel_totals(tmp_path):
    ad = pytest.importorskip('anndata')
    from scipy import sparse
    data = ad.AnnData(sparse.csr_matrix([[2, 3], [0, 4]]))
    path = tmp_path/'total.csv'
    def table(rows):
        with path.open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['observation_id', 'total_counts'])
            writer.writerows(rows)
    table([['0', 100], ['1', 400]])
    totals, record = library_totals(data, 'external_full_library', path)
    assert list(totals) == [100, 400] and record['size_bytes'] > 0
    with pytest.raises(ContractError, match='cannot carry'):
        library_totals(data, 'selected_features', path)
    table([['0', 100]])
    with pytest.raises(ContractError, match='complete'):
        library_totals(data, 'external_full_library', path)
    table([['0', 1], ['1', 400]])
    with pytest.raises(ContractError, match='smaller'):
        library_totals(data, 'external_full_library', path)


@pytest.mark.parametrize('version', ['0.4', '0.5'])
def test_multiaxis_ngff_plane_and_coordinates(tmp_path, version):
    zarr = pytest.importorskip('zarr')
    tifffile = pytest.importorskip('tifffile')
    from ifquant_platform.upstream_interchange import import_ngff_window
    root = zarr.open_group(str(tmp_path/'image.zarr'), mode='w', zarr_format=3 if version == '0.5' else 2)
    names = ['t', 'c', 'z', 'y', 'x']
    pixels = np.arange(2*4*3*5*6, dtype=np.uint16).reshape(2, 4, 3, 5, 6).astype('uint8')
    root.create_array('0', data=pixels, chunks=(1, 1, 1, 5, 6), **({'dimension_names': names} if version == '0.5' else {}))
    axes = [{'name': n, 'type': t, **({'unit': u} if u else {})} for n, t, u in
            [('t', 'time', 'second'), ('c', 'channel', None), ('z', 'space', 'micrometer'),
             ('y', 'space', 'micrometer'), ('x', 'space', 'micrometer')]]
    meta = {'axes': axes, 'datasets': [{'path': '0', 'coordinateTransformations': [
        {'type': 'scale', 'scale': [2, 1, 4, 3, 2]}, {'type': 'translation', 'translation': [10, 0, 20, 30, 40]}]}]}
    if version == '0.5':
        root.attrs['ome'] = {'version': version, 'multiscales': [meta]}
    else:
        root.attrs['multiscales'] = [dict(meta, version=version)]
    cfg = {'schema_version': 'ifquant.ngff-window/2', 'store': 'image.zarr', 'multiscale': 0, 'level': 0,
        'window_xywh': [1, 2, 3, 2], 'axis_indices': {'t': 1, 'z': 2}, 'channel_indices': [3, 1, 0],
        'channel_semantics': 'rgb', 'modality': 'he',
        'subject': {'subject_id': 'fixture', 'species': 'synthetic', 'specimen_id': 's', 'section_id': 'p'}}
    write_json(tmp_path/'plan.json', cfg)
    import_ngff_window(tmp_path/'plan.json', tmp_path/'out')
    expected = np.moveaxis(pixels[1, [3, 1, 0], 2, 2:4, 1:4], 0, -1)
    assert np.array_equal(tifffile.imread(tmp_path/'out/window.tif'), expected)
    result = load_strict_json(tmp_path/'out/derivation.json')
    assert result['window_origin_um_xy'] == [42, 36]
    assert result['selected_axis_coordinates']['z']['coordinate'] == 28
    assert result['selected_axis_coordinates']['t']['coordinate'] == 12
    cfg['axis_indices'].pop('z')
    write_json(tmp_path/'bad.json', cfg)
    with pytest.raises(ContractError, match='selection'):
        import_ngff_window(tmp_path/'bad.json', tmp_path/'bad')


def test_feature_selection_uses_full_library_and_stable_ties():
    from scipy import sparse
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
    from replay_lung_rna import select_features
    matrix = sparse.csr_matrix([[4, 4, 2], [8, 8, 4], [2, 2, 16]])
    indices, totals = select_features(matrix, ['A', 'B', 'mt-C'], ['g2', 'g1', 'g3'], ['g3'], 1, 1, ['mt-'])
    assert indices == [1, 2] and list(totals) == [10, 20, 20]


def test_optional_banksy_execution(tmp_path):
    pytest.importorskip('banksy')
    from ifquant_platform.spatial import import_assay
    from ifquant_platform.spatial_domains import domain_baselines
    with (tmp_path/'obs.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['observation_id', 'x', 'y', 'assay_status'])
        w.writerows([f'c{i}', i % 5, i // 5, 'measured'] for i in range(30))
    (tmp_path/'var.csv').write_text('feature_id,feature_name\ng1,A\ng2,B\ng3,C\n')
    with (tmp_path/'counts.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['observation_id', 'feature_id', 'count'])
        w.writerows([f'c{i}', f'g{j+1}', (i*(j+2)+j*j) % 13+1] for i in range(30) for j in range(3))
    with (tmp_path/'totals.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['observation_id', 'total_counts'])
        w.writerows([f'c{i}', 100+i*2] for i in range(30))
    write_json(tmp_path/'import.json', {'schema_version': 'ifquant.spatial-import/1', 'assay_id': 'fixture',
        'subject': {'subject_id': 'fixture', 'species': 'synthetic', 'specimen_id': 's', 'section_id': 'p'},
        'entity_type': 'spot', 'coordinate_frame': {'frame_id': 'f', 'unit': 'pixel', 'axes': ['x', 'y'],
        'origin': 'top_left', 'y_direction': 'down'}, 'observations_csv': 'obs.csv', 'features_csv': 'var.csv', 'counts_csv': 'counts.csv'})
    import_assay(tmp_path/'import.json', tmp_path/'assay.json')
    cfg = {'schema_version': 'ifquant.domain-baselines/2', 'assay': 'assay.json',
        'normalization_basis': 'external_full_library', 'library_totals_csv': 'totals.csv',
        'minimum_features': 3, 'minimum_library': 1, 'components': 2, 'clusters': 3, 'seed': 1,
        'radius': 1.1, 'coordinate_unit': 'pixel', 'smoothing_weight': .5,
        'banksy': {'neighbors': 4, 'lambda': .8, 'max_m': 1}}
    write_json(tmp_path/'plan.json', cfg)
    domain_baselines(tmp_path/'plan.json', tmp_path/'out.json')
    result = load_strict_json(tmp_path/'out.json')
    assert result['eligible_observations'] == 30 and len(result['results']) == 4
    assert len(result['partition_comparisons']) == 6 and result['external_library_input']
    assert not result['scientific_validation']


def test_instanseg_rejects_unpinned_model_before_loading(tmp_path):
    from PIL import Image

    from ifquant_platform.imaging import register_image
    Image.new('RGB', (32, 32)).save(tmp_path/'image.png')
    register_image(tmp_path/'image.png', tmp_path/'source.json', subject_id='s', species='synthetic',
        specimen_id='s', section_id='s', pixel_size_x=.5, pixel_size_y=.5, reader='pillow')
    (tmp_path/'model.pt').write_bytes(b'not a trusted model')
    write_json(tmp_path/'plan.json', {'schema_version': 'ifquant.instanseg/1', 'source': 'source.json',
        'weights': 'model.pt', 'window_xywh': [0, 0, 32, 32], 'threads': 1})
    with pytest.raises(ContractError, match='pinned official'):
        segment_instanseg(tmp_path/'plan.json', tmp_path/'out')
    assert not (tmp_path/'out').exists()
