"""Calibrated 2D cuff profiles and reviewed septal transects, not stereology."""
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import keys, require, validate_source, write_json
from .spatial import exact_id, file_record


def measure_profiles(config_path, output):
    from shapely import affinity
    from shapely.geometry import LineString, Polygon, shape
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'source', 'geojson', 'sampling_protocol', 'review'}, 'morphology profiles')
    require(cfg['schema_version'] == 'ifquant.morphology-profiles/1', 'unsupported morphology profiles')
    exact_id(cfg['sampling_protocol'], 'sampling protocol')
    keys(cfg['review'], {'reviewer', 'status', 'data_kind', 'reference'}, 'morphology review')
    require(cfg['review']['status'] == 'accepted' and cfg['review']['data_kind'] in ('synthetic', 'reviewed_reference'), 'reviewed/synthetic geometry required')
    for key in ('reviewer', 'reference'):
        exact_id(cfg['review'][key], key)
    base = Path(config_path).resolve().parent
    source = validate_source(load_strict_json(base/cfg['source']))
    path = base/cfg['geojson']
    record = file_record(path)
    features = load_strict_json(path)
    require(features.get('type') == 'FeatureCollection' and isinstance(features.get('features'), list) and
            0 < len(features['features']) <= 10_000, 'bounded FeatureCollection required')
    sx = source['grid']['pixel_size_x_um']/source['grid']['scale_x']
    sy = source['grid']['pixel_size_y_um']/source['grid']['scale_y']
    rows, seen = [], set()
    for feature in features['features']:
        fid = exact_id(feature.get('id'), 'morphology profile ID')
        require(fid not in seen, 'duplicate profile ID')
        seen.add(fid)
        prop = feature['properties']
        keys(prop, {'endpoint', 'compartment', 'sampling_unit'}, 'profile properties')
        for value in prop.values():
            exact_id(value, 'profile property')
        geom = shape(feature['geometry'])
        require(not geom.is_empty and geom.is_valid, 'invalid morphology geometry; no silent repair')
        minx, miny, maxx, maxy = geom.bounds
        require(minx >= 0 and miny >= 0 and maxx <= source['grid']['base_width'] and maxy <= source['grid']['base_height'], 'profile outside base image')
        physical = affinity.scale(geom, xfact=sx, yfact=sy, origin=(0, 0))
        if prop['endpoint'] == 'cuff_area_per_inner_perimeter':
            require(isinstance(physical, Polygon) and len(physical.interiors) == 1 and
                    prop['compartment'] in ('airway', 'vessel'), 'cuff requires airway/vessel polygon with one inner profile')
            perimeter = physical.interiors[0].length
            require(perimeter > 0, 'zero inner profile perimeter')
            result = {'cuff_area_um2': physical.area, 'inner_perimeter_um': perimeter,
                      'area_per_inner_perimeter_um': physical.area/perimeter,
                      'interpretation': '2D cuff burden normalized by inner profile perimeter; not radial thickness'}
        elif prop['endpoint'] == 'septal_transect_length':
            require(isinstance(physical, LineString) and physical.length > 0 and prop['compartment'] == 'alveolar',
                    'septal transect requires nonzero alveolar LineString')
            result = {'transect_length_um': physical.length,
                      'interpretation': 'reviewed 2D transect length; obliquity and inflation remain protocol-dependent; not unbiased 3D septal thickness'}
        else:
            require(False, 'unknown morphology endpoint')
        rows.append({'profile_id': fid, **prop, **result})
    require(file_record(path) == record, 'morphology profiles changed during analysis')
    write_json(output, {'schema_version': 'ifquant.morphology-profile-results/1', 'plan': cfg,
        'input': record, 'source_sha256': canonical_sha256(source), 'profiles': rows, 'scientific_validation': False,
        'interpretation': 'sampling units retained; no universal injury score, stereological estimate or independent biological replication'})
    return {'output': str(output), 'profiles': len(rows), 'scientific_validation': False}
