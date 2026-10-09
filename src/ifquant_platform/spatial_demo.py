"""A tiny synthetic registration, region/RNA, genotype and TCR fixture."""
from __future__ import annotations

from pathlib import Path

from .canonical import canonical_sha256, load_strict_json
from .histology import import_geojson
from .imaging import register_image, write_json
from .molecular_context import attach_context
from .spatial import import_assay, link_spatial


def demo_spatial(output):
    from PIL import Image

    root = Path(output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    Image.new('RGB', (120, 80), (218, 159, 193)).save(root/'synthetic.png')
    register_image(root/'synthetic.png', root/'source.json', subject_id='synthetic-subject',
                   species='synthetic', specimen_id='synthetic-lung', section_id='section-1',
                   pixel_size_x=.5, pixel_size_y=.8, reader='pillow')
    source = load_strict_json(root/'source.json')
    polygons = [('left', 'reference', [[0, 0], [60, 0], [60, 80], [0, 80], [0, 0]]),
                ('right', 'reference', [[60, 0], [120, 0], [120, 80], [60, 80], [60, 0]]),
                ('artifact', 'artifact', [[100, 0], [120, 0], [120, 20], [100, 20], [100, 0]])]
    write_json(root/'regions.geojson', {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'id': rid, 'geometry': {'type': 'Polygon', 'coordinates': [xy]},
         'properties': {'role': role, 'anatomy': 'alveolar_parenchyma', 'label': rid}}
        for rid, role, xy in polygons]})
    import_geojson(root/'source.json', root/'regions.geojson', root/'regions.json')
    (root/'observations.csv').write_text('observation_id,x,y,assay_status\n'
        'n1,5,5,measured\nn2,40,20,measured\nn3,30,20,measured\nn4,55,5,measured\n'
        'n5,100,100,failed\nn6,10,10,not_assayed\n', encoding='utf-8')
    (root/'features.csv').write_text('feature_id,feature_name\nf1,SyntheticGeneA\nf2,SyntheticGeneB\n', encoding='utf-8')
    (root/'counts.csv').write_text('observation_id,feature_id,count\nn1,f1,5\nn2,f1,2\nn2,f2,4\nn3,f1,1\nn4,f2,7\n', encoding='utf-8')
    config = {'schema_version': 'ifquant.spatial-import/1', 'assay_id': 'synthetic-rna',
              'subject': source['subject'], 'entity_type': 'nucleus',
              'coordinate_frame': {'frame_id': 'synthetic-assay-pixels', 'unit': 'pixel',
                                   'axes': ['x', 'y'], 'origin': 'top_left', 'y_direction': 'down'},
              'observations_csv': 'observations.csv', 'features_csv': 'features.csv', 'counts_csv': 'counts.csv'}
    write_json(root/'import.json', config)
    import_assay(root/'import.json', root/'assay.json')
    assay = load_strict_json(root/'assay.json')
    transform = {'schema_version': 'ifquant.affine-transform/1', 'assay_sha256': canonical_sha256(assay),
                 'source_sha256': canonical_sha256(source), 'from_frame': config['coordinate_frame']['frame_id'],
                 'to_frame': 'base_image_pixels', 'section_relation': 'same_section',
                 'matrix': [[2, 0, 0], [0, 2, 0], [0, 0, 1]], 'method': 'provided_affine',
                 'landmarks': [{'landmark_id': 'synthetic-check', 'role': 'evaluation', 'from': [12, 15], 'to': [24, 30]}]}
    write_json(root/'transform.json', transform)
    linked = link_spatial(root/'assay.json', root/'source.json', root/'regions.json', root/'transform.json',
                          root/'linked', uncertainty_um=.25)
    (root/'molecular.csv').write_text('observation_id,modality,target_id,status,value,coverage\n'
        'n1,transcript_genotype,synthetic-variant,measured,alternate_detected,5\n'
        'n2,transcript_genotype,synthetic-variant,measured,reference_only,3\n'
        'n3,transcript_genotype,synthetic-variant,ambiguous,,1\n'
        'n6,transcript_genotype,synthetic-variant,not_assayed,,\n'
        'n2,tcr,synthetic-clonotype-assay,measured,synthetic-clone-1,2\n'
        'n5,tcr,synthetic-clonotype-assay,failed,,0\n', encoding='utf-8')
    attached = attach_context(root/'assay.json', root/'molecular.csv', root/'context.json')
    return {'output': str(root), 'links': linked['status_counts'], 'molecular': attached['status_counts'],
            'scientific_validation': False, 'data_kind': 'entirely_synthetic'}
