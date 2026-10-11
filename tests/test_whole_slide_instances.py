"""Known-object seam/corner ground truth and interrupted package recovery."""
import csv
from contextlib import contextmanager

import pytest

np = pytest.importorskip('numpy')
tifffile = pytest.importorskip('tifffile')
from PIL import Image

from ifquant_platform import whole_slide_instances as slide
from ifquant_platform.canonical import (
    ContractError,
    canonical_sha256,
    file_sha256,
    load_strict_json,
)
from ifquant_platform.imaging import register_image, write_json


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    truth = np.zeros((145, 150), dtype=np.uint8)
    truth[20:45, 50:90] = 1                 # vertical seam
    truth[52:86, 105:123] = 2               # horizontal seam
    truth[56:80, 57:82] = 3                # four-tile corner
    truth[127:145, 129:150] = 4             # partial final tile / image edge
    truth[0:8, 0:8] = 5
    Image.fromarray(np.repeat(truth[..., None], 3, axis=2)).save(tmp_path/'image.png')
    register_image(tmp_path/'image.png', tmp_path/'source.json', subject_id='fixture', species='synthetic',
        specimen_id='s', section_id='p', pixel_size_x=.5, pixel_size_y=.5, reader='pillow')
    (tmp_path/'model.pt').write_bytes(b'fixture model stand-in')
    monkeypatch.setattr(slide, 'MODEL_SHA256', file_sha256(tmp_path/'model.pt'))
    monkeypatch.setattr(slide, '_binding', lambda cfg, source: {'config': canonical_sha256(cfg), 'source': canonical_sha256(source)})
    @contextmanager
    def predictor(*_):
        yield lambda image, scale: image[:, :, 0].astype(np.uint32)
    monkeypatch.setattr(slide, 'cpu_predictor', predictor)
    cfg = {'schema_version': 'ifquant.instanseg-slide/1', 'source': 'source.json', 'weights': 'model.pt',
           'tile_size': 64, 'halo': 16, 'threads': 1, 'overlap_iou': .5,
           'minimum_overlap_pixels': 4, 'maximum_objects': 1000}
    write_json(tmp_path/'plan.json', cfg)
    return tmp_path, truth


def test_seams_corners_partial_tiles_and_resume_are_invariant(fixture):
    root, truth = fixture
    result = slide.run_tiled_instanseg(root/'plan.json', root/'paused', max_tiles=2)
    assert result['status'] == 'paused' and result['completed_tiles'] == 2
    first = file_sha256(root/'paused/tiles/y000000000_x000000000.npy')
    result = slide.run_tiled_instanseg(root/'plan.json', root/'paused', resume=True)
    assert result['objects'] == 5 and result['foreground_pixels'] == int((truth > 0).sum())
    assert result['unresolved_seam_objects'] == 0
    assert file_sha256(root/'paused/tiles/y000000000_x000000000.npy') == first
    assert slide.validate_tiled_instanseg(root/'paused')['status'] == 'valid'
    slide.run_tiled_instanseg(root/'plan.json', root/'fresh')
    a, b = (load_strict_json(root/name/'package.json') for name in ('paused', 'fresh'))
    for name in ('instances.tif', 'objects.csv', 'matches.csv'):
        assert (root/'paused'/a['product']/name).read_bytes() == (root/'fresh'/b['product']/name).read_bytes()
    labels = tifffile.imread(root/'paused'/a['product']/'instances.tif')
    assert np.array_equal(labels > 0, truth > 0)
    assert len(np.unique(labels[truth == 3])) == 1
    with (root/'paused'/a['product']/'objects.csv').open() as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        yy, xx = np.nonzero(labels == int(row['object_id']))
        assert float(row['centroid_x_source_px']) == pytest.approx(xx.mean()+.5)
        assert float(row['centroid_y_source_px']) == pytest.approx(yy.mean()+.5)
        assert float(row['area_um2']) == len(xx)*.25
    with pytest.raises(ContractError, match='completed'):
        slide.run_tiled_instanseg(root/'plan.json', root/'paused', resume=True)


def test_overlap_union_rejects_transitive_same_tile_collapse():
    union = slide.IdentityUnion([0, 2, 4, 6])
    assert union.join(1, 3) == 'joined'
    assert union.join(3, 5) == 'joined'
    assert union.join(5, 2) == 'rejected_same_tile_collision'
    assert union.find(1) == union.find(5) and union.find(1) != union.find(2)


def test_narrow_grid_still_matches_vertical_neighbors():
    tiles = [{'core': [0, y, 40, 64]} for y in (0, 64, 128)]
    assert list(slide._neighbors(tiles, 64)) == [(1, 0), (2, 1)]


def test_tile_capacity_is_checked_before_inventory_allocation(fixture, monkeypatch):
    root, _ = fixture
    source = load_strict_json(root/'source.json')
    source['grid'].update(width=100_000, height=100_000)
    monkeypatch.setattr(slide, 'validate_source', lambda *_: source)
    monkeypatch.setattr(slide, 'tile_plan', lambda *a, **k: {})
    monkeypatch.setattr(slide, 'iter_tiles', lambda *_: pytest.fail('inventory allocated before capacity check'))
    with pytest.raises(ContractError, match='tile count capacity'):
        slide._validate_plan(load_strict_json(root/'plan.json'), root)


def test_process_lock_prevents_competing_writers_and_releases(tmp_path):
    lock = slide._acquire_lock(tmp_path/'lock')
    try:
        with pytest.raises(OSError):
            slide._acquire_lock(tmp_path/'lock')
    finally:
        lock.close()
    slide._acquire_lock(tmp_path/'lock').close()


def test_resume_detects_tampering_and_configuration_change(fixture):
    root, _ = fixture
    slide.run_tiled_instanseg(root/'plan.json', root/'run', max_tiles=1)
    cfg = load_strict_json(root/'plan.json'); cfg['overlap_iou'] = .7
    write_json(root/'changed.json', cfg)
    with pytest.raises(ContractError, match='resume inputs'):
        slide.run_tiled_instanseg(root/'changed.json', root/'run', resume=True)
    path = root/'run/tiles/y000000000_x000000000.npy'
    path.write_bytes(path.read_bytes()+b'drift')
    with pytest.raises(ContractError, match='bytes changed'):
        slide.run_tiled_instanseg(root/'plan.json', root/'run', resume=True)


def test_interrupted_uncommitted_tile_is_retained_and_recomputed(fixture):
    root, _ = fixture
    slide.run_tiled_instanseg(root/'plan.json', root/'run', max_tiles=1)
    (root/'run/tiles/y000000000_x000000064.npy').write_bytes(b'interrupted write')
    slide.run_tiled_instanseg(root/'plan.json', root/'run', resume=True)
    assert len(list((root/'run/tiles').glob('*.orphan-*'))) == 1
    assert slide.validate_tiled_instanseg(root/'run')['objects'] == 5


def test_completed_package_detects_mask_or_table_changes(fixture):
    root, _ = fixture
    slide.run_tiled_instanseg(root/'plan.json', root/'run')
    package = load_strict_json(root/'run/package.json')
    path = root/'run'/package['product']/'objects.csv'
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ContractError, match='binding differs'):
        slide.validate_tiled_instanseg(root/'run')
