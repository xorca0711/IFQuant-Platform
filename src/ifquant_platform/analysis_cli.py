"""Optional imaging evaluation and molecular/spatial analysis commands."""


def _benchmark(args):
    from .imaging_evaluation import benchmark_image
    return benchmark_image(args.source, args.output, tile_size=args.tile_size, tiles=args.tiles, seed=args.seed)


def _masks(args):
    from .imaging_evaluation import compare_masks
    return compare_masks(args.config, args.output)


def _agreement(args):
    from .imaging_evaluation import reviewer_agreement
    return reviewer_agreement(args.config, args.output)


def _programs(args):
    from .molecular_programs import score_programs
    return score_programs(args.config, args.output)


def _hypotheses(args):
    from .spatial_statistics import spatial_hypotheses
    return spatial_hypotheses(args.config, args.output)


def _ngff(args):
    from .upstream_interchange import import_ngff_window
    return import_ngff_window(args.config, args.output)


def _features(args):
    from .upstream_interchange import import_cell_features
    return import_cell_features(args.config, args.output)


def _registration(args):
    from .registration_qc import evaluate_registration
    return evaluate_registration(args.config, args.output)


def _valis_pair(args):
    from .valis_execution import run_valis_pair
    return run_valis_pair(args.config, args.output)


def _gotags(args):
    from .gotags_adapter import import_gotags
    return import_gotags(args.config, args.output)


def _domains(args):
    from .spatial_domains import domain_baselines
    return domain_baselines(args.config, args.output)


def _instanseg(args):
    from .instance_segmentation import segment_instanseg
    return segment_instanseg(args.config, args.output)


def _instanseg_slide(args):
    from .whole_slide_instances import run_tiled_instanseg
    return run_tiled_instanseg(args.config, args.output, resume=args.resume, max_tiles=args.max_tiles)


def _validate_instanseg_slide(args):
    from .whole_slide_instances import validate_tiled_instanseg
    return validate_tiled_instanseg(args.output)


def _profiles(args):
    from .morphology_profiles import measure_profiles
    return measure_profiles(args.config, args.output)


def _associations(args):
    from .associations import specimen_associations
    return specimen_associations(args.config, args.output)


def add_commands(parsers):
    p = parsers.add_parser('segment-instanseg-slide', help='stitch resumable tiled nuclei across a complete selected source grid')
    p.add_argument('config')
    p.add_argument('--output', required=True)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--max-tiles', type=int)
    p.set_defaults(handler=_instanseg_slide)
    p = parsers.add_parser('validate-instanseg-slide', help='rebuild and verify a completed tiled nuclei package')
    p.add_argument('output')
    p.set_defaults(handler=_validate_instanseg_slide)
    p = parsers.add_parser('benchmark-image', help='measure reproducible source-window reads and process memory')
    p.add_argument('source')
    p.add_argument('--output', required=True)
    p.add_argument('--tile-size', type=int, default=512)
    p.add_argument('--tiles', type=int, default=64)
    p.add_argument('--seed', type=int, default=0)
    p.set_defaults(handler=_benchmark)
    for name, handler, description in (
        ('compare-masks', _masks, 'compare explicit class masks against a reviewed/synthetic reference'),
        ('reviewer-agreement', _agreement, 'summarize paired ordinal reviews without filling missing scores'),
        ('score-rna-programs', _programs, 'score versioned RNA programs with explicit coverage and normalization'),
        ('test-spatial-hypotheses', _hypotheses, 'run predeclared mixing hypotheses with conditioned nulls'),
        ('import-ngff-window', _ngff, 'read a bounded calibrated NGFF 0.4/0.5 plane with explicit axes'),
        ('import-cell-features', _features, 'map MCMICRO-compatible numeric cell measurements explicitly'),
        ('evaluate-registration', _registration, 'evaluate portable VALIS point results and independent landmarks'),
        ('register-valis-pair', _valis_pair, 'execute pinned VALIS on declared public or private brightfield PNG planes'),
        ('import-slide-gotags', _gotags, 'import processed MC38-OVA author annotations with coverage gates'),
        ('domain-baselines', _domains, 'compare bounded expression-only and graph-smoothed exploratory clusters'),
        ('segment-instanseg', _instanseg, 'run pinned CPU brightfield nuclei inference on a calibrated bounded ROI'),
        ('measure-morphology-profiles', _profiles, 'measure calibrated reviewed cuff profiles and septal transects'),
        ('specimen-associations', _associations, 'test paired morphology/RNA summaries at biological-unit level')):
        p = parsers.add_parser(name, help=description)
        p.add_argument('config')
        p.add_argument('--output', required=True)
        p.set_defaults(handler=handler)
