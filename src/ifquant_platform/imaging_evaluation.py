"""Image execution benchmarks, mask comparisons and ordinal reviewer agreement."""
from __future__ import annotations

import csv
import time
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .imaging import integer, keys, open_source, require, validate_source, write_json
from .spatial import file_record


def benchmark_image(source_path, output, *, tile_size=512, tiles=64, seed=0):
    import numpy as np
    import psutil
    source = validate_source(load_strict_json(source_path))
    integer(tile_size, 'benchmark tile size')
    integer(tiles, 'benchmark tiles')
    integer(seed, 'benchmark seed', minimum=0)
    require(tile_size <= 4096 and tiles <= 10000, 'benchmark capacity exceeded')
    rng = np.random.default_rng(seed)
    timings, checksums, rss = [], [], []
    start = time.perf_counter()
    with open_source(source) as image:
        width, height = min(tile_size, image.width), min(tile_size, image.height)
        positions = [(int(rng.integers(image.width-width+1)), int(rng.integers(image.height-height+1))) for _ in range(tiles)]
        for x, y in positions:
            before = time.perf_counter()
            tile = image.read(x, y, width, height)
            timings.append(time.perf_counter()-before)
            checksums.append(int(tile.astype(np.uint64).sum()))
            rss.append(psutil.Process().memory_info().rss)
        # The same window must decode identically when read again.
        require(int(image.read(*positions[0], width, height).astype(np.uint64).sum()) == checksums[0], 'repeat window mismatch')
    validate_source(source)
    doc = {'schema_version': 'ifquant.image-window-benchmark/1', 'source_sha256': canonical_sha256(source),
           'source': source, 'seed': seed, 'tile_size': [width, height], 'tiles': tiles,
           'positions': positions, 'pixel_sums': checksums, 'read_seconds': timings,
           'read_median_seconds': float(np.median(timings)), 'sampled_peak_rss_bytes': max(rss),
           'elapsed_seconds': time.perf_counter()-start, 'scientific_validation': False,
           'scope': 'sampled window reads on one source/codec; no whole-slide analysis throughput or pathology accuracy claim'}
    write_json(output, doc)
    return {'output': str(output), 'tiles': tiles, 'read_median_seconds': doc['read_median_seconds'],
            'sampled_peak_rss_bytes': max(rss)}


def compare_masks(config_path, output):
    import numpy as np
    from PIL import Image
    config = load_strict_json(config_path)
    keys(config, {'schema_version', 'source', 'reference_mask', 'prediction_mask', 'classes',
                  'ignore_value', 'reference_review', 'method_id', 'sampling_protocol'}, 'mask comparison')
    require(config['schema_version'] == 'ifquant.mask-comparison/1', 'unsupported mask comparison')
    base = Path(config_path).resolve().parent
    source = validate_source(load_strict_json(base/config['source']))
    require(source['grid']['width']*source['grid']['height'] <= 16_000_000, 'use explicitly registered smaller mask regions')
    review = config['reference_review']
    keys(review, {'status', 'reviewer', 'at', 'data_kind'}, 'mask reference review')
    require(review['status'] == 'accepted' and review['reviewer'] and review['at'] and
            review['data_kind'] in ('synthetic', 'reviewed_reference'), 'explicit reference review required')
    require(config['method_id'] and config['sampling_protocol'], 'method and sampling protocol required')
    masks, records = [], []
    for key in ('reference_mask', 'prediction_mask'):
        path = base/config[key]
        records.append(file_record(path))
        with Image.open(path) as image:
            require(image.size == (source['grid']['width'], source['grid']['height']) and image.mode in ('L', 'I', 'I;16'),
                    'label masks must match the registered image pixel grid')
            masks.append(np.asarray(image))
    truth, prediction = masks
    classes = config['classes']
    require(isinstance(classes, list) and classes and len(set(classes)) == len(classes) and
            all(type(v) is int and v >= 0 for v in classes) and config['ignore_value'] not in classes, 'invalid class labels')
    valid = truth != config['ignore_value']
    require(np.any(valid) and set(np.unique(truth[valid])) <= set(classes) and
            set(np.unique(prediction[valid])) <= set(classes), 'unknown class or empty reference')
    matrix = [[int(np.sum(valid & (truth == a) & (prediction == b))) for b in classes] for a in classes]
    outcomes = []
    for i, label in enumerate(classes):
        tp = matrix[i][i]; actual = sum(matrix[i]); called = sum(row[i] for row in matrix)
        outcomes.append({'class': label, 'reference_pixels': actual, 'predicted_pixels': called,
                         'iou': tp/(actual+called-tp) if actual+called-tp else None,
                         'dice': 2*tp/(actual+called) if actual+called else None})
    doc = {'schema_version': 'ifquant.mask-comparison-results/1', 'plan': config,
           'source_sha256': canonical_sha256(source), 'inputs': records, 'classes': classes,
           'confusion_matrix': matrix, 'outcomes': outcomes, 'ignored_pixels': int((~valid).sum()),
           'scientific_validation': False, 'interpretation': 'per-image reference comparison; pixels are not biological replicates'}
    write_json(output, doc)
    return {'output': str(output), 'outcomes': outcomes, 'scientific_validation': False}


