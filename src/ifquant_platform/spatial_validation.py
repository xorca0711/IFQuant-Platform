"""Independent validation of published links and molecular-context products.

Original input files are required; validation never rewrites a completed output.
Producer hashes identify historical code, not the current validator version.
"""
import re
from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .histology import validate_regions
from .imaging import require, validate_source
from .molecular_context import build_context
from .spatial import build_links, links_csv, links_html, validate_assay, verify_file


def _equal_product(actual, expected):
    require(set(actual) == set(expected), 'published product fields differ')
    producer = actual['producer_sha256']
    require(isinstance(producer, str) and re.fullmatch('[a-f0-9]{64}', producer),
            'invalid historical producer hash')
    expected['producer_sha256'] = producer
    require(canonical_sha256(actual) == canonical_sha256(expected),
            'published product differs from recomputed inputs')


def validate_links(package, assay_path, source_path, regions_path):
    root = Path(package)
    doc = load_strict_json(root/'links.json')
    assay = validate_assay(load_strict_json(assay_path))
    source = validate_source(load_strict_json(source_path))
    regions = validate_regions(load_strict_json(regions_path), source)
    expected = build_links(assay, source, regions, doc['transform'], doc['boundary_uncertainty_um'])
    _equal_product(doc, expected)
    require((root/'links.csv').read_bytes() == links_csv(expected).encode('utf-8'),
            'published links CSV differs')
    require((root/'report.html').read_text(encoding='utf-8') == links_html(expected),
            'published links report differs')
    return {'status': 'valid', 'product_sha256': canonical_sha256(doc),
            'observations': len(doc['links']), 'scientific_validation': False}


def validate_context(context_path, assay_path):
    doc = load_strict_json(context_path)
    assay = validate_assay(load_strict_json(assay_path))
    verify_file(doc['input'])
    _equal_product(doc, build_context(assay, doc['input']['path']))
    return {'status': 'valid', 'product_sha256': canonical_sha256(doc),
            'observations': len(doc['observations']), 'scientific_validation': False}
