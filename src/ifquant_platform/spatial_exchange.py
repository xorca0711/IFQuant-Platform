"""A deliberately explicit SpatialData exchange profile, with portable store hashes.

This is an adapter for IFQuant-profile stores, not arbitrary SpatialData discovery.
Images in this first profile are bounded 2D RGB derivatives; large-image intake
continues through the existing windowed TIFF path.
"""
from __future__ import annotations

import json
from pathlib import Path

from .canonical import canonical_sha256, file_sha256, load_strict_json
from .imaging import keys, require, write_json
from .spatial import finite, inverse_affine, validate_assay
from .spatial_adapters import STATUS, assay_to_anndata, import_native


def _libraries():
    try:
        import numpy as np
        import pandas as pd
        import spatialdata as sd
        from spatialdata.models import Image2DModel, PointsModel, ShapesModel, TableModel
        from spatialdata.transformations import Affine, Identity, get_transformation
    except ImportError as exc:
        from .canonical import ContractError
        raise ContractError('SpatialData exchange requires the optional [spatialdata] extra') from exc
    return np, pd, sd, Image2DModel, PointsModel, ShapesModel, TableModel, Affine, Identity, get_transformation


def _tree(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'store must be a local directory')
    files = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'symlinks are unsupported in portable stores')
        if path.is_file():
            files.append({'path': path.relative_to(root).as_posix(), 'sha256': file_sha256(path),
                          'size_bytes': path.stat().st_size})
    require(bool(files), 'empty SpatialData store')
    return files


def _matrix(value):
    require(isinstance(value, list) and len(value) == 3 and
            all(isinstance(r, list) and len(r) == 3 for r in value), '3 x 3 affine required')
    for row in value:
        for v in row:
            finite(v, 'scene affine')
    require(value[2] == [0, 0, 1], 'perspective scene transforms unsupported')
    inverse_affine(value)
    return value


def export_spatialdata(assay_path, output, *, scene_path=None):
    np, pd, sd, Image, Points, Shapes, Table, Affine, Identity, _ = _libraries()
    assay = validate_assay(load_strict_json(assay_path))
    data = assay_to_anndata(assay_path)
    root = Path(output).resolve()
    manifest_path = root.with_name(root.name+'.ifquant.json')
    require(not root.exists() and not manifest_path.exists(), 'refusing to overwrite spatial exchange')
    frame = assay['coordinate_frame']['frame_id']
    transformations = {frame: Identity()}
    images, shapes, scene = {}, {}, None
    scene_record = None
    if scene_path:
        from PIL import Image as PILImage

        from .spatial import file_record, verify_file
        scene = load_strict_json(scene_path)
        keys(scene, {'frame_id', 'image', 'assay_to_image', 'regions_geojson', 'scale_factors'}, 'spatial scene')
        image_frame = scene['frame_id']
        require(isinstance(image_frame, str) and image_frame and image_frame != frame,
                'image frame must be explicitly named and distinct from assay frame')
        matrix = _matrix(scene['assay_to_image'])
        transformations[image_frame] = Affine(np.array(matrix), input_axes=('x', 'y'), output_axes=('x', 'y'))
        base = Path(scene_path).resolve().parent
        image_path = base/scene['image']
        image_record = file_record(image_path)
        with PILImage.open(image_path) as image:
            require(image.mode == 'RGB' and image.width*image.height <= 16_000_000,
                    'scene image requires RGB and at most 16 million pixels; use TIFF pipeline for larger sources')
            pixels = np.asarray(image).transpose(2, 0, 1)
        factors = scene['scale_factors']
        require(isinstance(factors, list) and len(factors) <= 4 and
                all(type(f) is int and 2 <= f <= 8 for f in factors), 'invalid scene pyramid factors')
        images['image'] = Image.parse(pixels, dims=('c', 'y', 'x'), c_coords=['r', 'g', 'b'],
                                     transformations={image_frame: Identity()},
                                     scale_factors=factors or None, chunks=(3, 256, 256))
        scene_record = {'image': image_record, 'frame_id': image_frame, 'assay_to_image': matrix,
                        'scale_factors': factors, 'regions': None,
                        'interpretation': 'pixel-frame image context; no physical calibration or pathology acceptance'}
        if scene['regions_geojson']:
            import geopandas as gpd
            from shapely.geometry import shape
            region_path = base/scene['regions_geojson']
            regions = load_strict_json(region_path)
            require(regions.get('type') == 'FeatureCollection', 'region FeatureCollection required')
            rows, geometries, ids = [], [], set()
            for i, feature in enumerate(regions['features']):
                rid = feature.get('id')
                require(isinstance(rid, str) and rid and rid not in ids, 'unique region IDs required')
                ids.add(rid)
                geometry = shape(feature['geometry'])
                require(geometry.geom_type in ('Polygon', 'MultiPolygon') and geometry.is_valid and not geometry.is_empty,
                        'invalid scene polygon')
                require(all(math_isfinite(v) for v in geometry.bounds), 'nonfinite scene geometry')
                rows.append({'region_id': rid, 'properties_json': json.dumps(feature.get('properties', {})), 'instance_id': i})
                geometries.append(geometry)
            require(bool(rows), 'scene regions cannot be empty')
            frame_data = gpd.GeoDataFrame(rows, geometry=geometries).set_index('instance_id')
            shapes['regions'] = Shapes.parse(frame_data, transformations={image_frame: Identity()})
            scene_record['regions'] = file_record(region_path)
            scene_record['geojson'] = regions
        verify_file(image_record)
    points = pd.DataFrame({'x': data.obsm['spatial'][:, 0], 'y': data.obsm['spatial'][:, 1],
                           'observation_id': list(data.obs_names)})
    point_element = Points.parse(points, coordinates={'x': 'x', 'y': 'y'}, transformations=transformations)
    require('ifquant_point_index' not in data.obs and 'ifquant_region' not in data.obs,
            'reserved SpatialData metadata columns already present')
    data.obs['ifquant_point_index'] = np.arange(data.n_obs)
    data.obs['ifquant_region'] = pd.Categorical(['observations']*data.n_obs)
    table = Table.parse(data, region='observations', region_key='ifquant_region', instance_key='ifquant_point_index')
    store = sd.SpatialData(images=images, shapes=shapes, points={'observations': point_element}, tables={'rna': table})
    store.write(root)
    manifest = {'schema_version': 'ifquant.spatialdata-exchange/1', 'assay_sha256': canonical_sha256(assay),
                'metadata': json.loads(data.uns['ifquant_metadata_json']), 'scene': scene_record,
                'files': _tree(root), 'scientific_validation': False}
    write_json(manifest_path, manifest)
    return {'output': str(root), 'manifest': str(manifest_path), 'observations': data.n_obs,
            'features': data.n_vars, 'coordinate_systems': sorted(transformations)}


