"""Reconcile reported RCC NMS tables, not a cell-level spatial reproduction."""
from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from ifquant_platform.imaging import require, write_json
from ifquant_platform.spatial import file_record

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def sheet_rows(path, sheet_name):
    with zipfile.ZipFile(path) as archive:
        strings = [''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        names = [s.attrib['name'] for s in workbook.find('m:sheets', NS)]
        require(sheet_name in names, 'source workbook sheet missing')
        # Resolve relationships rather than assuming sheet numbering.
        sheet = workbook.find('m:sheets', NS)[names.index(sheet_name)]
        rid = sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next(r.attrib['Target'] for r in rels if r.attrib['Id'] == rid)
        target = target.lstrip('/') if target.startswith('/') else 'xl/'+target
        rows = []
        for row in ET.fromstring(archive.read(target)).findall('m:sheetData/m:row', NS):
            record = {}
            for cell in row:
                column = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                value = cell.findtext('m:v', None, NS)
                if cell.attrib.get('t') == 's' and value is not None:
                    value = strings[int(value)]
                if cell.attrib.get('t') == 'inlineStr':
                    value = ''.join(cell.find('m:is', NS).itertext())
                record[column] = value
            rows.append(record)
        return rows


def nms_table(rows):
    require(rows[1].get('A') == 'Sample' and rows[1].get('B') == 'Reference target pair' and
            rows[1].get('E') == 'Radius', 'unexpected NMS source columns')
    records, sample, pair = {}, None, None
    for row in rows[2:]:
        if row.get('A'): sample = row['A']
        if row.get('B'): pair = row['B']
        if row.get('E') is None:
            continue
        require(sample and pair, 'NMS source group is missing')
        key = (sample, pair, float(row['E']))
        value = (float(row['C']), float(row['D']))
        require(key not in records and all(math.isfinite(v) for v in (*key[-1:], *value)) and
                key[-1] > 0 and value[0] >= 0 and 0 <= value[1] <= 1, 'invalid/duplicate NMS source row')
        records[key] = value
    return records


def reconcile(supplement, figures, output):
    first = nms_table(sheet_rows(supplement, 'Supplementary Table 13'))
    second = nms_table(sheet_rows(figures, 'Fig. 3c'))
    require(first and set(first) == set(second), 'reported table/figure hypothesis keys differ')
    differences = [{'sample': key[0], 'pair': key[1], 'radius_pixels': key[2], 'table': first[key], 'figure': second[key]}
                   for key in first if any(not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-9) for a, b in zip(first[key], second[key]))]
    report = {'schema_version': 'ifquant.published-source-reconciliation/1',
        'article': 'https://www.nature.com/articles/s41587-026-03194-1',
        'inputs': [file_record(supplement), file_record(figures)], 'sample': 'RCC_1_A',
        'comparison': 'Supplementary Table 13 against Figure 3c source data',
        'rows': len(first), 'pairs': len({key[1] for key in first}), 'radii_pixels': sorted({key[2] for key in first}),
        'differing_rows': differences, 'status': 'matched' if not differences else 'differences_found',
        'scientific_validation': False,
        'scope': 'reconciles published statistics only; source tables lack cell coordinates/edge counts; no recomputed NMS or permutation p-values'}
    write_json(output, report)
    return {k: report[k] for k in ('rows', 'pairs', 'status', 'scope')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supplement', type=Path, required=True)
    parser.add_argument('--figures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(reconcile(args.supplement, args.figures, args.output))
