"""Pinned CPU brightfield inference and bounded, label-number invariant matching."""
import time
from contextlib import contextmanager
from pathlib import Path

from .canonical import canonical_sha256, file_sha256, load_strict_json
from .imaging import integer, keys, open_source, require, validate_source, write_json
from .spatial import file_record

MODEL_SHA256 = '0c724da169d507d8dd2e206ad3675a0b1566824eee6e20ad9a0ba916311d9dd0'


@contextmanager
def cpu_predictor(weights, threads):
    """One pinned model per run; restore process thread settings on failure."""
    import importlib.metadata
    require(file_sha256(weights) == MODEL_SHA256, 'only pinned official brightfield_nuclei 0.1.1 weights accepted')
    require(importlib.metadata.version('instanseg-torch') == '0.1.2', 'pinned instanseg-torch 0.1.2 required')
    import torch
    from instanseg import InstanSeg
    require(torch.__version__.split('+')[0] == '2.8.0', 'pinned torch 2.8.0 required')
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(threads)
        model = torch.jit.load(str(weights), map_location='cpu').eval()
        require(file_sha256(weights) == MODEL_SHA256, 'weights changed while loading')
        predictor = InstanSeg(model, device='cpu', image_reader='skimage.io', verbosity=0, channels_last=False)
        def infer(image, pixel_size):
            with torch.inference_mode():
                result = predictor.eval_small_image(image, pixel_size=pixel_size, target='nuclei',
                    normalise=True, return_image_tensor=False, rescale_output=True)
            height, width = image.shape[:2]
            require(tuple(result.shape[-2:]) == (height, width) and result.numel() == height*width,
                    'model output does not preserve the selected image grid')
            return validate_labels(result.detach().cpu().numpy().reshape(height, width))
        yield infer
    finally:
        torch.set_num_threads(previous)


def validate_labels(values):
    import numpy as np
    values = np.asarray(values)
    require(values.ndim == 2 and values.size <= 4_000_000 and
            np.isfinite(values).all() and (values >= 0).all() and
            (values == np.floor(values)).all() and (values <= 2**32-1).all(),
            'bounded nonnegative integer 2D instance labels required')
    return values.astype(np.uint32)


