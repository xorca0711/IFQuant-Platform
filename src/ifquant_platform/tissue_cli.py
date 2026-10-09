"""Optional tissue-workflow CLI surface. No image dependencies at import time."""
from __future__ import annotations


def _register(args):
    from .imaging import register_image
    return register_image(args.image, args.output, subject_id=args.subject_id,
                          species=args.species, specimen_id=args.specimen_id,
                          section_id=args.section_id, pixel_size_x=args.pixel_size_x,
                          pixel_size_y=args.pixel_size_y, modality=args.modality,
                          reader=args.reader, series=args.series, level=args.level,
                          members=args.source_member)


def _plan(args):
    from .imaging import create_plan
    return create_plan(args.source, args.output, tile_size=args.tile_size, halo=args.halo)


def _regions(args):
    from .histology import import_geojson
    return import_geojson(args.source, args.geojson, args.output,
                          reviewer=args.reviewer, reason=args.reason, parent=args.parent)


def _fit(args):
    from .histology import fit_model
    return fit_model(args.source, args.output, profile_path=args.profile,
                     regions_path=args.regions, clusters=args.clusters, seed=args.seed,
                     max_samples=args.max_samples, supervised=args.supervised)


def _run(args):
    from .tissue_workflow import run_histology
    return run_histology(args.source, args.model, args.regions, args.output,
                         tile_size=args.tile_size, dense_classes=args.dense_class,
                         resume=args.resume, max_tiles=args.max_tiles)


def _validate(args):
    from .tissue_workflow import validate_histology
    return validate_histology(args.package)


def _demo(args):
    from .tissue_workflow import demo_histology
    return demo_histology(args.output)


def _review(args):
    from .tissue_reporting import review_template
    return review_template(args.package, args.rubric, args.output)


def _specimens(args):
    from .tissue_reporting import specimen_report
    return specimen_report(args.packages, args.output, reviews=args.review)


def _cells(args):
    from .tissue_reporting import cell_report
    return cell_report(args.package, args.output, radius_um=args.radius_um,
                       thresholds_path=args.thresholds)


def add_commands(parsers):
    p = parsers.add_parser('register-image', help='register calibrated 2D image and source members')
    p.add_argument('image')
    p.add_argument('--output', required=True)
    for field in ('subject-id', 'species', 'specimen-id', 'section-id'):
        p.add_argument('--' + field, required=True)
    p.add_argument('--pixel-size-x', type=float, required=True, help='base image micrometers/pixel')
    p.add_argument('--pixel-size-y', type=float, required=True, help='base image micrometers/pixel')
    p.add_argument('--modality', choices=['he', 'fluorescence'], default='he')
    p.add_argument('--reader', choices=['tiff', 'pillow'], default='tiff')
    p.add_argument('--series', type=int, default=0)
    p.add_argument('--level', type=int, default=0)
    p.add_argument('--source-member', action='append', default=[])
    p.set_defaults(handler=_register)
    p = parsers.add_parser('plan-tiles', help='create a calibrated image tile ownership plan')
    p.add_argument('source')
    p.add_argument('--output', required=True)
    p.add_argument('--tile-size', type=int, default=512)
    p.add_argument('--halo', type=int, default=0)
    p.set_defaults(handler=_plan)
    p = parsers.add_parser('import-regions', help='import QuPath Polygon GeoJSON as a new region revision')
    p.add_argument('source')
    p.add_argument('--geojson', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--parent', help='prior immutable region revision')
    p.add_argument('--reviewer', help='explicitly accepts imported regions under this reviewer identity')
    p.add_argument('--reason', default='')
    p.set_defaults(handler=_regions)
    p = parsers.add_parser('fit-histology', help='fit a frozen H&E appearance model on development data')
    p.add_argument('source')
    p.add_argument('--output', required=True)
    p.add_argument('--profile')
    p.add_argument('--regions')
    p.add_argument('--clusters', type=int, default=4)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--max-samples', type=int, default=30000)
    p.add_argument('--supervised', action='store_true', help='use accepted training-region labels')
    p.set_defaults(handler=_fit)
    p = parsers.add_parser('run-histology', help='run tiled H&E candidates, exclusions and region measurements')
    p.add_argument('source')
    p.add_argument('--model', required=True)
    p.add_argument('--regions', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--tile-size', type=int, default=512)
    p.add_argument('--dense-class', action='append', default=[], help='explicit candidate-class mapping, not grade')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--max-tiles', type=int, help='stop after a bounded number of verified tiles for resume testing')
    p.set_defaults(handler=_run)
    p = parsers.add_parser('validate-histology', help='verify package hashes, grid coverage and pixel counts')
    p.add_argument('package')
    p.set_defaults(handler=_validate)
    p = parsers.add_parser('demo-histology', help='generate and analyze a wholly synthetic H&E fixture')
    p.add_argument('--output', required=True)
    p.set_defaults(handler=_demo)
    p = parsers.add_parser('review-template', help='create an unfilled rubric-bound ordinal form')
    p.add_argument('package')
    p.add_argument('--rubric', required=True)
    p.add_argument('--output', required=True)
    p.set_defaults(handler=_review)
    p = parsers.add_parser('report-specimens', help='pool eligible region areas, retain ordinal counts')
    p.add_argument('packages', nargs='+')
    p.add_argument('--output', required=True)
    p.add_argument('--review', action='append', default=[])
    p.set_defaults(handler=_specimens)
    p = parsers.add_parser('report-cells', help='calibrated IF features, marker rules and radius neighbors')
    p.add_argument('package')
    p.add_argument('--output', required=True)
    p.add_argument('--radius-um', type=float, default=25)
    p.add_argument('--thresholds')
    p.set_defaults(handler=_cells)
