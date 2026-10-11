"""Shared explicit library-denominator validation for RNA analyses."""
import csv
from pathlib import Path

from .imaging import require
from .spatial import file_record


def library_totals(data, basis, path=None):
    import numpy as np
    selected = np.asarray(data.X.astype(float).sum(axis=1)).ravel()
    require(np.isfinite(selected).all() and (selected >= 0).all() and (selected <= 2**53-1).all(),
            'invalid selected library total')
    require(basis in ('selected_features', 'external_full_library'), 'explicit normalization basis required')
    if basis == 'selected_features':
        require(path is None, 'selected-feature normalization cannot carry full-library input')
        return selected, None
    require(path is not None, 'full-library totals required')
    record, rows, ids = file_record(path), {}, set(data.obs_names)
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == ['observation_id', 'total_counts'], 'invalid full-library table')
        for row in reader:
            require(set(row) == {'observation_id', 'total_counts'} and all(v is not None for v in row.values()), 'malformed full-library row')
            oid, value = row['observation_id'], row['total_counts']
            require(oid in ids and oid not in rows, 'unknown/duplicate full-library observation')
            require(value.isascii() and value.isdigit(), 'integer library total required')
            total = int(value)
            require(total <= 2**53-1, 'full library exceeds safe integer capacity')
            rows[oid] = total
    require(set(rows) == ids, 'complete full-library table required')
    values = np.array([rows[oid] for oid in data.obs_names], dtype=float)
    require(np.all(values >= selected), 'full library cannot be smaller than selected counts')
    require(file_record(path) == record, 'full-library input changed during analysis')
    return values, record
