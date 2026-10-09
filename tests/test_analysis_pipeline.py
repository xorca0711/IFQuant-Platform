"""Independent arithmetic, missingness and identity checks for priorities 3–5."""
import csv
import math

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('scipy')
pytest.importorskip('anndata')
from PIL import Image

from ifquant_platform.canonical import (
    ContractError,
    canonical_sha256,
    file_sha256,
    load_strict_json,
)
from ifquant_platform.imaging import register_image, write_json
from ifquant_platform.imaging_evaluation import compare_masks, reviewer_agreement
from ifquant_platform.molecular_programs import score_programs
from ifquant_platform.spatial import import_assay
from ifquant_platform.spatial_statistics import bh_adjust, mixing, radius_edges, spatial_hypotheses


def csv_file(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


@pytest.fixture
def example(tmp_path):
    Image.new('RGB', (12, 10), 'pink').save(tmp_path/'image.png')
    subject = {'subject_id': 'mouse', 'species': 'synthetic', 'specimen_id': 'lung', 'section_id': 's1'}
    register_image(tmp_path/'image.png', tmp_path/'source.json', **subject, pixel_size_x=2, pixel_size_y=3, reader='pillow')
    csv_file(tmp_path/'obs.csv', ['observation_id', 'x', 'y', 'assay_status'],
             [[f'c{i}', i % 4+1, i // 4+1, 'measured' if i < 10 else 'not_reported'] for i in range(12)])
    csv_file(tmp_path/'var.csv', ['feature_id', 'feature_name'], [['g1', 'one'], ['g2', 'two']])
    csv_file(tmp_path/'counts.csv', ['observation_id', 'feature_id', 'count'],
             [[f'c{i}', 'g1', i+1] for i in range(9)]+[['c0', 'g2', 3]])
    config = {'schema_version': 'ifquant.spatial-import/1', 'assay_id': 'synthetic', 'subject': subject,
        'entity_type': 'nucleus', 'coordinate_frame': {'frame_id': 'pixels', 'unit': 'pixel', 'axes': ['x', 'y'],
            'origin': 'top_left', 'y_direction': 'down'}, 'observations_csv': 'obs.csv',
            'features_csv': 'var.csv', 'counts_csv': 'counts.csv'}
    write_json(tmp_path/'import.json', config)
    import_assay(tmp_path/'import.json', tmp_path/'assay.json')
    return tmp_path


def run(root, config, function, stem='plan'):
    write_json(root/(stem+'.json'), config)
    function(root/(stem+'.json'), root/(stem+'-out.json'))
    return load_strict_json(root/(stem+'-out.json'))


def test_mask_confusion_and_absent_class(example):
    truth = np.zeros((10, 12), dtype=np.uint8); truth[0, :4] = 1; truth[1, 0] = 255
    pred = truth.copy(); pred[0, 0] = 0; pred[2, 0] = 1
    Image.fromarray(truth).save(example/'truth.png'); Image.fromarray(pred).save(example/'pred.png')
    config = {'schema_version': 'ifquant.mask-comparison/1', 'source': 'source.json', 'reference_mask': 'truth.png',
        'prediction_mask': 'pred.png', 'classes': [0, 1, 2], 'ignore_value': 255,
        'reference_review': {'status': 'accepted', 'reviewer': 'fixture', 'at': '2026-10-09', 'data_kind': 'synthetic'},
        'method_id': 'fixture', 'sampling_protocol': 'synthetic-complete-grid'}
    report = run(example, config, compare_masks)
    assert report['confusion_matrix'] == [[114, 1, 0], [1, 3, 0], [0, 0, 0]]
    assert report['outcomes'][1]['dice'] == .75
    assert report['outcomes'][2]['dice'] is None
    assert report['ignored_pixels'] == 1


def test_ordinal_agreement_missing_and_degenerate(example):
    csv_file(example/'ratings.csv', ['unit_id', 'reviewer', 'endpoint_id', 'score'],
             [['a', 'r1', 'injury', 0], ['a', 'r2', 'injury', 0], ['b', 'r1', 'injury', 1],
              ['b', 'r2', 'injury', 2], ['c', 'r1', 'injury', 2], ['c', 'r2', 'injury', 2], ['d', 'r1', 'injury', '']])
    cfg = {'schema_version': 'ifquant.ordinal-agreement/1', 'ratings_csv': 'ratings.csv', 'endpoint_id': 'injury',
           'ordered_scores': [0, 1, 2], 'reviewers': ['r1', 'r2'], 'rubric_reference': 'synthetic-rubric-v1'}
    out = run(example, cfg, reviewer_agreement)
    # Linear observed disagreement = 1/6; independent marginal expectation = 1/2.
    assert out['linear_weighted_kappa'] == pytest.approx(2/3)
    assert out['paired_units'] == 3 and out['incomplete_units'] == 1
    csv_file(example/'ratings.csv', ['unit_id', 'reviewer', 'endpoint_id', 'score'],
             [['a', 'r1', 'injury', 0], ['a', 'r2', 'injury', 0]])
    assert run(example, cfg, reviewer_agreement, 'constant')['linear_weighted_kappa'] is None


def program_config(root):
    write_json(root/'programs.json', {'schema_version': 'ifquant.gene-programs/1', 'registry_id': 'fixture-v1',
        'species': 'synthetic', 'feature_id_namespace': 'fixture', 'programs': [
            {'program_id': 'p1', 'feature_ids': ['g1', 'g2'], 'reference': 'fixture', 'min_coverage_fraction': 1,
             'interpretation': 'arithmetic test'},
            {'program_id': 'absent', 'feature_ids': ['g3'], 'reference': 'fixture', 'min_coverage_fraction': 1,
             'interpretation': 'coverage test'}]})
    return {'schema_version': 'ifquant.rna-program-analysis/1', 'assay': 'assay.json', 'programs': 'programs.json',
        'normalization_basis': 'selected_features', 'library_totals_csv': None, 'min_library_counts': 0, 'min_detected_features': 0}


def test_programs_raw_counts_coverage_and_missingness(example):
    cfg = program_config(example)
    before = file_sha256(example/'counts.csv')
    out = run(example, cfg, score_programs)
    rows = {(r['observation_id'], r['program_id']): r for r in out['observations']}
    assert rows['c0', 'p1']['mean_log1p_cp10k'] == pytest.approx((math.log1p(2500)+math.log1p(7500))/2)
    assert rows['c0', 'absent']['status'] == 'insufficient_gene_coverage'
    assert rows['c9', 'p1']['status'] == 'zero_library'
    assert rows['c10', 'p1']['status'] == 'rna_not_measured'
    assert file_sha256(example/'counts.csv') == before
    cfg.update(normalization_basis='external_full_library', library_totals_csv='totals.csv')
    csv_file(example/'totals.csv', ['observation_id', 'total_counts'], [[f'c{i}', 20] for i in range(12)])
    out = run(example, cfg, score_programs, 'full')
    assert out['observations'][0]['mean_log1p_cp10k'] == pytest.approx((math.log1p(500)+math.log1p(1500))/2)


@pytest.mark.parametrize('mutation,match', [('species', 'species'), ('total', 'smaller')])
def test_program_input_rejections(example, mutation, match):
    cfg = program_config(example)
    if mutation == 'species':
        registry = load_strict_json(example/'programs.json'); registry['species'] = 'wrong'
        write_json(example/'programs.json', registry, replace=True)
    else:
        cfg.update(normalization_basis='external_full_library', library_totals_csv='totals.csv')
        csv_file(example/'totals.csv', ['observation_id', 'total_counts'], [[f'c{i}', 0] for i in range(12)])
    with pytest.raises(ContractError, match=match):
        run(example, cfg, score_programs)


def test_graph_mixing_and_bh_arithmetic():
    xy = np.array([[0, 0], [1, 0], [2, 0], [3, 0]])
    edges = radius_edges(xy, 1.1)
    assert edges.tolist() == [[0, 1], [1, 2], [2, 3]]
    result = mixing(edges, np.array(['r', 'r', 't', 't']), 'r', 't')
    assert result['normalized_mixing_score'] == .25
    assert result['reference_reference_edges'] == 1
    adjusted = bh_adjust([.01, .04, None, .03])
    assert [adjusted[i] for i in (0, 1, 3)] == pytest.approx([.04, .0533333333, .0533333333])
    assert bh_adjust([.01, .04, None, .03])[2] is None
    with pytest.raises(ContractError, match='capacity'):
        radius_edges(xy, 5, limit=2)


def hypothesis_config(root):
    csv_file(root/'labels.csv', ['observation_id', 'specimen_id', 'region_id', 'coverage_stratum', 'label', 'boundary_distance'],
             [[f'c{i}', 'lung', 'all', 'coverage1', 'r' if i < 5 else 't', 10] for i in range(12)])
    return {'schema_version': 'ifquant.spatial-hypotheses/1', 'assay': 'assay.json',
        'assay_sha256': canonical_sha256(load_strict_json(root/'assay.json')), 'labels_csv': 'labels.csv',
        'labels_sha256': file_sha256(root/'labels.csv'), 'coordinate_unit': 'pixel',
        'pairs': [{'test_id': 'rt', 'reference': 'r', 'target': 't'}], 'radii': [1.1, 20], 'permutations': 19,
        'seed': 7, 'edge_policy': 'conditional_on_observed_window', 'excluded_labels': [], 'jitter_sd': .1,
        'uncertainty_basis': 'synthetic scenario', 'sensitivity_repeats': 3}


def test_frozen_hypotheses_reproducible_and_degenerate(example):
    cfg = hypothesis_config(example)
    a = run(example, cfg, spatial_hypotheses)
    b = run(example, cfg, spatial_hypotheses, 'repeat')
    assert a == b
    assert a['excluded_observations'] == {'rna_not_measured': 2}
    assert a['results'][1]['status'] == 'degenerate_null'
    assert a['results'][1]['p_enrichment'] is None
    p = a['results'][0]['p_enrichment']
    assert p is None or .05 <= p <= 1


@pytest.mark.parametrize('mutation,match', [('hash', 'binding'), ('units', 'unit'), ('boundary', 'eligible')])
def test_hypothesis_guards(example, mutation, match):
    cfg = hypothesis_config(example)
    if mutation == 'hash': cfg['labels_sha256'] = '0'*64
    if mutation == 'units': cfg['coordinate_unit'] = 'um'
    if mutation == 'boundary': cfg['edge_policy'] = 'exclude_boundary_observations'
    with pytest.raises(ContractError, match=match):
        run(example, cfg, spatial_hypotheses)


def test_mcmicro_features_preserve_ids_missing_and_scale(example):
    from ifquant_platform.upstream_interchange import import_cell_features
    csv_file(example/'cells.csv', ['CellID', 'X_centroid', 'Y_centroid', 'CD3', 'Area'],
             [['001', 3.5, 4, '', 10], ['abc', 6, 8, 2.5, 20]])
    cfg = {'schema_version': 'ifquant.cell-features-import/1', 'csv': 'cells.csv',
        'subject': load_strict_json(example/'source.json')['subject'], 'frame_id': 'native', 'unit': 'pixel',
        'id_column': 'CellID', 'x_column': 'X_centroid', 'y_column': 'Y_centroid',
        'feature_columns': ['CD3', 'Area'], 'upstream_method': 'synthetic-MCQuant-compatible'}
    out = run(example, cfg, import_cell_features)
    assert out['cells'][0] == {'cell_id': '001', 'x': 3.5, 'y': 4., 'features': {'CD3': None, 'Area': 10.}}
    csv_file(example/'cells.csv', ['CellID', 'X_centroid', 'Y_centroid', 'CD3', 'Area'],
             [['001', 3.5, 4, '', 10], ['001', 6, 8, 2.5, 20]])
    with pytest.raises(ContractError, match='duplicate'):
        run(example, cfg, import_cell_features, 'duplicate')


def test_ngff_calibrated_window_with_global_translation(example):
    import zarr

    from ifquant_platform.upstream_interchange import import_ngff_window
    root = zarr.open_group(str(example/'input.zarr'), mode='w', zarr_format=2)
    pixels = np.arange(3*10*12, dtype=np.uint8).reshape(3, 10, 12)
    root.create_array('0', data=pixels, chunks=(3, 5, 6))
    root.attrs['multiscales'] = [{'version': '0.4', 'axes': [{'name': 'c', 'type': 'channel'},
        {'name': 'y', 'type': 'space', 'unit': 'micrometer'}, {'name': 'x', 'type': 'space', 'unit': 'micrometer'}],
        'datasets': [{'path': '0', 'coordinateTransformations': [{'type': 'scale', 'scale': [1, 3, 2]}]}],
        'coordinateTransformations': [{'type': 'scale', 'scale': [1, 2, 2]}, {'type': 'translation', 'translation': [0, 10, 20]}]}]
    cfg = {'schema_version': 'ifquant.ngff-window/1', 'store': 'input.zarr', 'multiscale': 0, 'level': 0,
        'window_xywh': [2, 1, 4, 3], 'subject': load_strict_json(example/'source.json')['subject'], 'modality': 'he', 'channel_semantics': 'rgb'}
    write_json(example/'ngff.json', cfg)
    import_ngff_window(example/'ngff.json', example/'ngff-out')
    import tifffile
    assert np.array_equal(tifffile.imread(example/'ngff-out/window.tif'), np.moveaxis(pixels[:, 1:4, 2:6], 0, -1))
    assert load_strict_json(example/'ngff-out/derivation.json')['window_origin_um_xy'] == [28, 16]
    assert load_strict_json(example/'ngff-out/source.json')['grid']['pixel_size_x_um'] == 4


def test_registration_heldout_errors_folds_and_no_cell_identity(example):
    from ifquant_platform.registration_qc import evaluate_registration
    columns = ['point_id', 'role', 'source_x', 'source_y', 'warped_x', 'warped_y', 'target_x', 'target_y']
    rows = [['fit', 'fit', 0, 0, 0, 0, 0, 0], ['test', 'evaluation', 2, 2, 2, 2, 3, 3],
            ['c0', 'observation', 3, 2, 3, 2, '', ''], ['c1', 'observation', 11, 9, 11, 9, '', '']]
    rows += [[f'p{i}', 'probe', x, y, x, y, '', ''] for i, (x, y) in enumerate([(0, 0), (4, 0), (0, 4), (4, 4)])]
    csv_file(example/'points.csv', columns, rows)
    cfg = {'schema_version': 'ifquant.registration-points/1', 'moving_source': 'source.json', 'fixed_source': 'source.json',
        'points_csv': 'points.csv', 'points_sha256': file_sha256(example/'points.csv'), 'section_relation': 'same_section',
        'method': 'synthetic', 'method_version': '1', 'run_reference': 'fixture', 'heldout_reference': 'fixture-independent',
        'max_local_distance_um': 5, 'probe_grid_xy': [2, 2]}
    out = run(example, cfg, evaluate_registration)
    assert out['landmark_errors']['evaluation']['rmse_um'] == pytest.approx(math.sqrt(13))
    assert out['deformation']['folded_triangles'] == 0
    assert out['points'][2]['local_error_proxy_um'] == pytest.approx(math.sqrt(13))
    assert out['points'][3]['local_support'] == 'unsupported'
    rows[-1][4] = -4
    csv_file(example/'points.csv', columns, rows)
    cfg['points_sha256'] = file_sha256(example/'points.csv')
    assert run(example, cfg, evaluate_registration, 'fold')['deformation']['folded_triangles'] > 0
    rows[1][2:4] = [0, 0]
    csv_file(example/'points.csv', columns, rows)
    cfg['points_sha256'] = file_sha256(example/'points.csv')
    with pytest.raises(ContractError, match='reused'):
        run(example, cfg, evaluate_registration, 'leak')


def test_gotags_never_invents_coverage_or_expression_genotype(example):
    from ifquant_platform.gotags_adapter import import_gotags
    csv_file(example/'gotags.csv', ['barcode', 'SIINFEKL_WPRE_status', 'SIINFEKL_WPRE_nanopore_status', 'reads'],
             [['c0', 'expression-only', 'positive', 2], ['c1', 'expression-only', 'negative', ''], ['c2', 'NA', 'NA', 0]])
    cfg = {'schema_version': 'ifquant.slide-gotags-mc38-ova/1', 'assay': 'assay.json', 'annotations_csv': 'gotags.csv',
        'id_column': 'barcode', 'source_reference': 'synthetic schema fixture based on author analysis columns',
        'nanopore_value_map': {'positive': 'alternate_detected', 'negative': 'reference_only'},
        'nanopore_coverage_column': 'reads', 'tcr_column': None, 'tcr_coverage_column': None}
    write_json(example/'gotags.json', cfg)
    import_gotags(example/'gotags.json', example/'gotags-out')
    out = load_strict_json(example/'gotags-out/context.json')
    assert out['observations'][0]['value'] == 'alternate_detected'
    assert out['observations'][1]['status'] == 'ambiguous' and out['observations'][1]['value'] is None
    assert out['observations'][3]['status'] == 'not_reported'


def test_tiff_pyramid_base_and_reduced_levels(tmp_path):
    import tifffile

    from ifquant_platform.imaging import ImageReader
    full = np.arange(64*80*3, dtype=np.uint8).reshape(64, 80, 3)
    with tifffile.TiffWriter(tmp_path/'pyramid.tif') as writer:
        writer.write(full, photometric='rgb', tile=(16, 16), subifds=1)
        writer.write(full[::2, ::2], photometric='rgb', tile=(16, 16), subfiletype=1)
    with ImageReader(tmp_path/'pyramid.tif', reader='tiff', level=0) as image:
        assert np.array_equal(image.read(4, 5, 20, 10), full[5:15, 4:24])
    with ImageReader(tmp_path/'pyramid.tif', reader='tiff', level=1) as image:
        assert image.scale_x == image.scale_y == 2
        assert np.array_equal(image.read(2, 3, 10, 10), full[::2, ::2][3:13, 2:12])


def test_morphology_anisotropic_calibration_and_endpoint_semantics(example):
    pytest.importorskip('shapely')
    from ifquant_platform.morphology_profiles import measure_profiles
    write_json(example/'profiles.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': 'cuff', 'properties': {'endpoint': 'cuff_area_per_inner_perimeter', 'compartment': 'airway', 'sampling_unit': 'r1'},
         'geometry': {'type': 'Polygon', 'coordinates': [[[0, 0], [10, 0], [10, 8], [0, 8], [0, 0]], [[2, 2], [2, 6], [8, 6], [8, 2], [2, 2]]]}},
        {'type': 'Feature', 'id': 'septum', 'properties': {'endpoint': 'septal_transect_length', 'compartment': 'alveolar', 'sampling_unit': 'r1'},
         'geometry': {'type': 'LineString', 'coordinates': [[0, 0], [3, 4]]}}]})
    cfg = {'schema_version': 'ifquant.morphology-profiles/1', 'source': 'source.json', 'geojson': 'profiles.geojson',
           'sampling_protocol': 'fixture', 'review': {'reviewer': 'fixture', 'status': 'accepted', 'data_kind': 'synthetic', 'reference': 'fixture'}}
    out = run(example, cfg, measure_profiles)
    assert out['profiles'][0]['cuff_area_um2'] == 336
    assert out['profiles'][0]['inner_perimeter_um'] == 48
    assert out['profiles'][0]['area_per_inner_perimeter_um'] == 7
    assert out['profiles'][1]['transect_length_um'] == pytest.approx(math.sqrt(180))


def test_association_uses_biological_units_and_strata(example):
    from ifquant_platform.associations import specimen_associations
    csv_file(example/'paired.csv', ['biological_unit_id', 'stratum', 'sampling_unit_id', 'x', 'y'],
        [['a', 'day3', 'r1', 0, 0], ['a', 'day3', 'r2', 2, 4], ['b', 'day3', 'r1', 2, 4],
         ['c', 'day3', 'r1', 3, 6], ['d', 'day3', 'r1', 4, 8], ['e', 'day3', 'r1', '', 10], ['f', 'day7', 'r1', 1, 1]])
    cfg = {'schema_version': 'ifquant.specimen-associations/1', 'csv': 'paired.csv', 'x_endpoint': 'area', 'y_endpoint': 'RNA',
           'aggregation': 'paired_unit_mean', 'sampling_reference': 'fixture', 'permutations': 99, 'seed': 1}
    out = run(example, cfg, specimen_associations)
    assert out['results'][0]['biological_units'] == 4 and out['results'][0]['spearman_rho'] == pytest.approx(1)
    assert out['results'][1]['p_two_sided'] is None
    assert out['excluded_incomplete_sampling_units'] == 1
    assert out['aggregated_units'][0]['mean_x'] == 1


def test_domain_baseline_rejects_inadequate_panel_and_clusters(example):
    from ifquant_platform.spatial_domains import domain_baselines
    cfg = {'schema_version': 'ifquant.domain-baselines/1', 'assay': 'assay.json', 'normalization_basis': 'selected_features',
           'minimum_features': 100, 'minimum_library': 0, 'components': 2, 'clusters': 2, 'seed': 2,
           'radius': 2., 'coordinate_unit': 'pixel', 'smoothing_weight': .3}
    with pytest.raises(ContractError, match='insufficient features'):
        run(example, cfg, domain_baselines)
    # Add a third independent feature to give two centered components.
    with (example/'var.csv').open('a') as f: f.write('g3,three\n')
    with (example/'counts.csv').open('a') as f:
        for i in range(8): f.write(f'c{i},g3,{(i % 3+1)**2}\n')
    import_assay(example/'import.json', example/'domain-assay.json')
    cfg.update(assay='domain-assay.json', minimum_features=3)
    out = run(example, cfg, domain_baselines, 'adequate')
    assert out['eligible_observations'] == 9
    assert len(out['results']['expression_only']['labels']) == 9
    assert {r['cluster'] for r in out['results']['graph_smoothed']['labels']} == {0, 1}


def test_valis_export_direction_and_resolution(example):
    from ifquant_platform.registration_qc import export_valis_points
    csv_file(example/'before.csv', ['point_id', 'role', 'source_x', 'source_y', 'target_x', 'target_y'],
             [['a', 'observation', 1, 2, '', '']])
    fixed = object()
    class Slide:
        def warp_xy_from_to(self, xy, target, **kwargs):
            assert target is fixed
            assert kwargs == {'src_slide_level': 0, 'src_pt_level': 0, 'dst_slide_level': 0, 'non_rigid': True}
            return xy + [3, 4]
    export_valis_points(Slide(), fixed, example/'before.csv', example/'after.csv')
    with (example/'after.csv').open() as f:
        row = next(csv.DictReader(f))
    assert float(row['warped_x']) == 4 and float(row['warped_y']) == 6
