"""Resumable tiled nuclei inference with conservative overlap identity reconciliation.

Every output pixel belongs to exactly one half-open core. Overlap predictions
establish object identity only; ambiguous split/merge matches are not forced.
Image arrays remain bounded by a tile; object tables have an explicit capacity.
"""
import csv
import importlib.metadata
import os
import time
from pathlib import Path

from .canonical import canonical_sha256, file_sha256, load_strict_json
from .imaging import (
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
from .instance_segmentation import MODEL_SHA256, cpu_predictor, validate_labels


def overlap_pairs(a, b, box_a, box_b, threshold, minimum):
    """Mutual-best overlap IoU, evaluated only on the shared image rectangle."""
    import numpy as np
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b
    x, y, endx, endy = max(ax, bx), max(ay, by), min(ax+aw, bx+bw), min(ay+ah, by+bh)
    if x >= endx or y >= endy:
        return []
    av = a[y-ay:endy-ay, x-ax:endx-ax].ravel()
    bv = b[y-by:endy-by, x-bx:endx-bx].ravel()
    ca, cb = np.bincount(av), np.bincount(bv)
    both = (av != 0) & (bv != 0)
    pairs, counts = np.unique(np.stack([av[both], bv[both]], axis=1), axis=0, return_counts=True)
    candidates = []
    for (ia, ib), count in zip(pairs, counts):
        iou = count/(ca[ia]+cb[ib]-count)
        if count >= minimum and iou >= threshold:
            candidates.append((int(ia), int(ib), float(iou), int(count)))
    # Lexicographic tie breaking is stable; require each side to choose the other.
    ordered = sorted(candidates, key=lambda p: (-p[2], -p[3], p[0], p[1]))
    best_a, best_b = {}, {}
    for pair in ordered:
        best_a.setdefault(pair[0], pair)
        best_b.setdefault(pair[1], pair)
    return [p for p in ordered if best_a[p[0]] == p == best_b[p[1]]]


class IdentityUnion:
    """Reject any union that would equate two distinct labels from one tile."""
    def __init__(self, offsets):
        import numpy as np
        self.offsets = np.asarray(offsets)
        self.parent = np.arange(offsets[-1]+1, dtype=np.uint32)
        self.tiles = {}

    def find(self, value):
        root = value
        while self.parent[root] != root:
            root = int(self.parent[root])
        while self.parent[value] != value:
            previous = value
            value = int(self.parent[value])
            self.parent[previous] = root
        return root

    def join(self, a, b):
        import numpy as np
        a, b = self.find(a), self.find(b)
        if a == b:
            return 'already_linked'
        ta = self.tiles.get(a, {int(np.searchsorted(self.offsets, a, side='left')-1)})
        tb = self.tiles.get(b, {int(np.searchsorted(self.offsets, b, side='left')-1)})
        if ta & tb:
            return 'rejected_same_tile_collision'
        low, high = sorted((a, b))
        self.parent[high] = low
        self.tiles.pop(high, None)
        self.tiles[low] = ta | tb
        return 'joined'


def _binding(cfg, source):
    return {'config': canonical_sha256(cfg), 'source': canonical_sha256(source), 'weights': MODEL_SHA256,
            'code': {name: file_sha256(Path(__file__).with_name(name)) for name in
                     ('whole_slide_instances.py', 'instance_segmentation.py', 'imaging.py')},
            'environment': {name: importlib.metadata.version(name) for name in
                            ('numpy', 'tifffile', 'torch', 'instanseg-torch')}}


def _tile_paths(root, tile):
    return root/'tiles'/(tile['tile_id']+'.npy'), root/'tiles'/(tile['tile_id']+'.json')


def _acquire_lock(path):
    """OS-owned lock releases on process exit, including a hard interruption."""
    stream = path.open('a+b')
    try:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except BaseException:
        stream.close()
        raise


def _read_tile(root, tile):
    import numpy as np
    pixels, meta = _tile_paths(root, tile)
    record = load_strict_json(meta)
    require(record['tile'] == tile and record['sha256'] == file_sha256(pixels), 'tile identity or bytes changed')
    labels = np.load(pixels, allow_pickle=False)
    require(labels.dtype == np.uint32 and labels.shape == tuple(tile['read'][3:1:-1]), 'tile label grid differs')
    require(int(labels.max()) == record['objects'] and
            np.array_equal(np.unique(labels[labels > 0]), np.arange(1, record['objects']+1)), 'tile labels must be consecutive')
    return labels, record


def _validate_plan(cfg, base):
    keys(cfg, {'schema_version', 'source', 'weights', 'tile_size', 'halo', 'threads',
               'overlap_iou', 'minimum_overlap_pixels', 'maximum_objects'}, 'whole-slide nuclei plan')
    require(cfg['schema_version'] == 'ifquant.instanseg-slide/1', 'unsupported whole-slide plan')
    for name in ('tile_size', 'halo', 'threads', 'minimum_overlap_pixels', 'maximum_objects'):
        integer(cfg[name], name)
    require(cfg['tile_size'] % 16 == 0 and 64 <= cfg['tile_size'] <= 512 and
            16 <= cfg['halo'] <= cfg['tile_size']//2 and cfg['threads'] <= 16 and
            cfg['maximum_objects'] <= 2_000_000, 'whole-slide capacity exceeded')
    number(cfg['overlap_iou'], 'overlap IoU')
    require(cfg['overlap_iou'] <= 1, 'overlap IoU exceeds one')
    source = validate_source(load_strict_json(base/cfg['source']))
    g = source['grid']
    require(source['modality'] == 'he' and g['channels'] == 3 and g['dtype'] == 'uint8', 'uint8 RGB H&E source required')
    sx, sy = g['pixel_size_x_um'], g['pixel_size_y_um']
    require(abs(sx-sy) <= 1e-6*max(sx, sy), 'isotropic selected pixels required')
    require((cfg['tile_size']+2*cfg['halo'])**2*(sx/.5)**2 <= 4_000_000,
            'model-scale tile capacity exceeded')
    require(g['width']*g['height'] <= 10_000_000_000 and max(g['width'], g['height']) <= 1_000_000,
            'whole-slide raster capacity exceeded')
    require(file_sha256(base/cfg['weights']) == MODEL_SHA256, 'pinned weights required')
    plan = tile_plan(source, tile_size=cfg['tile_size'], halo=cfg['halo'])
    # Enforce capacity before materializing the tile inventory.
    size = cfg['tile_size']
    require(((g['width']+size-1)//size)*((g['height']+size-1)//size) <= 100_000,
            'tile count capacity exceeded')
    tiles = list(iter_tiles(plan))
    return source, tiles


def _neighbors(tiles, step):
    """All prior touching grid neighbors, including the two diagonal directions."""
    positions = {tuple(t['core'][:2]): i for i, t in enumerate(tiles)}
    for i, tile in enumerate(tiles):
        x, y = tile['core'][:2]
        for xy in ((x-step, y), (x-step, y-step), (x, y-step), (x+step, y-step)):
            if xy in positions and positions[xy] < i:
                yield i, positions[xy]


def stitch(root, cfg, source, tiles, destination):
    """Deterministic reconstruction from committed tile predictions; no model use."""
    import numpy as np
    import tifffile
    destination.mkdir(parents=True, exist_ok=False)
    offsets = [0]
    for tile in tiles:
        _, record = _read_tile(root, tile)
        offsets.append(offsets[-1]+record['objects'])
        require(offsets[-1] <= cfg['maximum_objects'], 'object table capacity exceeded')
    union = IdentityUnion(offsets)
    counts = {'joined': 0, 'already_linked': 0, 'rejected_same_tile_collision': 0}
    with (destination/'matches.csv').open('x', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['tile_a', 'label_a', 'tile_b', 'label_b', 'overlap_iou', 'overlap_pixels', 'decision'])
        for i, j in _neighbors(tiles, cfg['tile_size']):
            a, _ = _read_tile(root, tiles[i]); b, _ = _read_tile(root, tiles[j])
            for ia, ib, iou, pixels in overlap_pairs(a, b, tiles[i]['read'], tiles[j]['read'],
                                                   cfg['overlap_iou'], cfg['minimum_overlap_pixels']):
                decision = union.join(offsets[i]+ia, offsets[j]+ib)
                counts[decision] += 1
                writer.writerow([i, ia, j, ib, iou, pixels, decision])
    roots = np.array([union.find(i) for i in range(offsets[-1]+1)], dtype=np.uint32)
    # Bounded by the explicit instance cap, independent of slide pixel count.
    area = np.zeros(len(roots), dtype=np.uint64)
    sums = np.zeros((len(roots), 2), dtype=np.float64)
    borders = np.zeros(len(roots), dtype=bool)
    seams = np.zeros(len(roots), dtype=bool)
    supporting_tiles = np.zeros(len(roots), dtype=np.uint32)
    width, height = source['grid']['width'], source['grid']['height']
    def cores():
        for i, tile in enumerate(tiles):
            labels, _ = _read_tile(root, tile)
            x, y, w, h = tile['core']; rx, ry, _, _ = tile['read']
            local = labels[y-ry:y-ry+h, x-rx:x-rx+w]
            mapped = roots[offsets[i]+local]
            mapped[local == 0] = 0
            yield tile, mapped
    for tile, mapped in cores():
        x, y, w, h = tile['core']
        ids, inverse, sizes = np.unique(mapped, return_inverse=True, return_counts=True)
        yy, xx = np.indices((h, w))
        area[ids] += sizes.astype(np.uint64)
        sums[ids, 0] += np.bincount(inverse.ravel(), weights=(xx+x+.5).ravel())
        sums[ids, 1] += np.bincount(inverse.ravel(), weights=(yy+y+.5).ravel())
        supporting_tiles[ids] += 1
        for edge, outer in ((mapped[0], y == 0), (mapped[-1], y+h == height),
                            (mapped[:, 0], x == 0), (mapped[:, -1], x+w == width)):
            (borders if outer else seams)[np.unique(edge)] = True
    area[0] = 0
    kept = np.flatnonzero(area)
    renumber = np.zeros(len(roots), dtype=np.uint32)
    renumber[kept] = np.arange(1, len(kept)+1, dtype=np.uint32)
    sx, sy = source['grid']['pixel_size_x_um'], source['grid']['pixel_size_y_um']
    with (destination/'objects.csv').open('x', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['object_id', 'area_px', 'area_um2', 'centroid_x_source_px', 'centroid_y_source_px',
                         'touches_image_edge', 'touches_internal_seam', 'core_tiles', 'unresolved_seam'])
        for rid in kept:
            writer.writerow([int(renumber[rid]), int(area[rid]), float(area[rid]*sx*sy),
                float(sums[rid, 0]/area[rid]), float(sums[rid, 1]/area[rid]), int(borders[rid]),
                int(seams[rid]), int(supporting_tiles[rid]), int(seams[rid] and supporting_tiles[rid] < 2)])
    def chunks():
        for tile, mapped in cores():
            _, _, w, h = tile['core']
            chunk = np.zeros((cfg['tile_size'], cfg['tile_size']), dtype=np.uint32)
            chunk[:h, :w] = renumber[mapped]
            yield chunk
    tifffile.imwrite(destination/'instances.tif', data=chunks(), shape=(height, width), dtype='uint32',
        tile=(cfg['tile_size'], cfg['tile_size']), bigtiff=True, photometric='minisblack', compression='deflate',
        metadata={'axes': 'YX', 'pixel_size_um_xy': [sx, sy], 'coordinate_frame': 'source_selected_level_pixels'})
    return {'objects': len(kept), 'foreground_pixels': int(area.sum()), 'overlap_decisions': counts,
        'unresolved_seam_objects': int(np.sum(seams[kept] & (supporting_tiles[kept] < 2))),
        'boundary_objects': int(borders[kept].sum()), 'tiles': len(tiles)}


def run_tiled_instanseg(config_path, output, *, resume=False, max_tiles=None):
    import numpy as np
    cfg = load_strict_json(config_path)
    source, tiles = _validate_plan(cfg, Path(config_path).resolve().parent)
    if max_tiles is not None:
        integer(max_tiles, 'max_tiles')
    root = Path(output).resolve()
    binding = _binding(cfg, source)
    if resume:
        require(not (root/'package.json').exists(), 'completed run cannot resume')
        require(load_strict_json(root/'state.json')['binding'] == binding, 'resume inputs/code/environment differ')
    else:
        root.mkdir(parents=True, exist_ok=False)
        (root/'tiles').mkdir()
        write_json(root/'source.json', source)
        write_json(root/'plan.json', cfg)
    lock = _acquire_lock(root/'run.lock')
    # Check completion again under the lock: a competing finalizer may have won.
    if (root/'package.json').exists():
        lock.close()
        require(False, 'completed run cannot resume')
    start, done, new = time.perf_counter(), 0, 0
    state = {'schema_version': 'ifquant.instanseg-slide-state/1', 'binding': binding,
             'status': 'running', 'completed_tiles': 0, 'error': None}
    write_json(root/'state.json', state, replace=True)
    try:
        with cpu_predictor(Path(config_path).resolve().parent/cfg['weights'], cfg['threads']) as infer, open_source(source) as reader:
            total_objects = 0
            for tile in tiles:
                pixels, meta = _tile_paths(root, tile)
                if meta.exists():
                    _, record = _read_tile(root, tile)
                else:
                    if max_tiles is not None and new >= max_tiles:
                        state.update(status='paused', completed_tiles=done)
                        return state
                    # Retain an interrupted write rather than silently reusing uncommitted bytes.
                    if pixels.exists():
                        pixels.rename(pixels.with_suffix('.orphan-'+str(time.time_ns())))
                    labels = validate_labels(infer(reader.read(*tile['read']), source['grid']['pixel_size_x_um']))
                    require(labels.shape == tuple(tile['read'][3:1:-1]), 'inference tile shape differs')
                    ids = np.unique(labels); ids = ids[ids > 0]
                    dense = np.zeros(labels.shape, dtype=np.uint32)
                    positive = labels > 0
                    dense[positive] = np.searchsorted(ids, labels[positive])+1
                    with pixels.open('xb') as f:
                        np.save(f, dense, allow_pickle=False)
                    record = {'tile': tile, 'objects': len(ids), 'sha256': file_sha256(pixels)}
                    write_json(meta, record)
                    new += 1
                total_objects += record['objects']
                require(total_objects <= cfg['maximum_objects'], 'object table capacity exceeded')
                done += 1
                state['completed_tiles'] = done
                write_json(root/'state.json', state, replace=True)
        validate_source(source)
        # Each finalization attempt has its own directory; crashes leave prior bytes intact.
        product = root/('product-'+str(time.time_ns()))
        summary = stitch(root, cfg, source, tiles, product)
        manifest = {'schema_version': 'ifquant.instanseg-slide-package/1', 'binding': binding,
            'summary': summary, 'product': product.name, 'seconds_this_invocation': time.perf_counter()-start,
            'files': {str(p.relative_to(root)).replace('\\', '/'): file_sha256(p)
                      for p in [root/'source.json', root/'plan.json', *sorted((root/'tiles').glob('*.*')), *sorted(product.iterdir())]
                      if '.orphan-' not in p.name},
            'scientific_validation': False,
            'interpretation': 'core pixel ownership plus conservative overlap identity; seam ambiguities remain candidates for review, not proven biological instances'}
        write_json(root/'package.json', manifest)
        state.update(status='complete', completed_tiles=done)
        return {'output': str(root), **summary, 'scientific_validation': False}
    except BaseException as exc:
        state.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed', error=str(exc))
        raise
    finally:
        write_json(root/'state.json', state, replace=True)
        lock.close()


def validate_tiled_instanseg(output):
    """Verify bytes, coverage and reproducible object reconciliation, without inference."""
    import tempfile
    root = Path(output).resolve()
    package = load_strict_json(root/'package.json')
    require(package['schema_version'] == 'ifquant.instanseg-slide-package/1', 'unsupported slide package')
    for name, digest in package['files'].items():
        path = (root/name).resolve()
        require(path.is_relative_to(root) and file_sha256(path) == digest, 'package file binding differs')
    cfg, source = load_strict_json(root/'plan.json'), validate_source(load_strict_json(root/'source.json'))
    require(package['binding']['config'] == canonical_sha256(cfg) and package['binding']['source'] == canonical_sha256(source),
            'package source/plan binding differs')
    tiles = list(iter_tiles(tile_plan(source, tile_size=cfg['tile_size'], halo=cfg['halo'])))
    require(all(str(p.relative_to(root)).replace('\\', '/') in package['files'] for t in tiles for p in _tile_paths(root, t)),
            'incomplete tile manifest')
    with tempfile.TemporaryDirectory(dir=root, prefix='verify-') as temporary:
        summary = stitch(root, cfg, source, tiles, Path(temporary)/'rebuild')
        require(summary == package['summary'], 'reconstructed summary differs')
        for name in ('matches.csv', 'objects.csv', 'instances.tif'):
            key = package['product']+'/'+name
            require(key in package['files'] and file_sha256(Path(temporary)/'rebuild'/name) == package['files'][key],
                    'reconstructed product differs')
    return {'status': 'valid', **summary, 'scientific_validation': False}
