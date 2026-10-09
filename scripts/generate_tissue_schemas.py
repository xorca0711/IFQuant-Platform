"""Generate the published closed JSON shapes; Python validators enforce semantic invariants too."""
import json
from pathlib import Path


def obj(**properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def array(items, minimum=0, maximum=None):
    result = {'type': 'array', 'items': items, 'minItems': minimum}
    if maximum is not None:
        result['maxItems'] = maximum
    return result


def const(value):
    return {'const': value}


def enum(*values):
    return {'enum': list(values)}


def nullable(shape):
    return {'anyOf': [shape, {'type': 'null'}]}


text = {'type': 'string', 'minLength': 1}
sha = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
positive = {'type': 'number', 'exclusiveMinimum': 0}
nonnegative = {'type': 'number', 'minimum': 0}
integer = {'type': 'integer', 'minimum': 0}
count = {'type': 'integer', 'minimum': 1}
anatomy = enum('alveolar_parenchyma', 'airway', 'vessel', 'pleura', 'unresolved')
file = obj(path=text, sha256=sha, size_bytes=count)
source = obj(schema_version=const('ifquant.image-source/1'),
             subject=obj(subject_id=text, species=text, specimen_id=text, section_id=text),
             modality=enum('he', 'fluorescence'), files=array(file, 1),
             selection=obj(reader=enum('tiff', 'pillow'), series=integer, level=integer),
             grid=obj(width=count, height=count, base_width=count, base_height=count, channels=count,
                      dtype=text, scale_x=positive, scale_y=positive,
                      pixel_size_x_um=positive, pixel_size_y_um=positive),
             calibration_source=const('user_declared_base_pixel_size'))
review = obj(status=enum('pending', 'accepted', 'rejected', 'uncertain'),
             reviewer=nullable(text), at=nullable(text), reason={'type': 'string'})
regions = obj(schema_version=const('ifquant.regions/1'), source_sha256=sha,
              coordinate_frame=const('base_image_pixels'), parent=nullable(obj(path=text, sha256=sha)),
              regions=array(obj(region_id=text, role=enum('reference', 'artifact', 'lesion', 'training'),
                                anatomy=anatomy, label=text, wkt=text, review=review), 1))
profile = obj(schema_version=const('ifquant.he-profile/1'),
              background_rgb=array({'type': 'number', 'exclusiveMinimum': 0, 'maximum': 255}, 3, 3),
              stain_vectors=array(array(nonnegative, 3, 3), 2, 2), tissue_od_sum_min=positive, description=text)
model = obj(schema_version=const('ifquant.he-color-model/1'),
            algorithm=enum('lab_kmeans', 'lab_nearest_centroid'), profile=profile,
            centers=array(array({'type': 'number'}, 2, 2), 2, 16), class_names=array(text, 2, 16),
            training=array(obj(source_sha256=sha, regions_sha256=nullable(sha), sample_count=count), 1),
            seed=integer, feature_space=const('srgb_d65_lab_ab'), scientific_validation=const(False))
plan = obj(schema_version=const('ifquant.tile-plan/1'), source_sha256=sha, width=count, height=count,
           tile_size={'type': 'integer', 'minimum': 1, 'maximum': 4096},
           halo={'type': 'integer', 'minimum': 0, 'maximum': 512},
           ownership=const('nonoverlapping_half_open_core'), coordinate_frame=const('selected_level_pixels'))
rubric = obj(schema_version=const('ifquant.ordinal-rubric/1'), rubric_id=text, description=text, reference=text,
             endpoints=array(obj(endpoint_id=text, anatomies=array(anatomy, 1),
                                 levels=array(obj(score=integer, label=text, definition=text), 2)), 1))
ordinal = obj(schema_version=const('ifquant.ordinal-review/1'), package_sha256=sha, rubric=rubric,
              rows=array(obj(region_id=text, endpoint_id=text, status=enum('pending', 'accepted', 'uncertain', 'not_applicable'),
                             score=nullable(integer), reviewer=nullable(text), at=nullable(text), reason={'type': 'string'})))
thresholds = obj(schema_version=const('ifquant.marker-thresholds/1'),
                 thresholds=array(obj(name=text, measurement_id=text, unit=text, minimum_inclusive=nonnegative)))
producer = obj(python=text, platform=text,
               code=obj(**{name: sha for name in ('canonical.py', 'imaging.py', 'histology.py',
                        'tissue_workflow.py', 'phase3_validation.py', 'package_validation.py')}),
               dependencies=obj(**{name: text for name in ('numpy', 'Pillow', 'tifffile', 'zarr')}))
package = obj(schema_version=const('ifquant.histology-package/1'),
              binding=obj(source_sha256=sha, model_sha256=sha, regions_sha256=sha, plan_sha256=sha,
                          dense_candidate_classes=array(text), producer=producer),
              files=array(obj(path=text, sha256=sha), 1), completed_tiles=count,
              status=const('engineering_complete'), scientific_validation=const(False), severity_authorized=const(False))


def main():
    root = Path(__file__).resolve().parents[1] / 'contracts/tissue/v1'
    root.mkdir(parents=True, exist_ok=True)
    for name, shape in {'image-source': source, 'regions': regions, 'he-profile': profile,
                        'he-color-model': model, 'tile-plan': plan, 'ordinal-rubric': rubric,
                        'ordinal-review': ordinal, 'marker-thresholds': thresholds,
                        'histology-package': package}.items():
        schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                  '$id': f'https://ifquant.org/contracts/tissue/v1/{name}.schema.json', **shape}
        (root / (name + '.schema.json')).write_text(json.dumps(schema, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