def match_instances(reference, prediction, threshold=0.5):
    """Maximum-cardinality IoU matching; exhaustive common ROI, background is zero."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    reference, prediction = validate_labels(reference), validate_labels(prediction)
    require(reference.shape == prediction.shape, 'instance grids differ')
    require(type(threshold) in (int, float) and 0 < threshold <= 1, 'invalid IoU threshold')
    rids, ri, rc = np.unique(reference, return_inverse=True, return_counts=True)
    pids, pi, pc = np.unique(prediction, return_inverse=True, return_counts=True)
    require(len(rids)*len(pids) <= 4_000_000, 'instance matching capacity exceeded')
    counts = np.bincount(ri.ravel()*len(pids)+pi.ravel(), minlength=len(rids)*len(pids)).reshape(len(rids), len(pids))
    iou = counts/(rc[:, None]+pc[None, :]-counts)
    iou = iou[np.ix_(rids != 0, pids != 0)]
    nr, npred = iou.shape
    valid = iou >= threshold
    # A valid match outweighs the sum of all secondary IoU improvements.
    rows, cols = linear_sum_assignment(-(valid*(min(nr, npred)+1)+iou))
    matched = iou[rows, cols][valid[rows, cols]]
    tp = len(matched)
    return {'reference_instances': nr, 'predicted_instances': npred, 'true_positive': tp,
            'false_positive': npred-tp, 'false_negative': nr-tp, 'iou_threshold': threshold,
            'precision': tp/npred if npred else None, 'recall': tp/nr if nr else None,
            'f1': 2*tp/(nr+npred) if nr+npred else None,
            'mean_matched_iou': float(matched.mean()) if tp else None,
            'reference_kind': 'caller must distinguish model conformance from independent annotation'}


def segment_instanseg(config_path, output):
    import csv
    import importlib.metadata

    import numpy as np
    cfg = load_strict_json(config_path)
    keys(cfg, {'schema_version', 'source', 'weights', 'window_xywh', 'threads'}, 'InstanSeg plan')
    require(cfg['schema_version'] == 'ifquant.instanseg/1', 'unsupported InstanSeg plan')
    integer(cfg['threads'], 'threads')
    require(cfg['threads'] <= 16, 'CPU thread cap is 16')
    base = Path(config_path).resolve().parent
    source = validate_source(load_strict_json(base/cfg['source']))
    require(source['modality'] == 'he', 'brightfield nuclei model requires declared H&E')
    window = cfg['window_xywh']
    require(isinstance(window, list) and len(window) == 4, 'explicit x,y,width,height window required')
    x, y, width, height = window
    for value in (x, y):
        integer(value, 'window origin', minimum=0)
    for value in (width, height):
        integer(value, 'window size')
    sx, sy = (source['grid'][k] for k in ('pixel_size_x_um', 'pixel_size_y_um'))
    require(abs(sx-sy) <= 1e-6*max(sx, sy), 'isotropic input pixels required; resample explicitly upstream')
    require(width*height <= 1_000_000 and width*height*(sx/0.5)**2 <= 4_000_000,
            'bounded inference window or model-scale workspace exceeded')
    weights = base/cfg['weights']
    require(file_sha256(weights) == MODEL_SHA256, 'only pinned official brightfield_nuclei 0.1.1 weights accepted')
    with open_source(source) as reader:
        image = reader.read(x, y, width, height)
    require(image.shape == (height, width, 3) and image.dtype == np.uint8, 'uint8 RGB input required')
    require(not Path(output).exists(), 'refusing existing inference output')
    require(importlib.metadata.version('instanseg-torch') == '0.1.2', 'pinned instanseg-torch 0.1.2 required')
    import torch
    from instanseg import InstanSeg
    require(torch.__version__.split('+')[0] == '2.8.0', 'pinned torch 2.8.0 required')
    start, previous_threads = time.perf_counter(), torch.get_num_threads()
    try:
        torch.set_num_threads(cfg['threads'])
        model = torch.jit.load(str(weights), map_location='cpu').eval()
        require(file_sha256(weights) == MODEL_SHA256, 'weights changed while loading')
        predictor = InstanSeg(model, device='cpu', image_reader='skimage.io', verbosity=0, channels_last=False)
        with torch.inference_mode():
            result = predictor.eval_small_image(image, pixel_size=sx, target='nuclei',
                normalise=True, return_image_tensor=False, rescale_output=True)
        require(tuple(result.shape[-2:]) == (height, width) and result.numel() == height*width,
                'model output does not preserve the selected image grid')
        labels = validate_labels(result.detach().cpu().numpy().reshape(height, width))
    finally:
        torch.set_num_threads(previous_threads)
    validate_source(source)
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    np.save(destination/'nuclei.npy', labels, allow_pickle=False)
    from skimage.measure import regionprops
    with (destination/'nuclei.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['object_id', 'centroid_x_source_px', 'centroid_y_source_px', 'area_um2', 'touches_window_edge'])
        objects = regionprops(labels)
        for obj in objects:
            by, bx, ey, ex = obj.bbox
            writer.writerow([f'nucleus-{obj.label}', obj.centroid[1]+x+0.5, obj.centroid[0]+y+0.5,
                             obj.area*sx*sy, int(bx == 0 or by == 0 or ex == width or ey == height)])
    report = {'schema_version': 'ifquant.instanseg-results/1', 'plan': cfg,
        'source_sha256': canonical_sha256(source), 'weights': file_record(weights),
        'engine': {'instanseg_torch': '0.1.2', 'torch': torch.__version__, 'device': 'cpu'},
        'objects': len(objects), 'seconds': time.perf_counter()-start,
        'coordinate_convention': 'source selected-level pixels; pixel centers at index + 0.5; origin at upper left corner',
        'artifacts': [file_record(destination/n) for n in ('nuclei.npy', 'nuclei.csv')],
        'scientific_validation': False,
        'scope': 'bounded H&E nuclei ROI; border objects flagged; no tile stitching, cell phenotype, or lesion score'}
    write_json(destination/'result.json', report)
    return {'output': str(destination), 'objects': len(objects), 'scientific_validation': False}
