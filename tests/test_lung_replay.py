"""Acquisition safety/reproducibility without network or source-data downloads in CI."""
import gzip
import hashlib
import importlib.util
from pathlib import Path

import pytest

from ifquant_platform.canonical import ContractError

spec = importlib.util.spec_from_file_location('lung_replay', Path(__file__).resolve().parents[1]/'scripts/replay_lung_example.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def test_cached_source_and_decompressed_drift(tmp_path):
    content = gzip.compress(b'fixed source bytes', mtime=0)
    (tmp_path/'input.txt.gz').write_bytes(content)
    manifest = {'files': [{'name': 'input.txt.gz', 'url': 'https://example.invalid/no-network',
                          'size_bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}]}
    paths = replay.acquire(manifest, tmp_path, False)
    assert paths['input.txt.gz'].read_bytes() == b'fixed source bytes'
    paths['input.txt.gz'].write_bytes(b'changed')
    with pytest.raises(ContractError, match='decompressed cache differs'):
        replay.acquire(manifest, tmp_path, False)


def test_missing_cache_requires_explicit_download(tmp_path):
    with pytest.raises(ContractError, match='supply --download'):
        replay.acquire({'files': [{'name': 'missing', 'url': 'https://example.invalid/no-network'}]}, tmp_path, False)
