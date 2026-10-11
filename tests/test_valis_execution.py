"""Fail before loading the optional engine when source semantics are invalid."""
import pytest

pytest.importorskip('numpy')
from PIL import Image

from ifquant_platform.canonical import ContractError
from ifquant_platform.imaging import register_image, write_json
from ifquant_platform.valis_execution import run_valis_pair


def test_generic_brightfield_is_explicit_and_section_identity_checked(tmp_path):
    for name in ('moving', 'fixed'):
        Image.new('RGB', (32, 32), 'white').save(tmp_path/f'{name}.png')
        register_image(tmp_path/f'{name}.png', tmp_path/f'{name}.json', subject_id='example-series-proxy',
            species='not_reported', specimen_id='example-series-proxy', section_id=name,
            pixel_size_x=8, pixel_size_y=8, reader='pillow', modality='brightfield')
    plan = {'schema_version': 'ifquant.valis-pair/1', 'moving_source': 'moving.json', 'fixed_source': 'fixed.json',
        'points_csv': 'points.csv', 'section_relation': 'same_section', 'heldout_reference': 'not_available',
        'non_rigid': True, 'processed_size': 1024, 'seed': 1, 'model_cache': 'cache', 'probe_grid_xy': None,
        'max_local_distance_um': 100}
    write_json(tmp_path/'plan.json', plan)
    with pytest.raises(ContractError, match='section relation'):
        run_valis_pair(tmp_path/'plan.json', tmp_path/'out')
    assert not (tmp_path/'out').exists()
