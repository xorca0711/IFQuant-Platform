"""Explicit upstream image/cell-table bridges; no inferred biological identity."""
from __future__ import annotations

import csv
import math
from pathlib import Path

from .canonical import load_strict_json
from .imaging import integer, keys, register_image, require, write_json
from .spatial import exact_id, file_record
from .spatial_exchange import _tree


def import_ngff_window(config_path, output):
    """Read an explicit calibrated NGFF 0.4/0.5 plane into the image contract.

    This bounded bridge deliberately avoids extending the existing source schema
    with ambiguous Z/T/channel selections or treating a crop as an entire slide.
    """
    import numpy as np
    import tifffile
    import zarr
    cfg = load_strict_json(config_path)
    extended = cfg.get('schema_version') == 'ifquant.ngff-window/2'
    keys(cfg, {'schema_version', 'store', 'multiscale', 'level', 'window_xywh',
               'subject', 'modality', 'channel_semantics'} |
               ({'axis_indices', 'channel_indices'} if extended else set()), 'NGFF window config')
    require(cfg['schema_version'] in ('ifquant.ngff-window/1', 'ifquant.ngff-window/2'), 'unsupported NGFF window config')
    store = Path(config_path).resolve().parent/cfg['store']
    inventory = _tree(store)
    root = zarr.open_group(str(store), mode='r')
    integer(cfg['multiscale'], 'multiscale', minimum=0)
    integer(cfg['level'], 'level', minimum=0)
    metadata = root.attrs.get('ome', dict(root.attrs))
    require(isinstance(metadata, dict), 'invalid OME metadata')
    multiscales = metadata.get('multiscales', [])
    require(cfg['multiscale'] < len(multiscales), 'missing NGFF multiscale')
    meta = multiscales[cfg['multiscale']]
    version = metadata.get('version') if 'ome' in root.attrs else meta.get('version')
    require(version in (('0.4', '0.5') if extended else ('0.4',)), 'unsupported NGFF version')
    require(root.metadata.zarr_format == (3 if version == '0.5' else 2), 'NGFF version/storage mismatch')
    axes = meta['axes']
    names = [a['name'] for a in axes]
    if extended:
        require(names[-2:] == ['y', 'x'] and names == [n for n in ('t', 'c', 'z', 'y', 'x') if n in names],
                'supported axes are ordered TCZYX subsets ending YX')
        keys(cfg['axis_indices'], set(names) & {'t', 'z'}, 'explicit T/Z selection')
        for axis in axes[:-2]:
            require(axis.get('type') == {'t': 'time', 'c': 'channel', 'z': 'space'}[axis['name']], 'axis type mismatch')
    else:
        require(names in (['y', 'x'], ['c', 'y', 'x']), 'only explicit 2D YX/CYX supported; select Z/T upstream')
    for axis in axes[-2:]:
        require(axis.get('type') == 'space' and axis.get('unit') == 'micrometer', 'micrometer spatial axes required')
    datasets = meta['datasets']
    require(cfg['level'] < len(datasets), 'NGFF level missing')
    dataset = datasets[cfg['level']]
    path = dataset['path']
    require(isinstance(path, str) and path and not Path(path).is_absolute() and
            '..' not in Path(path).parts and '\\' not in path, 'unsafe NGFF dataset path')
    array = root[path]
    require(array.ndim == len(axes) and array.dtype == np.dtype('uint8'), 'UINT8 2D image profile required')
    if version == '0.5':
        require(array.metadata.zarr_format == 3 and list(array.metadata.dimension_names or []) == names,
                'NGFF 0.5 dimension_names must match axes')
    selected_channels = cfg['channel_indices'] if extended else (list(range(array.shape[0])) if names[0] == 'c' else None)
    if 'c' in names:
        require(isinstance(selected_channels, list) and len(selected_channels) in (1, 3) and
                len(set(selected_channels)) == len(selected_channels), 'select one grayscale or three RGB channels explicitly')
        for channel in selected_channels:
            integer(channel, 'channel index', minimum=0)
            require(channel < array.shape[names.index('c')], 'channel out of bounds')
    else:
        require(selected_channels is None, 'channel selection without channel axis')
    channels = len(selected_channels) if selected_channels else 1
    require(channels in (1, 3), 'only grayscale or explicit RGB order supported')
    require(cfg['channel_semantics'] == ('rgb' if channels == 3 else 'grayscale'), 'declare grayscale or RGB channel semantics explicitly')
    require(math.prod(array.chunks)*array.dtype.itemsize <= 128*1024**2, 'NGFF decoded chunk exceeds capacity')
    scale, offset = np.ones(len(axes)), np.zeros(len(axes))
    for transforms in (dataset.get('coordinateTransformations'), meta.get('coordinateTransformations', [])):
        require(isinstance(transforms, list), 'NGFF coordinate transforms required')
        if transforms:
            require([t.get('type') for t in transforms] in (['scale'], ['scale', 'translation']), 'unsupported NGFF transform sequence')
        for transform in transforms:
            kind = transform['type']
            keys(transform, {'type', kind}, 'NGFF transform')
            values = np.asarray(transform[kind], dtype=float)
            require(values.shape == scale.shape and np.isfinite(values).all(), 'invalid NGFF transform values')
            if kind == 'scale':
                require(np.all(values > 0), 'positive NGFF scales required')
                scale *= values
                offset *= values
            else:
                offset += values
    require(bool(dataset.get('coordinateTransformations')), 'level calibration is required')
    window = cfg['window_xywh']
    require(isinstance(window, list) and len(window) == 4, 'window must be x,y,width,height')
    x, y, width, height = window
    for value in (x, y):
        integer(value, 'window origin', minimum=0)
    for value in (width, height):
        integer(value, 'window extent')
    require(x+width <= array.shape[-1] and y+height <= array.shape[-2] and
            width*height <= 16_000_000, 'NGFF window bounds/capacity exceeded')
    selectors = []
    selected_coordinates = {}
    for i, axis in enumerate(axes[:-2]):
        name = axis['name']
        if name == 'c':
            selectors.append(selected_channels)
        else:
            index = cfg['axis_indices'][name]
            integer(index, f'{name} index', minimum=0)
            require(index < array.shape[i], f'{name} selection out of bounds')
            selectors.append(index)
            selected_coordinates[name] = {'index': index, 'coordinate': float(offset[i]+index*scale[i]), 'unit': axis.get('unit')}
    selectors.extend([slice(y, y+height), slice(x, x+width)])
    pixels = np.asarray(array.oindex[tuple(selectors)])
    if 'c' in names:
        pixels = np.moveaxis(pixels, 0, -1) if channels == 3 else pixels[0]
    require(_tree(store) == inventory, 'NGFF store changed during read')
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    image = destination/'window.tif'
    tifffile.imwrite(image, pixels, tile=(256, 256), photometric='rgb' if channels == 3 else 'minisblack')
    origin = [float(offset[-1]+x*scale[-1]), float(offset[-2]+y*scale[-2])]
    write_json(destination/'derivation.json', {'schema_version': 'ifquant.ngff-derivative/1',
        'plan': cfg, 'ngff_version': version, 'selected_axis_coordinates': selected_coordinates,
        'store_inventory': inventory, 'window_origin_um_xy': origin,
        'window_pixel_size_um_xy': [float(scale[-1]), float(scale[-2])],
        'scope': 'bounded 2D derivative; RGB channel meaning must be declared by the producer', 'scientific_validation': False})
    register_image(image, destination/'source.json', **cfg['subject'], modality=cfg['modality'],
                   pixel_size_x=float(scale[-1]), pixel_size_y=float(scale[-2]),
                   members=[destination/'derivation.json'])
    return {'output': str(destination), 'window_origin_um_xy': origin, 'scientific_validation': False}


