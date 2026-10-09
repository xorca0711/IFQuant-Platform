"""Coordinate, exact-join and missingness invariants on explicitly synthetic data."""
import copy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ifquant_platform.canonical import ContractError, canonical_sha256, load_strict_json
from ifquant_platform.imaging import write_json
from ifquant_platform.molecular_context import attach_context
from ifquant_platform.spatial import (
    _link,
    _point_relation,
    apply_affine,
    import_assay,
    inverse_affine,
    link_spatial,
    validate_assay,
    validate_transform,
)
from ifquant_platform.spatial_demo import demo_spatial
from ifquant_platform.spatial_validation import validate_context, validate_links


@pytest.fixture
def sample(tmp_path):
    root = tmp_path/'demo'
    demo_spatial(root)
    return root


def inputs(root):
    return [load_strict_json(root/name) for name in ('assay.json', 'source.json', 'regions.json', 'transform.json')]


def test_completed_products_validate_without_rewriting(sample):
    assert validate_links(sample/'linked', sample/'assay.json', sample/'source.json', sample/'regions.json')['status'] == 'valid'
    assert validate_context(sample/'context.json', sample/'assay.json')['status'] == 'valid'


@pytest.mark.parametrize('product', ['links', 'context', 'csv', 'report'])
def test_completed_product_tampering_is_rejected(sample, product):
    if product == 'links':
        path = sample/'linked/links.json'
        doc = load_strict_json(path)
        doc['region_rna_counts'][0]['raw_count_sum'] += 1
        write_json(path, doc, replace=True)
    elif product == 'context':
        path = sample/'context.json'
        doc = load_strict_json(path)
        doc['observations'][0]['coverage'] = 999
        write_json(path, doc, replace=True)
    else:
        path = sample/'linked'/('links.csv' if product == 'csv' else 'report.html')
        path.write_text(path.read_text(encoding='utf-8')+'changed', encoding='utf-8')
    with pytest.raises(ContractError, match='differs'):
        if product == 'context':
            validate_context(sample/'context.json', sample/'assay.json')
        else:
            validate_links(sample/'linked', sample/'assay.json', sample/'source.json', sample/'regions.json')


def test_roundtrip_rotation_reflection_anisotropy():
    matrix = [[0, -2, 12], [-.5, 0, -7], [0, 0, 1]]
    point = [123.25, -9.5]
    assert apply_affine(inverse_affine(matrix), apply_affine(matrix, point)) == pytest.approx(point)
    with pytest.raises(ContractError, match='singular'):
        inverse_affine([[1, 2, 0], [2, 4, 0], [0, 0, 1]])


def test_demo_links_and_measured_zero_distinct_from_missing(sample):
    doc = load_strict_json(sample/'linked/links.json')
    assert doc['status_counts'] == {'linked': 3, 'boundary_ambiguous': 1, 'artifact': 1, 'outside_image': 1}
    counts = {(r['region_id'], r['feature_id']): r for r in doc['region_rna_counts']}
    assert counts[('left', 'f1')]['raw_count_sum'] == 5
    assert counts[('left', 'f2')]['raw_count_sum'] == 0
    assert counts[('left', 'f1')]['measured_observations'] == 1  # n6 is unassayed
    libraries = {r['observation_id']: r['total_counts'] for r in inputs(sample)[0]['statistics']['libraries']}
    assert libraries['n6'] is None and libraries['n5'] is None
    assert doc['landmark_errors']['evaluation']['max_um'] == 0


def test_snapshot_and_source_tampering_fail(sample):
    assay = inputs(sample)[0]
    assay['observations'][0]['x'] += 1
    with pytest.raises(ContractError, match='snapshot'):
        validate_assay(assay)
    (sample/'counts.csv').write_text('changed', encoding='utf-8')
    with pytest.raises(ContractError, match='bytes changed'):
        validate_assay(inputs(sample)[0])


@pytest.mark.parametrize('extra,match', [
    ('n1,f1,2\n', 'duplicate count'), ('unknown,f1,2\n', 'unknown observation'),
    ('n1,unknown,2\n', 'unknown observation'), ('n6,f1,2\n', 'unassayed'),
    ('n1,f2,-1\n', 'nonnegative'), ('n1,f2,1.5\n', 'nonnegative')])
def test_invalid_sparse_count_tables(sample, extra, match):
    with (sample/'counts.csv').open('a', encoding='utf-8') as stream:
        stream.write(extra)
    with pytest.raises(ContractError, match=match):
        import_assay(sample/'import.json', sample/'bad.json')
    assert not (sample/'bad.json').exists()


def test_ids_are_not_normalized_or_silently_deduplicated(sample):
    with (sample/'observations.csv').open('a', encoding='utf-8') as stream:
        stream.write('n1,1,1,measured\n')
    with pytest.raises(ContractError, match='duplicate observation'):
        import_assay(sample/'import.json', sample/'duplicate.json')
    text = (sample/'observations.csv').read_text().replace('n1,1,1,measured', ' n7,1,1,measured')
    (sample/'observations.csv').write_text(text)
    with pytest.raises(ContractError, match='whitespace'):
        import_assay(sample/'import.json', sample/'whitespace.json')


