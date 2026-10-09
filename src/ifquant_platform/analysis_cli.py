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


def _gotags(args):
    from .gotags_adapter import import_gotags
    return import_gotags(args.config, args.output)


def _domains(args):
    from .spatial_domains import domain_baselines
    return domain_baselines(args.config, args.output)


def _profiles(args):
    from .morphology_profiles import measure_profiles
    return measure_profiles(args.config, args.output)


def _associations(args):
    from .associations import specimen_associations
    return specimen_associations(args.config, args.output)


def add_commands(parsers):
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
        ('import-ngff-window', _ngff, 'read a bounded calibrated NGFF 0.4 YX/CYX window'),
        ('import-cell-features', _features, 'map MCMICRO-compatible numeric cell measurements explicitly'),
        ('evaluate-registration', _registration, 'evaluate portable VALIS point results and independent landmarks'),
        ('import-slide-gotags', _gotags, 'import processed MC38-OVA author annotations with coverage gates'),
        ('domain-baselines', _domains, 'compare bounded expression-only and graph-smoothed exploratory clusters'),
        ('measure-morphology-profiles', _profiles, 'measure calibrated reviewed cuff profiles and septal transects'),
        ('specimen-associations', _associations, 'test paired morphology/RNA summaries at biological-unit level')):
        p = parsers.add_parser(name, help=description)
        p.add_argument('config')
        p.add_argument('--output', required=True)
        p.set_defaults(handler=handler)
