"""Generate editable synthetic plans for priority 3–5 tools and run them.

All identities, labels, geometry and gene programs are explicit engineering
fixtures. Nothing in this example supplies biological validation or a human review.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from ifquant_platform.canonical import canonical_sha256, file_sha256, load_strict_json
from ifquant_platform.imaging import register_image, write_json
from ifquant_platform.spatial import import_assay


def table(path, columns, rows):
    with path.open('x', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def demo(output):
    import numpy as np
    from PIL import Image

    from ifquant_platform.associations import specimen_associations
    from ifquant_platform.gotags_adapter import import_gotags
    from ifquant_platform.imaging_evaluation import compare_masks, reviewer_agreement
    from ifquant_platform.molecular_programs import score_programs
    from ifquant_platform.morphology_profiles import measure_profiles
    from ifquant_platform.registration_qc import evaluate_registration
    from ifquant_platform.spatial_domains import domain_baselines
    from ifquant_platform.spatial_statistics import spatial_hypotheses
    from ifquant_platform.upstream_interchange import import_cell_features
    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    Image.new('RGB', (64, 64), (220, 170, 190)).save(root/'image.png')
    subject = {'subject_id': 'synthetic-mouse', 'species': 'synthetic', 'specimen_id': 'synthetic-lung', 'section_id': 'section1'}
    register_image(root/'image.png', root/'source.json', **subject, pixel_size_x=1., pixel_size_y=2., reader='pillow')
    rng = np.random.default_rng(12)
    table(root/'observations.csv', ['observation_id', 'x', 'y', 'assay_status'],
          [[f'c{i:03}', 4+5*(i % 8), 4+5*(i//8), 'measured' if i < 30 else 'not_reported'] for i in range(32)])
    table(root/'features.csv', ['feature_id', 'feature_name'], [[f'g{i}', f'fixture_gene{i}'] for i in range(5)])
    table(root/'counts.csv', ['observation_id', 'feature_id', 'count'],
          [[f'c{i:03}', f'g{j}', int(rng.integers(1, 50))] for i in range(30) for j in range(5)])
    write_json(root/'assay-import.json', {'schema_version': 'ifquant.spatial-import/1', 'assay_id': 'fixture-rna', 'subject': subject,
        'entity_type': 'nucleus', 'coordinate_frame': {'frame_id': 'fixture-pixels', 'unit': 'pixel', 'axes': ['x', 'y'], 'origin': 'top_left', 'y_direction': 'down'},
        'observations_csv': 'observations.csv', 'features_csv': 'features.csv', 'counts_csv': 'counts.csv'})
    import_assay(root/'assay-import.json', root/'assay.json')
    reports = {}
    def execute(name, config, function, directory=False):
        write_json(root/(name+'.json'), config)
        reports[name] = function(root/(name+'.json'), root/(name+'-result' if directory else name+'-result.json'))
    write_json(root/'program-registry.json', {'schema_version': 'ifquant.gene-programs/1', 'registry_id': 'synthetic-v1', 'species': 'synthetic',
        'feature_id_namespace': 'fixture', 'programs': [{'program_id': 'arithmetic-example', 'feature_ids': ['g0', 'g1'], 'reference': 'synthetic arithmetic only',
        'min_coverage_fraction': 1., 'interpretation': 'not a biological gene program'}]})
    execute('programs', {'schema_version': 'ifquant.rna-program-analysis/1', 'assay': 'assay.json', 'programs': 'program-registry.json',
        'normalization_basis': 'selected_features', 'library_totals_csv': None, 'min_library_counts': 0, 'min_detected_features': 0}, score_programs)
    execute('domains', {'schema_version': 'ifquant.domain-baselines/1', 'assay': 'assay.json', 'normalization_basis': 'selected_features',
        'minimum_features': 5, 'minimum_library': 1, 'components': 2, 'clusters': 2, 'seed': 10, 'radius': 8., 'coordinate_unit': 'pixel', 'smoothing_weight': .3}, domain_baselines)
    table(root/'labels.csv', ['observation_id', 'specimen_id', 'region_id', 'coverage_stratum', 'label', 'boundary_distance'],
        [[f'c{i:03}', 'synthetic-lung', 'r1', 'adequate', 'reference' if i % 2 == 0 else 'target', 4] for i in range(32)])
    execute('hypotheses', {'schema_version': 'ifquant.spatial-hypotheses/1', 'assay': 'assay.json',
        'assay_sha256': canonical_sha256(load_strict_json(root/'assay.json')), 'labels_csv': 'labels.csv', 'labels_sha256': file_sha256(root/'labels.csv'),
        'coordinate_unit': 'pixel', 'pairs': [{'test_id': 'fixture-pair', 'reference': 'reference', 'target': 'target'}], 'radii': [8., 12.],
        'permutations': 99, 'seed': 10, 'edge_policy': 'conditional_on_observed_window', 'excluded_labels': [], 'jitter_sd': .5,
        'uncertainty_basis': 'synthetic perturbation scenario, not measured registration error', 'sensitivity_repeats': 5}, spatial_hypotheses)
    table(root/'gotags.csv', ['barcode', 'SIINFEKL_WPRE_status', 'SIINFEKL_WPRE_nanopore_status', 'reads', 'clonotype', 'tcr_reads'],
        [['c000', 'expression_detected', 'positive', 5, 'fixture-TCR', 3], ['c001', 'NA', 'negative', '', '', '']])
    execute('gotags', {'schema_version': 'ifquant.slide-gotags-mc38-ova/1', 'assay': 'assay.json', 'annotations_csv': 'gotags.csv', 'id_column': 'barcode',
        'source_reference': 'synthetic fixture of documented author columns', 'nanopore_value_map': {'positive': 'alternate_detected', 'negative': 'reference_only'},
        'nanopore_coverage_column': 'reads', 'tcr_column': 'clonotype', 'tcr_coverage_column': 'tcr_reads'}, import_gotags, directory=True)
    table(root/'points.csv', ['point_id', 'role', 'source_x', 'source_y', 'warped_x', 'warped_y', 'target_x', 'target_y'],
        [['f1', 'fit', 2, 2, 2, 2, 2, 2], ['e1', 'evaluation', 10, 10, 10, 10, 11, 10], ['c000', 'observation', 8, 8, 8, 8, '', '']]+
        [[f'p{i}', 'probe', x, y, x, y, '', ''] for i, (x, y) in enumerate([(0, 0), (63, 0), (0, 63), (63, 63)])])
    execute('registration', {'schema_version': 'ifquant.registration-points/1', 'moving_source': 'source.json', 'fixed_source': 'source.json',
        'points_csv': 'points.csv', 'points_sha256': file_sha256(root/'points.csv'), 'section_relation': 'same_section', 'method': 'synthetic', 'method_version': '1',
        'run_reference': 'fixture', 'heldout_reference': 'independent synthetic target', 'max_local_distance_um': 20., 'probe_grid_xy': [2, 2]}, evaluate_registration)
    reference = np.zeros((64, 64), dtype=np.uint8); reference[:, 32:] = 1
    prediction = reference.copy(); prediction[:, 31] = 1
    Image.fromarray(reference).save(root/'reference.png'); Image.fromarray(prediction).save(root/'prediction.png')
    execute('masks', {'schema_version': 'ifquant.mask-comparison/1', 'source': 'source.json', 'reference_mask': 'reference.png', 'prediction_mask': 'prediction.png',
        'classes': [0, 1], 'ignore_value': 255, 'reference_review': {'status': 'accepted', 'reviewer': 'fixture generator', 'at': '2026-10-09', 'data_kind': 'synthetic'},
        'method_id': 'fixture-one-column-error', 'sampling_protocol': 'synthetic full grid'}, compare_masks)
    table(root/'ratings.csv', ['unit_id', 'reviewer', 'endpoint_id', 'score'],
        [['u1', 'r1', 'fixture', 0], ['u1', 'r2', 'fixture', 0], ['u2', 'r1', 'fixture', 1], ['u2', 'r2', 'fixture', 2]])
    execute('agreement', {'schema_version': 'ifquant.ordinal-agreement/1', 'ratings_csv': 'ratings.csv', 'endpoint_id': 'fixture', 'ordered_scores': [0, 1, 2],
        'reviewers': ['r1', 'r2'], 'rubric_reference': 'synthetic ordinal rubric'}, reviewer_agreement)
    write_json(root/'profiles.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': 'cuff1', 'properties': {'endpoint': 'cuff_area_per_inner_perimeter', 'compartment': 'airway', 'sampling_unit': 'r1'},
         'geometry': {'type': 'Polygon', 'coordinates': [[[5, 5], [30, 5], [30, 30], [5, 30], [5, 5]], [[10, 10], [10, 25], [25, 25], [25, 10], [10, 10]]]}},
        {'type': 'Feature', 'id': 'septum1', 'properties': {'endpoint': 'septal_transect_length', 'compartment': 'alveolar', 'sampling_unit': 'r1'},
         'geometry': {'type': 'LineString', 'coordinates': [[40, 40], [43, 44]]}}]})
    execute('morphology', {'schema_version': 'ifquant.morphology-profiles/1', 'source': 'source.json', 'geojson': 'profiles.geojson', 'sampling_protocol': 'synthetic geometry',
        'review': {'reviewer': 'fixture generator', 'status': 'accepted', 'data_kind': 'synthetic', 'reference': 'analytic geometry'}}, measure_profiles)
    table(root/'paired.csv', ['biological_unit_id', 'stratum', 'sampling_unit_id', 'x', 'y'],
        [[f'synthetic_mouse{i}', 'fixture-day3', f'region{j}', i+j*.1, i*2+j*.2] for i in range(5) for j in range(2)])
    execute('associations', {'schema_version': 'ifquant.specimen-associations/1', 'csv': 'paired.csv', 'x_endpoint': 'synthetic-area', 'y_endpoint': 'synthetic-RNA',
        'aggregation': 'paired_unit_mean', 'sampling_reference': 'synthetic independent IDs', 'permutations': 99, 'seed': 12}, specimen_associations)
    table(root/'cells.csv', ['CellID', 'X_centroid', 'Y_centroid', 'CD3', 'Area'], [['001', 1, 2, 2.5, 6], ['002', 3, 4, '', 8]])
    execute('cell-features', {'schema_version': 'ifquant.cell-features-import/1', 'csv': 'cells.csv', 'subject': subject, 'frame_id': 'fixture-pixels', 'unit': 'pixel',
        'id_column': 'CellID', 'x_column': 'X_centroid', 'y_column': 'Y_centroid', 'feature_columns': ['CD3', 'Area'], 'upstream_method': 'synthetic MCQuant-compatible table'}, import_cell_features)
    write_json(root/'report.json', {'schema_version': 'ifquant.development-demo/1', 'data_kind': 'synthetic', 'scientific_validation': False, 'results': reports})
    return {'output': str(root), 'workflows': len(reports), 'scientific_validation': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(demo(args.output))
