"""Calibrated, content-bound 2D image intake and bounded region reads.

The v1 fluorescence packages are unchanged. This separate source contract admits
species/subject identity, multi-file sources and selected TIFF pyramid levels.
"""
from __future__ import annotations

import math
import os
import uuid
from pathlib import Path
from typing import Any

from .canonical import (
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    load_strict_json,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def keys(value: Any, expected: set[str], label: str) -> None:
    require(isinstance(value, dict) and set(value) == expected, f'{label}: invalid fields')


def number(value: Any, label: str, *, positive: bool = True) -> float:
    require(type(value) in (float, int) and math.isfinite(value), f'{label}: finite number required')
    require(value > 0 if positive else value >= 0, f'{label}: invalid range')
    return float(value)


def integer(value: Any, label: str, *, minimum: int = 1) -> int:
    require(type(value) is int and value >= minimum, f'{label}: integer >= {minimum} required')
    return value


def identifier(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f'{label}: nonempty text required')
    return value


def write_json(path: str | Path, value: Any, *, replace: bool = False) -> None:
    """Atomic JSON publication; replacement is reserved for explicit mutable ledgers."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    require(replace or not path.exists(), f'refusing to overwrite {path}')
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with temporary.open('xb') as stream:
        stream.write(canonical_json_bytes(value) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(temporary, path)
    else:
        # Both paths publish atomically without replacing an existing destination.
        # Windows rename is exclusive; POSIX rename would overwrite, so use a link there.
        try:
            if os.name == 'nt':
                os.rename(temporary, path)
            else:
                os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


class ImageReader:
    """Windowed TIFF/Zarr reads; Pillow is restricted to explicitly small images."""

    def __init__(self, path: str | Path, *, reader: str, series: int = 0, level: int = 0):
        import numpy as np

        self.path = Path(path)
        self.resource = self.store = None
        require(reader in ('tiff', 'pillow'), 'reader must be tiff or pillow')
        integer(series, 'series', minimum=0)
        integer(level, 'level', minimum=0)
        try:
            if reader == 'tiff':
                import tifffile
                import zarr

                self.resource = tifffile.TiffFile(self.path)
                require(series < len(self.resource.series), 'TIFF series does not exist')
                selected = self.resource.series[series]
                require(level < len(selected.levels), 'TIFF level does not exist')
                base, selected = selected.levels[0], selected.levels[level]
                require(selected.axes in ('YX', 'YXS', 'YXC'),
                        'select an explicit 2D YX/YXS/YXC derivative; Z/T/planar channels unsupported')
                self.base_width = base.shape[1]
                self.base_height = base.shape[0]
                # Refuse a gigantic decoded strip: windowing alone cannot bound its codec allocation.
                page = selected.pages[0]
                decoded = page.chunks[0] * page.chunks[1] * page.samplesperpixel * page.dtype.itemsize
                require(decoded <= 128 * 1024**2, 'decoded TIFF chunk exceeds 128 MiB; retile first')
                self.store = selected.aszarr()
                self.array = zarr.open(self.store, mode='r')
            else:
                from PIL import Image

                require(series == level == 0, 'Pillow has no selected series/pyramid level')
                self.resource = Image.open(self.path)
                require(self.resource.width * self.resource.height <= 16_000_000,
                        'large images require the tiled TIFF reader')
                require(self.resource.mode in ('RGB', 'L'), 'Pillow source must be RGB or L')
                self.array = np.asarray(self.resource)
                self.base_height, self.base_width = self.array.shape[:2]
            self.height, self.width = self.array.shape[:2]
            self.channels = self.array.shape[2] if self.array.ndim == 3 else 1
            self.dtype = str(self.array.dtype)
            self.scale_x = self.base_width / self.width
            self.scale_y = self.base_height / self.height
        except Exception:
            self.close()
            raise

    def read(self, x: int, y: int, width: int, height: int):
        import numpy as np

        for v in (x, y):
            integer(v, 'read origin', minimum=0)
        for v in (width, height):
            integer(v, 'read extent')
        require(x + width <= self.width and y + height <= self.height, 'read exceeds image bounds')
        require(width * height * self.channels * self.array.dtype.itemsize <= 128 * 1024**2,
                'read exceeds 128 MiB; use smaller tiles')
        return np.asarray(self.array[y:y + height, x:x + width])

    def close(self):
        if self.store is not None:
            self.store.close()
        if self.resource is not None:
            self.resource.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def register_image(path, output, *, subject_id, species, specimen_id, section_id,
                   pixel_size_x, pixel_size_y, modality='he', reader='tiff',
                   series=0, level=0, members=()):
    files = [Path(path).resolve(), *(Path(p).resolve() for p in members)]
    require(len(set(files)) == len(files), 'duplicate source members')
    before = [{'path': str(p), 'sha256': file_sha256(p), 'size_bytes': p.stat().st_size}
              for p in files]
    with ImageReader(files[0], reader=reader, series=series, level=level) as image:
        doc = {
            'schema_version': 'ifquant.image-source/1',
            'subject': {'subject_id': subject_id, 'species': species,
                        'specimen_id': specimen_id, 'section_id': section_id},
            'modality': modality, 'files': before,
            'selection': {'reader': reader, 'series': series, 'level': level},
            'grid': {'width': image.width, 'height': image.height,
                     'base_width': image.base_width, 'base_height': image.base_height,
                     'channels': image.channels, 'dtype': image.dtype,
                     'scale_x': image.scale_x, 'scale_y': image.scale_y,
                     'pixel_size_x_um': number(pixel_size_x, 'pixel_size_x') * image.scale_x,
                     'pixel_size_y_um': number(pixel_size_y, 'pixel_size_y') * image.scale_y},
            'calibration_source': 'user_declared_base_pixel_size',
        }
    validate_source(doc)
    write_json(output, doc)
    return {'source_sha256': canonical_sha256(doc), 'output': str(output)}


def validate_source(doc, *, verify_files=True):
    keys(doc, {'schema_version', 'subject', 'modality', 'files', 'selection', 'grid',
               'calibration_source'}, 'source')
    require(doc['schema_version'] == 'ifquant.image-source/1', 'unsupported image source')
    keys(doc['subject'], {'subject_id', 'species', 'specimen_id', 'section_id'}, 'subject')
    for key, value in doc['subject'].items():
        identifier(value, key)
    require(doc['modality'] in ('he', 'fluorescence'), 'unsupported modality')
    require(doc['calibration_source'] == 'user_declared_base_pixel_size', 'invalid calibration source')
    keys(doc['selection'], {'reader', 'series', 'level'}, 'selection')
    require(doc['selection']['reader'] in ('tiff', 'pillow'), 'invalid reader')
    for name in ('series', 'level'):
        integer(doc['selection'][name], name, minimum=0)
    g = doc['grid']
    keys(g, {'width', 'height', 'base_width', 'base_height', 'channels', 'dtype', 'scale_x',
             'scale_y', 'pixel_size_x_um', 'pixel_size_y_um'}, 'grid')
    for name in ('width', 'height', 'base_width', 'base_height', 'channels'):
        integer(g[name], name)
    identifier(g['dtype'], 'dtype')
    for name in ('scale_x', 'scale_y', 'pixel_size_x_um', 'pixel_size_y_um'):
        number(g[name], name)
    require(g['scale_x'] == g['base_width'] / g['width'] and
            g['scale_y'] == g['base_height'] / g['height'], 'inconsistent grid scale')
    require(isinstance(doc['files'], list) and len(doc['files']) > 0, 'source files required')
    seen = set()
    for f in doc['files']:
        keys(f, {'path', 'sha256', 'size_bytes'}, 'source file')
        path = Path(identifier(f['path'], 'source path'))
        require(path.is_absolute() and str(path.resolve()) not in seen, 'duplicate/relative source')
        seen.add(str(path.resolve()))
        require(isinstance(f['sha256'], str) and len(f['sha256']) == 64 and
                all(c in '0123456789abcdef' for c in f['sha256']), 'invalid source hash')
        integer(f['size_bytes'], 'file size')
        if verify_files:
            require(path.stat().st_size == f['size_bytes'] and file_sha256(path) == f['sha256'],
                    f'source bytes changed: {path}')
    return doc


def open_source(doc):
    image = ImageReader(doc['files'][0]['path'], **doc['selection'])
    g = doc['grid']
    if any(getattr(image, key) != g[key] for key in
           ('width', 'height', 'base_width', 'base_height', 'channels', 'dtype', 'scale_x', 'scale_y')):
        image.close()
        raise ContractError('reader metadata differs from registered grid')
    return image


def tile_plan(source, *, tile_size=512, halo=0):
    validate_source(source, verify_files=False)
    integer(tile_size, 'tile_size')
    integer(halo, 'halo', minimum=0)
    require(tile_size <= 4096 and halo <= 512, 'tile size/halo exceeds supported allocation')
    return {'schema_version': 'ifquant.tile-plan/1', 'source_sha256': canonical_sha256(source),
            'width': source['grid']['width'], 'height': source['grid']['height'],
            'tile_size': tile_size, 'halo': halo,
            'ownership': 'nonoverlapping_half_open_core',
            'coordinate_frame': 'selected_level_pixels'}


def iter_tiles(plan):
    """Lazy row-major cores own every pixel once; halos are read context only."""
    keys(plan, {'schema_version', 'source_sha256', 'width', 'height', 'tile_size', 'halo',
                'ownership', 'coordinate_frame'}, 'tile plan')
    require(plan['schema_version'] == 'ifquant.tile-plan/1' and
            plan['ownership'] == 'nonoverlapping_half_open_core' and
            plan['coordinate_frame'] == 'selected_level_pixels', 'invalid tile plan')
    w, h, size = (integer(plan[k], k) for k in ('width', 'height', 'tile_size'))
    halo = integer(plan['halo'], 'halo', minimum=0)
    require(size <= 4096 and halo <= 512, 'tile size/halo exceeds limit')
    for y in range(0, h, size):
        for x in range(0, w, size):
            cw, ch = min(size, w - x), min(size, h - y)
            rx, ry = max(0, x - halo), max(0, y - halo)
            yield {'tile_id': f'y{y:09d}_x{x:09d}', 'core': [x, y, cw, ch],
                   'read': [rx, ry, min(w, x + cw + halo) - rx,
                            min(h, y + ch + halo) - ry]}


def create_plan(source_path, output, *, tile_size=512, halo=0):
    source = validate_source(load_strict_json(source_path))
    plan = tile_plan(source, tile_size=tile_size, halo=halo)
    write_json(output, plan)
    return {'output': str(output), 'tiles': math.ceil(plan['width'] / tile_size) *
            math.ceil(plan['height'] / tile_size), 'plan_sha256': canonical_sha256(plan)}