def math_isfinite(value):
    import math
    return math.isfinite(value)


def import_spatialdata(store_path, output):
    np, _, sd, _, _, _, _, _, _, get_transform = _libraries()
    root = Path(store_path).resolve()
    manifest_path = root.with_name(root.name+'.ifquant.json')
    manifest = load_strict_json(manifest_path)
    keys(manifest, {'schema_version', 'assay_sha256', 'metadata', 'scene', 'files', 'scientific_validation'},
         'SpatialData exchange manifest')
    require(manifest['schema_version'] == 'ifquant.spatialdata-exchange/1' and
            manifest['scientific_validation'] is False, 'unsupported SpatialData profile')
    require(_tree(root) == manifest['files'], 'SpatialData store bytes changed or incomplete')
    store = sd.read_zarr(root)
    require(set(store.tables) == {'rna'} and set(store.points) == {'observations'}, 'unexpected exchange elements')
    data = store.tables['rna'].copy()
    require(json.loads(data.uns['ifquant_metadata_json']) == manifest['metadata'], 'exchange metadata differs')
    points = store.points['observations'].compute().sort_index()
    require(list(points.index) == list(range(data.n_obs)) and
            list(points['observation_id']) == list(data.obs_names), 'point/table identity or order mismatch')
    require(np.array_equal(points[['x', 'y']].to_numpy(), data.obsm['spatial']), 'point/table coordinates differ')
    require(list(data.obs['ifquant_point_index']) == list(range(data.n_obs)) and
            set(data.obs['ifquant_region']) == {'observations'}, 'invalid table annotation mapping')
    frame = manifest['metadata']['coordinate_frame']['frame_id']
    transforms = get_transform(store.points['observations'], get_all=True)
    expected_frames = {frame} | ({manifest['scene']['frame_id']} if manifest['scene'] else set())
    require(set(transforms) == expected_frames, 'coordinate systems differ')
    require(np.allclose(transforms[frame].to_affine_matrix(('x', 'y'), ('x', 'y')), np.eye(3)), 'assay frame moved')
    if manifest['scene']:
        scene = manifest['scene']
        image_frame = scene['frame_id']
        require(np.allclose(transforms[image_frame].to_affine_matrix(('x', 'y'), ('x', 'y')),
                            scene['assay_to_image']), 'image transformation differs')
        require(set(store.images) == {'image'} and set(store.shapes) == ({'regions'} if scene['regions'] else set()),
                'missing or extra scene elements')
    else:
        require(not store.images and not store.shapes, 'unexpected scene elements')
    del data.obs['ifquant_point_index'], data.obs['ifquant_region']
    data.uns.pop('spatialdata_attrs', None)
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    data.write_h5ad(out/'exchange.h5ad')
    metadata = manifest['metadata']
    config = {k: metadata[k] for k in ('assay_id', 'subject', 'entity_type', 'coordinate_frame')}
    config.update(schema_version='ifquant.native-spatial-import/1', format='anndata',
                  inputs={'h5ad': 'exchange.h5ad'}, options={'counts_layer': 'X', 'coordinates_key': 'spatial',
                  'feature_name_column': 'feature_name', 'status_column': STATUS, 'default_status': 'measured', 'feature_ids': None})
    write_json(out/'import-native.json', config)
    result = import_native(out/'import-native.json', out/'assay')
    # Keep the portable scene and named transformations, even though the assay uses its native frame.
    write_json(out/'scene-provenance.json', {'metadata': metadata, 'scene': manifest['scene'],
                                           'exchange_manifest_sha256': canonical_sha256(manifest)})
    return result
