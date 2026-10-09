"""Pinned acquisition and source-table guard checks without network traffic."""
import hashlib
import importlib.util
import io
import sys
from pathlib import Path

import pytest

from ifquant_platform.canonical import ContractError

scripts = Path(__file__).resolve().parents[1]/'scripts'
for name in ('reconcile_gotags_source', 'replay_public_qualification'):
    spec = importlib.util.spec_from_file_location(name, scripts/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
replay = sys.modules['replay_public_qualification']
source = sys.modules['reconcile_gotags_source']


def test_pinned_range_rejects_truncation_and_does_not_publish(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        status = 206
        @property
        def headers(self):
            return {'Content-Range': 'bytes 0-3/4'}
    monkeypatch.setattr(replay.urllib.request, 'urlopen', lambda *a, **k: Response(b'abc'))
    record = {'name': 'nested/file', 'size_bytes': 4, 'sha256': hashlib.sha256(b'abcd').hexdigest(), 'url': 'https://example.invalid/file'}
    with pytest.raises(ContractError, match='truncated'):
        replay.acquire(record, tmp_path, True)
    assert not (tmp_path/'nested/file').exists()
    monkeypatch.setattr(replay.urllib.request, 'urlopen', lambda *a, **k: Response(b'abcd'))
    assert replay.acquire(record, tmp_path, True).read_bytes() == b'abcd'
    (tmp_path/'nested/file').write_bytes(b'bad!')
    with pytest.raises(ContractError, match='cached'):
        replay.acquire(record, tmp_path, False)


def test_reported_nms_merges_group_labels_but_rejects_duplicate_hypotheses():
    rows = [{}, {'A': 'Sample', 'B': 'Reference target pair', 'E': 'Radius'},
            {'A': 's', 'B': 'r-t', 'C': '0.5', 'D': '0.02', 'E': '10'},
            {'A': None, 'B': None, 'C': '1.5', 'D': '.1', 'E': '20'}]
    assert source.nms_table(rows) == {('s', 'r-t', 10.): (.5, .02), ('s', 'r-t', 20.): (1.5, .1)}
    with pytest.raises(ContractError, match='duplicate'):
        source.nms_table(rows+[rows[-1]])