def reviewer_agreement(config_path, output):
    config = load_strict_json(config_path)
    keys(config, {'schema_version', 'ratings_csv', 'endpoint_id', 'ordered_scores', 'reviewers', 'rubric_reference'}, 'agreement config')
    require(config['schema_version'] == 'ifquant.ordinal-agreement/1', 'unsupported agreement config')
    levels, reviewers = config['ordered_scores'], config['reviewers']
    require(levels == sorted(set(levels)) and len(levels) >= 2 and all(type(v) is int for v in levels), 'ordered integer scores required')
    require(len(reviewers) == 2 and len(set(reviewers)) == 2 and all(reviewers), 'two distinct reviewers required')
    require(config['endpoint_id'] and config['rubric_reference'], 'endpoint and rubric required')
    path = Path(config_path).resolve().parent/config['ratings_csv']
    scores, units = {}, set()
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == ['unit_id', 'reviewer', 'endpoint_id', 'score'], 'invalid rating columns')
        for row in reader:
            require(row['unit_id'] and row['reviewer'] in reviewers and row['endpoint_id'] == config['endpoint_id'], 'invalid rating identity')
            pair = (row['unit_id'], row['reviewer'])
            require(pair not in scores, 'duplicate rating')
            score = int(row['score']) if row['score'] else None
            require(score is None or score in levels, 'rating outside rubric')
            scores[pair] = score
            units.add(row['unit_id'])
    paired = [(scores.get((u, reviewers[0])), scores.get((u, reviewers[1]))) for u in sorted(units)]
    complete = [(a, b) for a, b in paired if a is not None and b is not None]
    require(bool(complete), 'no paired completed ratings')
    matrix = [[sum(a == x and b == y for a, b in complete) for y in levels] for x in levels]
    n = len(complete)
    row_counts = [sum(row) for row in matrix]
    col_counts = [sum(row[j] for row in matrix) for j in range(len(levels))]
    observed, expected = 0., 0.
    for i in range(len(levels)):
        for j in range(len(levels)):
            weight = abs(i-j)/(len(levels)-1)
            observed += weight*matrix[i][j]/n
            expected += weight*row_counts[i]*col_counts[j]/n**2
    kappa = 1-observed/expected if expected else None
    doc = {'schema_version': 'ifquant.ordinal-agreement-results/1', 'plan': config, 'input': file_record(path),
           'paired_units': n, 'incomplete_units': len(units)-n, 'confusion_matrix': matrix,
           'exact_agreement_fraction': sum(a == b for a, b in complete)/n, 'linear_weighted_kappa': kappa,
           'kappa_status': 'estimated' if kappa is not None else 'undefined_marginals',
           'scientific_validation': False, 'interpretation': 'descriptive agreement on supplied units; no reviewer correctness or injury validity claim'}
    write_json(output, doc)
    return {'output': str(output), 'paired_units': n, 'linear_weighted_kappa': kappa}
