"""Publish stage 5/6 interchange shapes; runtime validators add identity and geometry checks."""
import json
from pathlib import Path

from generate_tissue_schemas import array, const, enum, integer, nullable, obj, sha, text

subject = obj(subject_id=text, species=text, specimen_id=text, section_id=text)
frame = obj(frame_id=text, unit=enum('pixel', 'um'), axes=const(['x', 'y']),
            origin=const('top_left'), y_direction=const('down'))
file = obj(path=text, sha256=sha, size_bytes=integer)
number = {'type': 'number'}
positive = {'type': 'number', 'minimum': 0}
point = array(number, 2, 2)
observation = obj(observation_id=text, x=number, y=number,
                  assay_status=enum('measured', 'not_assayed', 'failed', 'not_reported'))
config = obj(schema_version=const('ifquant.spatial-import/1'), assay_id=text, subject=subject,
             entity_type=enum('spot', 'nucleus', 'cell'), coordinate_frame=frame,
             observations_csv=text, features_csv=text, counts_csv=text)
assay = obj(schema_version=const('ifquant.spatial-assay/1'), assay_id=text, subject=subject,
            entity_type=enum('spot', 'nucleus', 'cell'), coordinate_frame=frame,
            inputs=obj(observations=file, features=file, counts=file),
            observations=array(observation, 1, 200000),
            features=array(obj(feature_id=text, feature_name=text), 1, 100000),
            matrix_semantics=const('raw_rna_counts_sparse_zero_for_measured_observations_only'),
            scientific_validation=const(False),
            statistics=obj(count_rows=integer, nonzero_rows=integer,
                           libraries=array(obj(observation_id=text, total_counts=nullable(integer)), 1)))
transform = obj(schema_version=const('ifquant.affine-transform/1'), assay_sha256=sha,
                source_sha256=sha, from_frame=text, to_frame=const('base_image_pixels'),
                section_relation=enum('same_section', 'serial_section'), method=const('provided_affine'),
                matrix=array(array(number, 3, 3), 3, 3),
                landmarks=array(obj(**{'landmark_id': text, 'role': enum('fit', 'evaluation'), 'from': point, 'to': point})))
error = obj(count=integer, rmse_um=nullable(positive), max_um=nullable(positive))
statuses = ['outside_image', 'artifact', 'boundary_ambiguous', 'overlapping_references', 'outside_reference', 'linked']
link = obj(observation_id=text, entity_type=enum('spot', 'nucleus', 'cell'),
           assay_status=enum('measured', 'not_assayed', 'failed', 'not_reported'), x_base_px=number, y_base_px=number,
           x_um=number, y_um=number, link_status=enum(*statuses), region_id=nullable(text),
           reference_review=nullable(enum('pending', 'accepted', 'uncertain')))
links = obj(schema_version=const('ifquant.spatial-links/1'), assay_sha256=sha, source_sha256=sha,
            regions_sha256=sha, transform=transform, landmark_errors=obj(fit=error, evaluation=error),
            boundary_uncertainty_um=positive, numeric_roundtrip_max_input_units=positive,
            links=array(link, 1), region_rna_counts=array(obj(region_id=text, feature_id=text,
                                                            raw_count_sum=integer, measured_observations=integer)),
            status_counts={'type': 'object', 'properties': {s: integer for s in statuses}, 'additionalProperties': False},
            registration_status=enum('evaluation_landmarks_supplied', 'not_evaluated'),
            assignment_semantics=const('point_center_to_region_only; no cell identity or spot-area deconvolution'),
            scientific_validation=const(False), producer_sha256=sha)
modality = enum('transcript_genotype', 'tcr')
call_status = enum('measured', 'not_assayed', 'failed', 'ambiguous', 'not_reported')
context = obj(schema_version=const('ifquant.molecular-context/1'), assay_sha256=sha,
              entity_type=enum('spot', 'nucleus', 'cell'), input=file,
              targets=array(obj(modality=modality, target_id=text), 1),
              observations=array(obj(observation_id=text, modality=modality, target_id=text,
                                     status=call_status, value=nullable(text), coverage=nullable(integer)), 1, 1000000),
              status_counts=array(obj(status=call_status, count=integer)),
              join_semantics=const('exact observation ID within one assay; no coordinate-nearest or cross-section cell matching'),
              interpretation=const('RNA reference-only is not DNA wild type; clonotype presence does not establish antigen specificity'),
              scientific_validation=const(False), producer_sha256=sha)


def main():
    root = Path(__file__).resolve().parents[1]/'contracts/spatial/v1'
    root.mkdir(parents=True, exist_ok=True)
    for name, shape in {'spatial-import': config, 'spatial-assay': assay, 'affine-transform': transform,
                        'spatial-links': links, 'molecular-context': context}.items():
        schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                  '$id': f'https://ifquant.org/contracts/spatial/v1/{name}.schema.json', **shape}
        (root/(name+'.schema.json')).write_text(json.dumps(schema, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
