"""Region semantics and frozen color baselines for H&E candidate measurements.

Inspired by LungDamage's Lab clustering; independently implemented. No automatic
severity ranking, joint target fitting, stain-concentration or lineage claim.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import (
    identifier,
    integer,
    iter_tiles,
    keys,
    number,
    open_source,
    require,
    tile_plan,
    validate_source,
    write_json,
)
from .phase3_validation import _canonical_wkt, _parse_polygon_geometry

ANATOMY = {'alveolar_parenchyma', 'airway', 'vessel', 'pleura', 'unresolved'}
ROLES = {'reference', 'artifact', 'lesion', 'training'}


def default_profile():
    return {'schema_version': 'ifquant.he-profile/1', 'background_rgb': [255, 255, 255],
            'stain_vectors': [[0.65, 0.70, 0.29], [0.07, 0.99, 0.11]],
            'tissue_od_sum_min': 0.15,
            'description': 'Engineering starting profile; review for the intended stain batch'}


def validate_profile(profile):
    import numpy as np

    keys(profile, {'schema_version', 'background_rgb', 'stain_vectors',
                   'tissue_od_sum_min', 'description'}, 'H&E profile')
    require(profile['schema_version'] == 'ifquant.he-profile/1', 'unsupported stain profile')
    require(isinstance(profile['background_rgb'], list) and len(profile['background_rgb']) == 3,
            'three background values required')
    for value in profile['background_rgb']:
        require(0 < number(value, 'background') <= 255, 'background outside 8-bit range')
    vectors = profile['stain_vectors']
    require(isinstance(vectors, list) and len(vectors) == 2 and
            all(isinstance(v, list) and len(v) == 3 for v in vectors), 'two RGB stain vectors required')
    for vector in vectors:
        for value in vector:
            number(value, 'stain coefficient', positive=False)
    require(np.linalg.matrix_rank(np.asarray(vectors, dtype=float)) == 2,
            'stain vectors must be independent')
    number(profile['tissue_od_sum_min'], 'tissue threshold')
    identifier(profile['description'], 'profile description')
    return profile


def features(rgb, profile):
    """sRGB/D65 Lab and clipped linear-projection H/E features.

    H/E values are appearance features only. No absolute stain quantification.
    Pixel-local processing has no tile-boundary dependence.
    """
    import numpy as np

    require(rgb.dtype == np.uint8 and rgb.ndim == 3 and rgb.shape[2] == 3,
            'H&E requires native uint8 RGB pixels')
    values = rgb.astype(np.float64)
    srgb = values / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[0.4124564, 0.3575761, 0.1804375],
                             [0.2126729, 0.7151522, 0.0721750],
                             [0.0193339, 0.1191920, 0.9503041]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4 / 29)
    lab = np.stack((116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                    200 * (f[..., 1] - f[..., 2])), axis=-1)
    od = np.maximum(0, -np.log((values + 1) / (np.asarray(profile['background_rgb']) + 1)))
    stains = np.asarray(profile['stain_vectors'], dtype=float)
    stains /= np.linalg.norm(stains, axis=1)[:, None]
    he = np.maximum(0, od @ np.linalg.pinv(stains))
    return lab, he, od.sum(axis=-1) >= profile['tissue_od_sum_min']


def _geometry(wkt, source):
    require(isinstance(wkt, str) and len(wkt) < 1_000_000, 'invalid region geometry')
    canonical = _canonical_wkt('POLYGON', wkt, 'region')
    require(canonical == wkt, 'region WKT must be canonical')
    parsed = _parse_polygon_geometry('POLYGON', wkt, 'region')
    require(all(0 <= x <= source['grid']['base_width'] and
                0 <= y <= source['grid']['base_height']
                for poly in parsed.polygons for ring in poly for x, y in ring),
            'region outside base image')
    return parsed.polygons[0]


def validate_regions(doc, source, *, _ancestors=()):
    keys(doc, {'schema_version', 'source_sha256', 'coordinate_frame', 'regions', 'parent'}, 'regions')
    require(doc['schema_version'] == 'ifquant.regions/1' and
            doc['source_sha256'] == canonical_sha256(source) and
            doc['coordinate_frame'] == 'base_image_pixels', 'region source/frame mismatch')
    identity = canonical_sha256(doc)
    require(identity not in _ancestors and len(_ancestors) < 128, 'cyclic/excessive region ancestry')
    require(isinstance(doc['regions'], list) and bool(doc['regions']), 'regions cannot be empty')
    ids = set()
    for region in doc['regions']:
        keys(region, {'region_id', 'role', 'anatomy', 'label', 'wkt', 'review'}, 'region')
        identifier(region['region_id'], 'region id')
        require(region['region_id'] not in ids, 'duplicate region id')
        ids.add(region['region_id'])
        require(region['role'] in ROLES and region['anatomy'] in ANATOMY, 'unknown role/anatomy')
        identifier(region['label'], 'region label')
        _geometry(region['wkt'], source)
        review = region['review']
        keys(review, {'status', 'reviewer', 'at', 'reason'}, 'review')
        require(review['status'] in ('pending', 'accepted', 'rejected', 'uncertain'), 'invalid review')
        if review['status'] == 'pending':
            require(review['reviewer'] is review['at'] is None, 'pending review has no reviewer/time')
        else:
            identifier(review['reviewer'], 'reviewer')
            identifier(review['reason'], 'review reason')
            require(isinstance(review['at'], str) and review['at'].endswith('Z'), 'UTC review time required')
            try:
                datetime.fromisoformat(review['at'])
            except ValueError as exc:
                from .canonical import ContractError
                raise ContractError('invalid review timestamp') from exc
        require(isinstance(review['reason'], str), 'review reason must be text')
    require(any(r['role'] == 'reference' and r['review']['status'] != 'rejected'
                for r in doc['regions']), 'at least one reference region required')
    parent = doc['parent']
    if parent is not None:
        keys(parent, {'path', 'sha256'}, 'region parent')
        require(Path(parent['path']).is_absolute(), 'parent must have an absolute path')
        ancestor = load_strict_json(parent['path'])
        require(canonical_sha256(ancestor) == parent['sha256'], 'parent region content changed')
        require(ancestor['source_sha256'] == doc['source_sha256'], 'correction changed source')
        validate_regions(ancestor, source, _ancestors=(*_ancestors, identity))
    return doc


def region_mask(region, source, core):
    """Pixel-center even/odd rasterization, with native-to-selected-level mapping."""
    import numpy as np

    x, y, w, h = core
    xx = (np.arange(x, x + w)[None, :] + 0.5) * source['grid']['scale_x']
    yy = (np.arange(y, y + h)[:, None] + 0.5) * source['grid']['scale_y']
    mask = np.zeros((h, w), dtype=bool)
    # Polygon holes toggle parity. Half-open edge rule gives stable shared boundaries.
    for ring in _parse_polygon_geometry('POLYGON', region['wkt'], 'region').polygons[0]:
        ring = [(float(a), float(b)) for a, b in ring]
        from itertools import pairwise
        for (ax, ay), (bx, by) in pairwise(ring):
            if ay != by:
                mask ^= ((ay > yy) != (by > yy)) & (xx < (bx - ax) * (yy - ay) / (by - ay) + ax)
    return mask


def import_geojson(source_path, geojson_path, output, *, reviewer=None, reason='', parent=None):
    source = validate_source(load_strict_json(source_path))
    data = load_strict_json(geojson_path)
    require(data.get('type') == 'FeatureCollection', 'GeoJSON FeatureCollection required')
    regions = []
    for index, feature in enumerate(data.get('features', [])):
        geometry = feature['geometry']
        require(geometry['type'] == 'Polygon', 'only Polygon regions are supported')
        rings = []
        for ring in geometry['coordinates']:
            require(len(ring) >= 4 and ring[0] == ring[-1], 'polygon rings must be closed')
            pairs = []
            for point in ring:
                require(len(point) == 2, '2D coordinates required')
                for v in point:
                    number(v, 'coordinate', positive=False)
                pairs.append(f'{point[0]:.6f} {point[1]:.6f}')
            rings.append('(' + ', '.join(pairs) + ')')
        props = feature.get('properties', {})
        name = props.get('classification', {}).get('name', 'unresolved')
        role = props.get('role', 'reference')
        anatomy = props.get('anatomy', name)
        require(anatomy in ANATOMY and role in ROLES, 'set explicit supported anatomy/role properties')
        regions.append({'region_id': str(feature.get('id', f'region_{index:04d}')),
                        'role': role, 'anatomy': anatomy,
                        'label': props.get('label', name),
                        'wkt': _canonical_wkt('POLYGON', 'POLYGON (' + ', '.join(rings) + ')', 'import'),
                        'review': {'status': 'accepted' if reviewer else 'pending',
                                   'reviewer': reviewer,
                                   'at': datetime.now(UTC).isoformat().replace('+00:00', 'Z')
                                   if reviewer else None, 'reason': reason}})
    doc = {'schema_version': 'ifquant.regions/1', 'source_sha256': canonical_sha256(source),
           'coordinate_frame': 'base_image_pixels', 'regions': regions,
           'parent': {'path': str(Path(parent).resolve()),
                      'sha256': canonical_sha256(load_strict_json(parent))} if parent else None}
    validate_regions(doc, source)
    write_json(output, doc)
    return {'output': str(output), 'region_count': len(regions), 'sha256': canonical_sha256(doc)}


def export_geojson(source, regions):
    validate_regions(regions, source)
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': r['region_id'],
         'geometry': {'type': 'Polygon', 'coordinates': [
             [[float(x), float(y)] for x, y in ring] for ring in _geometry(r['wkt'], source)]},
         'properties': {'objectType': 'annotation', 'classification': {'name': r['anatomy']},
                        'role': r['role'], 'anatomy': r['anatomy'], 'label': r['label']}}
        for r in regions['regions']]}


def assign(features_ab, centers):
    import numpy as np

    return np.argmin(((features_ab[..., None, :] - np.asarray(centers))**2).sum(axis=-1), axis=-1)


def validate_model(doc):
    import numpy as np

    keys(doc, {'schema_version', 'algorithm', 'profile', 'centers', 'class_names',
               'training', 'seed', 'feature_space', 'scientific_validation'}, 'model')
    require(doc['schema_version'] == 'ifquant.he-color-model/1', 'unsupported model')
    require(doc['algorithm'] in ('lab_kmeans', 'lab_nearest_centroid'), 'unsupported algorithm')
    require(doc['feature_space'] == 'srgb_d65_lab_ab' and doc['scientific_validation'] is False,
            'invalid model claims/features')
    validate_profile(doc['profile'])
    centers = np.asarray(doc['centers'], dtype=float)
    require(centers.ndim == 2 and centers.shape[1] == 2 and 2 <= len(centers) <= 16 and
            np.isfinite(centers).all(), 'invalid cluster centers')
    require(len(doc['class_names']) == len(centers) and
            len(set(doc['class_names'])) == len(centers), 'class names must match centers')
    for name in doc['class_names']:
        identifier(name, 'class name')
    integer(doc['seed'], 'seed', minimum=0)
    require(isinstance(doc['training'], list) and len(doc['training']) > 0, 'training ledger missing')
    for item in doc['training']:
        keys(item, {'source_sha256', 'regions_sha256', 'sample_count'}, 'training input')
        for name in ('source_sha256', 'regions_sha256'):
            value = item[name]
            require(name == 'regions_sha256' and value is None or isinstance(value, str) and
                    len(value) == 64 and all(c in '0123456789abcdef' for c in value),
                    'valid training identity hash required')
        integer(item['sample_count'], 'training samples')
    return doc


def fit_model(source_path, output, *, profile_path=None, regions_path=None,
              clusters=4, seed=0, max_samples=30000, supervised=False):
    import numpy as np

    integer(clusters, 'clusters')
    integer(max_samples, 'max_samples')
    integer(seed, 'seed', minimum=0)
    require(2 <= clusters <= 16 and max_samples <= 100000, 'training allocation limit')
    source = validate_source(load_strict_json(source_path))
    require(source['modality'] == 'he', 'H&E source required')
    profile = validate_profile(load_strict_json(profile_path) if profile_path else default_profile())
    regions = validate_regions(load_strict_json(regions_path), source) if regions_path else None
    require(not supervised or regions is not None, 'supervised model requires training regions')
    stride = max(1, math.ceil(math.sqrt(source['grid']['width'] * source['grid']['height'] / max_samples)))
    positions, samples, labels = [], [], []
    with open_source(source) as image:
        for tile in iter_tiles(tile_plan(source, tile_size=256)):
            x, y, w, h = tile['core']
            lab, _, tissue = features(image.read(x, y, w, h), profile)
            yy, xx = np.indices((h, w))
            select = tissue & ((xx + x) % stride == 0) & ((yy + y) % stride == 0)
            label_image = np.full((h, w), '', dtype=object)
            if regions:
                reference = np.zeros((h, w), dtype=bool)
                for r in regions['regions']:
                    if r['role'] == 'reference' and r['review']['status'] != 'rejected':
                        reference |= region_mask(r, source, tile['core'])
                select &= reference
                for r in regions['regions']:
                    if r['role'] == 'artifact' and r['review']['status'] != 'rejected':
                        select &= ~region_mask(r, source, tile['core'])
                if supervised:
                    for r in regions['regions']:
                        if r['role'] == 'training' and r['review']['status'] == 'accepted':
                            mask = region_mask(r, source, tile['core'])
                            require(not np.any(mask & (label_image != '')), 'overlapping training labels')
                            label_image[mask] = r['label']
                    select &= label_image != ''
            samples.extend(lab[..., 1:3][select].tolist())
            positions.extend(((yy[select] + y) * image.width + xx[select] + x).tolist())
            labels.extend(label_image[select].tolist())
    require(len(samples) >= clusters, 'insufficient eligible training pixels')
    order = np.argsort(positions)[:max_samples]
    data = np.asarray(samples)[order]
    if supervised:
        labels = np.asarray(labels)[order]
        names = sorted(set(labels))
        require(2 <= len(names) <= 16, 'supervised training needs 2-16 accepted classes')
        centers = np.asarray([data[labels == name].mean(axis=0) for name in names])
    else:
        rng = np.random.default_rng(seed)
        centers = [data[int(rng.integers(len(data)))]]
        for _ in range(1, clusters):
            distance = np.min(((data[:, None, :] - np.asarray(centers))**2).sum(axis=-1), axis=1)
            require(distance.max() > 0, 'training colors cannot support requested clusters')
            centers.append(data[int(np.argmax(distance))])
        centers = np.asarray(centers)
        for _ in range(100):
            assignments = assign(data, centers)
            updated = np.asarray([data[assignments == i].mean(axis=0)
                                  if np.any(assignments == i) else centers[i]
                                  for i in range(clusters)])
            if np.max(np.abs(updated - centers)) < 1e-8:
                centers = updated
                break
            centers = updated
        centers = centers[np.lexsort((centers[:, 1], centers[:, 0]))]
        names = [f'cluster_{i}' for i in range(clusters)]
    doc = {'schema_version': 'ifquant.he-color-model/1',
           'algorithm': 'lab_nearest_centroid' if supervised else 'lab_kmeans',
           'profile': profile, 'centers': centers.tolist(), 'class_names': names,
           'training': [{'source_sha256': canonical_sha256(source),
                         'regions_sha256': canonical_sha256(regions) if regions else None,
                         'sample_count': len(data)}],
           'seed': seed, 'feature_space': 'srgb_d65_lab_ab', 'scientific_validation': False}
    validate_model(doc)
    validate_source(source)
    write_json(output, doc)
    return {'model_sha256': canonical_sha256(doc), 'output': str(output), 'samples': len(data)}