def test_transform_identity_units_and_independent_landmarks(sample):
    assay, source, _, transform = inputs(sample)
    transform['landmarks'][0]['to'] = [25, 32]
    errors = validate_transform(transform, assay, source)
    assert errors['evaluation']['max_um'] == pytest.approx((.5**2 + 1.6**2)**.5)
    transform['landmarks'].append({**transform['landmarks'][0], 'landmark_id': 'fit-duplicate', 'role': 'fit'})
    with pytest.raises(ContractError, match='reused'):
        validate_transform(transform, assay, source)
    transform = inputs(sample)[3]
    transform['from_frame'] = 'different-frame'
    with pytest.raises(ContractError, match='frame'):
        validate_transform(transform, assay, source)


def test_cross_subject_and_serial_section_scope(sample):
    assay, source, _, transform = inputs(sample)
    assay['subject']['subject_id'] = 'different-subject'
    transform['assay_sha256'] = canonical_sha256(assay)
    with pytest.raises(ContractError, match='cross-subject'):
        validate_transform(transform, assay, source)
    assay = inputs(sample)[0]
    assay['subject']['section_id'] = 'adjacent-section'
    transform['assay_sha256'] = canonical_sha256(assay)
    with pytest.raises(ContractError, match='section relation'):
        validate_transform(transform, assay, source)
    transform['section_relation'] = 'serial_section'
    transform['landmarks'] = []
    assert validate_transform(transform, assay, source)['evaluation']['max_um'] is None


def test_region_holes_boundary_distance_and_overlap(sample):
    rings = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
             [(2, 2), (2, 8), (8, 8), (8, 2), (2, 2)]]
    assert _point_relation(rings, 5, 5, .5, 2) == (False, 1.5)
    assert _point_relation(rings, 0, 5, .5, 2)[1] == 0
    assay, source, regions, transform = inputs(sample)
    duplicate = copy.deepcopy(regions['regions'][0])
    duplicate['region_id'] = 'overlap'
    regions['regions'].append(duplicate)
    links = _link(assay, source, regions, transform, .25)
    assert links[0]['link_status'] == 'overlapping_references' and links[0]['region_id'] is None


def test_boundary_uncertainty_abstains(sample):
    assay, source, regions, transform = inputs(sample)
    assay['observations'][0]['x'] = 29.8  # 0.2 um from shared native boundary
    assert _link(assay, source, regions, transform, .25)[0]['link_status'] == 'boundary_ambiguous'
    assert _link(assay, source, regions, transform, .1)[0]['link_status'] == 'linked'
    with pytest.raises(ContractError):
        _link(assay, source, regions, transform, -1)


def test_context_missingness_and_rna_genotype_meaning(sample):
    doc = load_strict_json(sample/'context.json')
    rows = {(r['observation_id'], r['modality']): r for r in doc['observations']}
    assert rows[('n1', 'tcr')]['status'] == 'not_reported' and rows[('n1', 'tcr')]['value'] is None
    assert rows[('n6', 'transcript_genotype')]['status'] == 'not_assayed'
    assert rows[('n3', 'transcript_genotype')]['status'] == 'ambiguous'
    assert rows[('n2', 'transcript_genotype')]['value'] == 'reference_only'
    assert 'not DNA wild type' in doc['interpretation']


@pytest.mark.parametrize('line,match', [
    ('unknown,tcr,target,measured,clone1,2\n', 'unknown observation'),
    ('n1,tcr,target,measured,clone1,0\n', 'positive observed coverage'),
    ('n1,tcr,target,not_assayed,clone1,\n', 'definitive value'),
    ('n1,transcript_genotype,target,measured,wild_type,2\n', 'DNA genotype')])
def test_invalid_molecular_calls(sample, line, match):
    path = sample/'bad-molecular.csv'
    path.write_text('observation_id,modality,target_id,status,value,coverage\n'+line, encoding='utf-8')
    with pytest.raises(ContractError, match=match):
        attach_context(sample/'assay.json', path, sample/'invalid-context.json')


def test_transform_binding_rejects_wrong_source(sample):
    transform = inputs(sample)[3]
    transform['source_sha256'] = '0'*64
    write_json(sample/'wrong-transform.json', transform)
    with pytest.raises(ContractError, match='identity'):
        link_spatial(sample/'assay.json', sample/'source.json', sample/'regions.json',
                     sample/'wrong-transform.json', sample/'invalid-run')
    assert not (sample/'invalid-run').exists()


def test_closed_schemas_match_demo(sample):
    root = Path(__file__).resolve().parents[1]/'contracts/spatial/v1'
    for filename, schema in [('import.json', 'spatial-import'), ('assay.json', 'spatial-assay'),
                              ('transform.json', 'affine-transform'), ('linked/links.json', 'spatial-links'),
                              ('context.json', 'molecular-context')]:
        spec = load_strict_json(root/(schema+'.schema.json'))
        Draft202012Validator.check_schema(spec)
        validator = Draft202012Validator(spec)
        data = load_strict_json(sample/filename)
        validator.validate(data)
        data['unexpected'] = 1
        assert not validator.is_valid(data)
