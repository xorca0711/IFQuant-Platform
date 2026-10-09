"""Engineering invariants, not biological accuracy tests."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
import tifffile

from ifquant_platform.canonical import ContractError, canonical_sha256, load_strict_json
from ifquant_platform.histology import (
    default_profile,
    export_geojson,
    features,
    fit_model,
    import_geojson,
    region_mask,
    validate_profile,
    validate_regions,
)
from ifquant_platform.imaging import (
    ImageReader,
    iter_tiles,
    register_image,
    tile_plan,
    validate_source,
    write_json,
)
from ifquant_platform.phase3_validation import _canonical_wkt
from ifquant_platform.tissue_reporting import (
    cell_report,
    radius_neighbors,
    review_template,
    specimen_report,
    validate_review,
)
from ifquant_platform.tissue_workflow import run_histology, validate_histology


def region(rid, role, wkt, *, accepted=False, label=None):
    return {'region_id': rid, 'role': role, 'anatomy': 'alveolar_parenchyma',
            'label': label or rid, 'wkt': _canonical_wkt('POLYGON', wkt, rid),
            'review': {'status': 'accepted' if accepted else 'pending',
                       'reviewer': 'synthetic-reviewer' if accepted else None,
                       'at': '2026-10-09T00:00:00Z' if accepted else None,
                       'reason': 'synthetic test only'}}


@pytest.fixture
def sample(tmp_path):
    y, x = np.indices((48, 64))
    rgb = np.full((48, 64, 3), 250, dtype=np.uint8)
    rgb[(x % 8) < 4] = [216, 152, 189]
    rgb[(x > 32) & (y > 12)] = [100, 50, 110]
    rgb[:4] = [20, 60, 160]
    tifffile.imwrite(tmp_path / 'source.tif', rgb, photometric='rgb', tile=(16, 16))
    register_image(tmp_path / 'source.tif', tmp_path / 'source.json', subject_id='s1', species='synthetic',
                   specimen_id='lung1', section_id='section1', pixel_size_x=.5, pixel_size_y=.8)
    source = load_strict_json(tmp_path / 'source.json')
    regions = {'schema_version': 'ifquant.regions/1', 'source_sha256': canonical_sha256(source),
               'coordinate_frame': 'base_image_pixels', 'parent': None,
               'regions': [region('reference', 'reference', 'POLYGON ((0 0, 64 0, 64 48, 0 48, 0 0))'),
                           region('artifact', 'artifact', 'POLYGON ((0 0, 64 0, 64 4, 0 4, 0 0))')]}
    write_json(tmp_path / 'regions.json', regions)
    fit_model(tmp_path / 'source.json', tmp_path / 'model.json', regions_path=tmp_path / 'regions.json', clusters=2)
    return tmp_path, source, regions, rgb


def run(sample, name='run', **kwargs):
    root = sample[0]
    run_histology(root / 'source.json', root / 'model.json', root / 'regions.json', root / name, **kwargs)
    return root / name


def test_windowed_pyramid_and_calibration(tmp_path):
    rgb = np.arange(64 * 48 * 3, dtype=np.uint8).reshape(48, 64, 3)
    path = tmp_path / 'pyramid.ome.tif'
    with tifffile.TiffWriter(path, ome=True) as writer:
        writer.write(rgb, subifds=1, photometric='rgb', tile=(16, 16), metadata={'axes': 'YXS'})
        writer.write(rgb[::2, ::2], subfiletype=1, photometric='rgb', tile=(16, 16))
    with ImageReader(path, reader='tiff', level=1) as reader:
        assert (reader.width, reader.height, reader.scale_x) == (32, 24, 2)
        np.testing.assert_array_equal(reader.read(2, 3, 5, 4), rgb[6:14:2, 4:14:2])
        with pytest.raises(ContractError, match='bounds'):
            reader.read(30, 20, 10, 10)
    register_image(path, tmp_path / 'source.json', subject_id='s', species='synthetic',
                   specimen_id='lung', section_id='section', pixel_size_x=.4, pixel_size_y=.7, level=1)
    source = load_strict_json(tmp_path / 'source.json')
    assert source['grid']['pixel_size_x_um'] == .8
    assert source['grid']['pixel_size_y_um'] == 1.4
    square = region('square', 'reference', 'POLYGON ((0 0, 8 0, 8 8, 0 8, 0 0))')
    assert region_mask(square, source, [0, 0, 32, 24]).sum() == 16


def test_source_identity_and_calibration_fail_closed(sample):
    root, source, _, _ = sample
    invalid = copy.deepcopy(source)
    invalid['grid']['pixel_size_x_um'] = 0
    with pytest.raises(ContractError):
        validate_source(invalid)
    invalid = copy.deepcopy(source)
    invalid['grid']['scale_x'] = 2
    with pytest.raises(ContractError, match='scale'):
        validate_source(invalid)
    with (root / 'source.tif').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ContractError, match='bytes changed'):
        validate_source(source)


def test_companion_members_are_content_bound(sample):
    root, _, _, _ = sample
    member = root / 'companion.ets'
    member.write_bytes(b'synthetic member')
    register_image(root / 'source.tif', root / 'multi.json', subject_id='s', species='synthetic',
                   specimen_id='lung', section_id='section', pixel_size_x=.5, pixel_size_y=.5,
                   members=[member])
    source = load_strict_json(root / 'multi.json')
    member.write_bytes(b'changed member')
    with pytest.raises(ContractError):
        validate_source(source)


def test_tile_ownership_and_large_plan(sample):
    _, source, _, _ = sample
    coverage = np.zeros((48, 64), int)
    for tile in iter_tiles(tile_plan(source, tile_size=17, halo=3)):
        x, y, w, h = tile['core']
        rx, ry, rw, rh = tile['read']
        assert rx <= x and ry <= y and rx + rw >= x + w and ry + rh >= y + h
        coverage[y:y+h, x:x+w] += 1
    assert np.all(coverage == 1)
    large = copy.deepcopy(source)
    large['grid'].update(width=100000, height=80000, base_width=100000, base_height=80000)
    plan = tile_plan(large, tile_size=1024)
    assert sum(t['core'][2] * t['core'][3] for t in iter_tiles(plan)) == 8_000_000_000
    assert len(json.dumps(plan)) < 500


def test_polygon_hole_and_invalid_topology(sample):
    _, source, regions, _ = sample
    hole = region('hole', 'reference', 'POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0), (2 2, 2 8, 8 8, 8 2, 2 2))')
    assert region_mask(hole, source, [0, 0, 64, 48]).sum() == 64
    bad = copy.deepcopy(regions)
    bad['regions'][0]['wkt'] = 'POLYGON ((0 0, 10 10, 10 0, 0 10, 0 0))'
    with pytest.raises(ContractError):
        validate_regions(bad, source)


def test_pixel_features_are_position_independent(sample):
    _, _, _, rgb = sample
    profile = default_profile()
    lab, he, tissue = features(rgb, profile)
    shifted = np.roll(rgb, 11, axis=1)
    other = features(shifted, profile)
    for expected, actual in zip((lab, he, tissue), other):
        np.testing.assert_allclose(np.roll(expected, 11, axis=1), actual)
    assert int(tissue.sum()) == int(other[2].sum())  # counts, never sums of pixel indices
    profile['stain_vectors'][1] = profile['stain_vectors'][0]
    with pytest.raises(ContractError, match='independent'):
        validate_profile(profile)


def test_frozen_fit_reproducible(sample):
    root = sample[0]
    fit_model(root / 'source.json', root / 'model2.json', regions_path=root / 'regions.json', clusters=2)
    assert load_strict_json(root / 'model.json') == load_strict_json(root / 'model2.json')


def test_tile_size_invariance_and_denominators(sample):
    a = run(sample, 'a', tile_size=17, dense_classes=['cluster_0'])
    b = run(sample, 'b', tile_size=64, dense_classes=['cluster_0'])
    assert validate_histology(a)['status'] == 'valid'
    assert load_strict_json(a / 'measurements.json') == load_strict_json(b / 'measurements.json')
    row = load_strict_json(a / 'measurements.json')['regions'][0]
    assert row['reference_pixels'] == 64 * 48
    assert row['artifact_pixels'] == 64 * 4
    assert row['eligible_reference_area_um2'] == pytest.approx(64 * 44 * .5 * .8)
    assert row['tissue_pixels'] + row['airspace_candidate_pixels'] == 64 * 44
    assert row['severity_score'] is None and row['annotated_lesion_fraction_of_tissue'] is None
    assert row['scientific_validation'] is False


def test_resume_matches_uninterrupted_and_refuses_changed_inputs(sample):
    root = sample[0]
    a = run(sample, 'resume', tile_size=16, max_tiles=2)
    assert not (a / 'package.json').exists()
    assert load_strict_json(a / 'run-state.json')['status'] == 'paused'
    with pytest.raises(ContractError, match='changed'):
        run(sample, 'resume', resume=True, tile_size=32)
    run(sample, 'resume', resume=True, tile_size=16)
    b = run(sample, 'fresh', tile_size=16)
    assert load_strict_json(a / 'measurements.json') == load_strict_json(b / 'measurements.json')
    for mask in (a / 'tiles').glob('*.npy'):
        assert mask.read_bytes() == (b / 'tiles' / mask.name).read_bytes()
    with pytest.raises(ContractError, match='completed'):
        run_histology(root / 'source.json', root / 'model.json', root / 'regions.json', a, resume=True, tile_size=16)


@pytest.mark.parametrize('artifact', ['measurements.json', 'tiles/y000000000_x000000000.npy', 'measurements.csv'])
def test_package_tamper_rejected(sample, artifact):
    out = run(sample)
    with (out / artifact).open('ab') as stream:
        stream.write(b'tamper')
    with pytest.raises(ContractError, match='changed artifact'):
        validate_histology(out)


def test_failed_overlap_is_logged(sample):
    root, _, regions, _ = sample
    regions['regions'].append(region('overlap', 'reference', 'POLYGON ((1 1, 20 1, 20 20, 1 20, 1 1))'))
    write_json(root / 'regions.json', regions, replace=True)
    with pytest.raises(ContractError, match='overlap'):
        run(sample)
    state = load_strict_json(root / 'run/run-state.json')
    assert state['status'] == 'failed' and 'overlap' in state['error']
    assert not (root / 'run/package.json').exists() and not (root / 'run/run.lock').exists()


def test_geojson_revision_roundtrip_and_parent_tamper(sample):
    root, source, regions, _ = sample
    write_json(root / 'annotations.geojson', export_geojson(source, regions))
    import_geojson(root / 'source.json', root / 'annotations.geojson', root / 'correction.json', parent=root / 'regions.json')
    correction = load_strict_json(root / 'correction.json')
    assert [r['wkt'] for r in correction['regions']] == [r['wkt'] for r in regions['regions']]
    assert all(r['review']['status'] == 'pending' for r in correction['regions'])
    regions['regions'][0]['label'] = 'changed'
    write_json(root / 'regions.json', regions, replace=True)
    with pytest.raises(ContractError, match='parent region'):
        validate_regions(correction, source)


def test_supervised_requires_accepted_labels(sample):
    root, _, regions, _ = sample
    regions['regions'] += [region('a', 'training', 'POLYGON ((0 4, 25 4, 25 48, 0 48, 0 4))', label='pink'),
                           region('b', 'training', 'POLYGON ((40 14, 64 14, 64 48, 40 48, 40 14))', label='purple')]
    write_json(root / 'training.json', regions)
    with pytest.raises(ContractError, match='insufficient'):
        fit_model(root / 'source.json', root / 'supervised.json', regions_path=root / 'training.json', supervised=True)
    for r in regions['regions'][2:]:
        r['review'] = {'status': 'accepted', 'reviewer': 'synthetic', 'at': '2026-10-09T00:00:00Z', 'reason': 'test'}
    write_json(root / 'training.json', regions, replace=True)
    fit_model(root / 'source.json', root / 'supervised.json', regions_path=root / 'training.json', supervised=True)
    model = load_strict_json(root / 'supervised.json')
    assert model['algorithm'] == 'lab_nearest_centroid' and model['class_names'] == ['pink', 'purple']


def rubric():
    return {'schema_version': 'ifquant.ordinal-rubric/1', 'rubric_id': 'synthetic',
            'description': 'Testing only', 'reference': 'No biological meaning',
            'endpoints': [{'endpoint_id': 'synthetic-feature', 'anatomies': ['alveolar_parenchyma'],
                           'levels': [{'score': 0, 'label': 'zero', 'definition': 'Synthetic zero'},
                                      {'score': 1, 'label': 'one', 'definition': 'Synthetic one'}]}]}


def test_review_missingness_completeness_and_no_ordinal_average(sample):
    root = sample[0]
    out = run(sample)
    write_json(root / 'rubric.json', rubric())
    review_template(out, root / 'rubric.json', root / 'review.json')
    form = load_strict_json(root / 'review.json')
    rows = load_strict_json(out / 'measurements.json')['regions']
    validate_review(form, canonical_sha256(load_strict_json(out / 'package.json')), rows)
    bad = copy.deepcopy(form)
    bad['rows'] = []
    with pytest.raises(ContractError, match='incomplete'):
        validate_review(bad, form['package_sha256'], rows)
    bad = copy.deepcopy(form)
    bad['rows'][0]['score'] = 0
    with pytest.raises(ContractError, match='unaccepted'):
        validate_review(bad, form['package_sha256'], rows)
    specimen_report([out], root / 'report', reviews=[root / 'review.json'])
    summary = load_strict_json(root / 'report/summary.json')
    ordinal = next(iter(summary['specimens'][0]['ordinal'].values()))
    assert ordinal == {'accepted_score_counts': {}, 'status_counts': {'pending': 1}}
    assert 'no arithmetic average' in summary['ordinal_aggregation']
    form['rows'][0].update(status='accepted', score=1, reviewer='synthetic-reviewer',
                           at='2026-10-09T00:00:00Z', reason='Synthetic software test only')
    write_json(root / 'accepted.json', form)
    specimen_report([out], root / 'accepted-report', reviews=[root / 'accepted.json'])
    accepted = load_strict_json(root / 'accepted-report/summary.json')
    tally = next(iter(accepted['specimens'][0]['ordinal'].values()))
    assert tally == {'accepted_score_counts': {'1': 1}, 'status_counts': {'accepted': 1}}
    assert accepted['rubrics'][canonical_sha256(form['rubric'])] == form['rubric']
    bad = copy.deepcopy(form)
    bad['rows'][0]['score'] = 5
    with pytest.raises(ContractError, match='outside rubric'):
        validate_review(bad, form['package_sha256'], rows)
    bad['rows'][0]['score'] = 1
    bad['rows'][0]['at'] = 'invalidZ'
    with pytest.raises(ContractError, match='timestamp'):
        validate_review(bad, form['package_sha256'], rows)
    with pytest.raises(ContractError, match='duplicate section'):
        specimen_report([out, out], root / 'duplicate')


def test_specimen_pooling_is_area_weighted(sample):
    root, source, _, _ = sample
    a = run(sample, 'section1', dense_classes=['cluster_0'])
    source['subject']['section_id'] = 'section2'
    write_json(root / 'source2.json', source)
    regions = load_strict_json(root / 'regions.json')
    regions['source_sha256'] = canonical_sha256(source)
    regions['regions'][0] = region('small', 'reference', 'POLYGON ((0 4, 20 4, 20 40, 0 40, 0 4))')
    write_json(root / 'regions2.json', regions)
    run_histology(root / 'source2.json', root / 'model.json', root / 'regions2.json', root / 'section2', dense_classes=['cluster_0'])
    specimen_report([a, root / 'section2'], root / 'pooled')
    doc = load_strict_json(root / 'pooled/summary.json')
    group = doc['specimens'][0]
    assert len(doc['specimens']) == 1 and len(group['section_ids']) == 2
    expected = sum(r['dense_candidate_area_um2'] for r in doc['sections']) / sum(r['tissue_material_area_um2'] for r in doc['sections'])
    assert group['dense_candidate_fraction_of_tissue'] == expected


def test_radius_matches_brute_force_and_separates_roi():
    points = [(0, 0), (3, 4), (5.1, 0), (0, 0)]
    groups = ['a', 'a', 'a', 'b']
    assert radius_neighbors(points, groups, 5) == [[1], [0, 2], [1], []]
    with pytest.raises(ContractError, match='comparison limit'):
        radius_neighbors([(0, 0)] * 10, ['a'] * 10, 5, max_comparisons=2)


def test_cell_report_calibration_missing_markers_and_zero_neighbors(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / 'validation/fixtures/minimal-cell-package'
    rules = {'schema_version': 'ifquant.marker-thresholds/1', 'thresholds': [
        {'name': 'DAPI-positive', 'measurement_id': 'dapi_cell_mean', 'unit': 'native_sample_value', 'minimum_inclusive': 100},
        {'name': 'missing-marker', 'measurement_id': 'absent', 'unit': 'native_sample_value', 'minimum_inclusive': 0}]}
    write_json(tmp_path / 'thresholds.json', rules)
    cell_report(fixture, tmp_path / 'report', thresholds_path=tmp_path / 'thresholds.json')
    row = json.loads((tmp_path / 'report/cells.jsonl').read_text())
    assert (row['x_um'], row['y_um'], row['neighbor_count']) == (25, 25, 0)
    assert row['marker_phenotype'] == {'DAPI-positive': True, 'missing-marker': None}
    summary = load_strict_json(tmp_path / 'report/summary.json')
    assert summary['marker_counts']['missing-marker']['measured'] == 0


def test_atomic_json_never_overwrites_existing(tmp_path):
    path = tmp_path / 'immutable.json'
    write_json(path, {'first': True})
    with pytest.raises((ContractError, FileExistsError)):
        write_json(path, {'second': True})
    assert load_strict_json(path) == {'first': True}


def test_interrupt_records_cancellation(sample, monkeypatch):
    import ifquant_platform.tissue_workflow as workflow

    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(workflow, 'features', interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(sample)
    assert load_strict_json(sample[0] / 'run/run-state.json')['status'] == 'cancelled'
    assert not (sample[0] / 'run/run.lock').exists()


def test_published_schemas_cover_runtime_documents(sample):
    from jsonschema import Draft202012Validator

    out = run(sample)
    schema_root = Path(__file__).resolve().parents[1] / 'contracts/tissue/v1'
    for schema in schema_root.glob('*.schema.json'):
        Draft202012Validator.check_schema(load_strict_json(schema))
    for document, schema_name in [('source.json', 'image-source'), ('model.json', 'he-color-model'),
                                  ('regions.json', 'regions'), ('tile-plan.json', 'tile-plan'),
                                  ('package.json', 'histology-package')]:
        validator = Draft202012Validator(load_strict_json(schema_root / (schema_name + '.schema.json')))
        data = load_strict_json(out / document)
        validator.validate(data)
        data['unexpected'] = 'reject'
        assert not validator.is_valid(data)


def test_working_memory_limit_is_explicit(sample):
    with pytest.raises(ContractError, match='memory limit'):
        run(sample, tile_size=1024)
