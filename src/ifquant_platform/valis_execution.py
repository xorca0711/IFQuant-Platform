"""Live, pinned VALIS registration followed by the portable forward-point boundary."""
import importlib.metadata
import os
import time
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import integer, keys, require, validate_source, write_json
from .registration_qc import evaluate_registration, export_valis_points
from .spatial import file_record


def run_valis_pair(config_path, output):
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'moving_source', 'fixed_source', 'points_csv', 'section_relation',
        'heldout_reference', 'non_rigid', 'processed_size', 'seed', 'model_cache', 'probe_grid_xy',
        'max_local_distance_um'}, 'VALIS execution plan')
    require(cfg['schema_version'] == 'ifquant.valis-pair/1', 'unsupported VALIS execution plan')
    integer(cfg['seed'], 'seed', minimum=0)
    integer(cfg['processed_size'], 'processed size')
    require(256 <= cfg['processed_size'] <= 2048 and type(cfg['non_rigid']) is bool, 'invalid registration controls')
    base = Path(config_path).resolve().parent
    moving, fixed = [validate_source(load_strict_json(base/cfg[k])) for k in ('moving_source', 'fixed_source')]
    require(moving['subject']['subject_id'] == fixed['subject']['subject_id'] and
            moving['subject']['specimen_id'] == fixed['subject']['specimen_id'], 'paired specimen identity mismatch')
    same = moving['subject']['section_id'] == fixed['subject']['section_id']
    require(cfg['section_relation'] in ('same_section', 'serial_section', 'unknown') and same == (cfg['section_relation'] == 'same_section'),
            'section relation mismatch')
    for source in (moving, fixed):
        require(source['selection'] == {'reader': 'pillow', 'series': 0, 'level': 0} and
                source['modality'] in ('he', 'brightfield') and source['grid']['channels'] == 3 and
                source['grid']['dtype'] == 'uint8', 'VALIS profile requires explicit level-zero RGB brightfield PNG source')
    require(moving['files'][0]['path'] != fixed['files'][0]['path'], 'distinct paired input files required')
    require(importlib.metadata.version('valis-wsi') == '1.2.0', 'pinned VALIS 1.2.0 runtime required')
    points_record = file_record(base/cfg['points_csv'])
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(root/'plan.json', cfg)
    # VALIS instantiates default learned matchers at import. Keep those ancillary
    # downloads in an explicit cache; the configured VGG descriptor needs none.
    os.environ['TORCH_HOME'] = str((base/cfg['model_cache']).resolve())
    os.environ['MPLBACKEND'] = 'Agg'
    import cv2
    import numpy as np
    import torch
    from valis import feature_detectors, feature_matcher, non_rigid_registrars, registration

    from .valis_reader import CalibratedPNGReader
    require(torch.__version__.split('+')[0] == '2.8.0' and not torch.cuda.is_available(), 'pinned CPU torch runtime required')
    previous = torch.get_num_threads()
    torch.set_num_threads(4)
    cv2.setNumThreads(4)
    cv2.setRNGSeed(cfg['seed'])
    np.random.seed(cfg['seed'])
    paths = [source['files'][0]['path'] for source in (fixed, moving)]
    readers = {source['files'][0]['path']: [CalibratedPNGReader, {'pixel_size_um_xy': [
        source['grid']['pixel_size_x_um'], source['grid']['pixel_size_y_um']]}] for source in (fixed, moving)}
    start = time.perf_counter()
    try:
        detector = feature_detectors.VggFD()
        matcher = feature_matcher.Matcher(feature_detector=detector)
        registrar = registration.Valis(str(root), str(root/'registration'), name='pair', image_type='brightfield',
            img_list=paths, reference_img_f=paths[0], align_to_reference=True, imgs_ordered=True,
            feature_detector_cls=detector, matcher=matcher, matcher_for_sorting=matcher,
            non_rigid_registrar_cls=non_rigid_registrars.OpticalFlowWarper if cfg['non_rigid'] else None,
            max_image_dim_px=cfg['processed_size'], max_processed_image_dim_px=cfg['processed_size'],
            max_non_rigid_registration_dim_px=cfg['processed_size'], check_for_reflections=False)
        if not cfg['non_rigid'] and not hasattr(registrar, 'non_rigid_reg_kwargs'):
            # VALIS 1.2.0 cleanup accesses this field even when the constructor
            # skipped nonrigid setup. Supply only the empty cleanup container;
            # do not change registration or accept a partially failed result.
            registrar.non_rigid_reg_kwargs = {}
        rigid, nonrigid, errors = registrar.register(reader_dict=readers)
        require(rigid is not None and errors is not None and (not cfg['non_rigid'] or nonrigid is not None),
                'VALIS registration did not complete; inspect preserved runtime logs')
        errors.to_csv(root/'valis-fitted-summary.csv', index=False)
        # Evaluation targets were never supplied to the image registration.
        record = export_valis_points(registrar.get_slide(paths[1]), registrar.get_slide(paths[0]),
            base/cfg['points_csv'], root/'warped-points.csv', non_rigid=cfg['non_rigid'])
        require(file_record(base/cfg['points_csv']) == points_record, 'point input changed during registration')
        for source in (moving, fixed):
            validate_source(source)
        qc = {'schema_version': 'ifquant.registration-points/1', 'moving_source': str((base/cfg['moving_source']).resolve()),
            'fixed_source': str((base/cfg['fixed_source']).resolve()), 'points_csv': 'warped-points.csv',
            'points_sha256': record['output']['sha256'], 'section_relation': cfg['section_relation'],
            'method': 'VALIS', 'method_version': '1.2.0', 'run_reference': str(root/'plan.json'),
            'heldout_reference': cfg['heldout_reference'], 'max_local_distance_um': cfg['max_local_distance_um'],
            'probe_grid_xy': cfg['probe_grid_xy']}
        write_json(root/'qc-plan.json', qc)
        result = evaluate_registration(root/'qc-plan.json', root/'qc.json')
        report = {'schema_version': 'ifquant.valis-execution/1', 'plan': cfg, 'seconds': time.perf_counter()-start,
            'sources': {'moving': canonical_sha256(moving), 'fixed': canonical_sha256(fixed)},
            'point_input': points_record, 'point_export': record, 'qc': result,
            'method': 'VALIS VGG/OpenCV descriptor matching, similarity transform, optional optical flow; bounded PNG reader',
            'compatibility': 'VALIS 1.2.0 rigid-only cleanup container initialized when absent',
            'runtime': {name: importlib.metadata.version(name) for name in ('valis-wsi', 'numpy', 'torch', 'pyvips', 'scikit-image')},
            'ancillary_import_weights': [file_record(p) for p in sorted((Path(os.environ['TORCH_HOME'])/'hub/checkpoints').glob('*')) if p.is_file()],
            'scientific_validation': False}
        write_json(root/'result.json', report)
        return report
    finally:
        registration.kill_jvm()
        torch.set_num_threads(previous)