def import_cell_features(config_path, output):
    """Map MCMICRO-compatible CSV explicitly, without calling intensities RNA counts."""
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'csv', 'subject', 'frame_id', 'unit', 'id_column',
               'x_column', 'y_column', 'feature_columns', 'upstream_method'}, 'cell-feature config')
    require(cfg['schema_version'] == 'ifquant.cell-features-import/1', 'unsupported cell-feature config')
    keys(cfg['subject'], {'subject_id', 'species', 'specimen_id', 'section_id'}, 'cell-feature subject')
    for value in (*cfg['subject'].values(), cfg['frame_id'], cfg['upstream_method']):
        exact_id(value, 'cell-feature identity/provenance')
    require(cfg['unit'] in ('pixel', 'micrometer'), 'explicit coordinate unit required')
    features = cfg['feature_columns']
    require(isinstance(features, list) and 0 < len(features) <= 200 and len(set(features)) == len(features), 'unique feature columns required')
    columns = [cfg['id_column'], cfg['x_column'], cfg['y_column'], *features]
    require(len(set(columns)) == len(columns), 'identity, coordinates and features must be separate columns')
    path = Path(config_path).resolve().parent/cfg['csv']
    record = file_record(path)
    rows, seen = [], set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames) and
                set(columns) <= set(reader.fieldnames), 'missing or duplicate upstream columns')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'malformed upstream row')
            oid = exact_id(row[cfg['id_column']], 'cell ID')
            require(oid not in seen, 'duplicate cell ID')
            seen.add(oid)
            xy = [float(row[cfg[k]]) for k in ('x_column', 'y_column')]
            require(all(math.isfinite(v) for v in xy), 'invalid cell coordinates')
            values = {f: float(row[f]) if row[f] != '' else None for f in features}
            require(all(v is None or math.isfinite(v) for v in values.values()), 'nonfinite cell feature')
            rows.append({'cell_id': oid, 'x': xy[0], 'y': xy[1], 'features': values})
            require(len(rows)*len(features) <= 2_000_000, 'cell-feature capacity exceeded')
    require(rows and file_record(path) == record, 'empty or changed cell-feature source')
    write_json(output, {'schema_version': 'ifquant.cell-features/1', 'plan': cfg, 'input': record,
        'cells': rows, 'scientific_validation': False,
        'interpretation': 'exact upstream IDs and numeric measurements; no inferred phenotype or RNA counts'})
    return {'output': str(output), 'cells': len(rows), 'features': len(features)}
