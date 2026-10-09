"""CLI entry points for the stage 5/6 engineering foundation."""
from __future__ import annotations


def _import(args):
    from .spatial import import_assay
    return import_assay(args.config, args.output)


def _validate(args):
    from .canonical import canonical_sha256, load_strict_json
    from .spatial import validate_assay
    doc = validate_assay(load_strict_json(args.assay))
    return {'status': 'valid', 'assay_sha256': canonical_sha256(doc), 'scientific_validation': False}


def _link(args):
    from .spatial import link_spatial
    return link_spatial(args.assay, args.source, args.regions, args.transform, args.output,
                        uncertainty_um=args.boundary_uncertainty_um)


def _context(args):
    from .molecular_context import attach_context
    return attach_context(args.assay, args.calls, args.output)


def _demo(args):
    from .spatial_demo import demo_spatial
    return demo_spatial(args.output)


def add_commands(parsers):
    p = parsers.add_parser('import-spatial', help='import explicit XY observations and sparse raw RNA counts')
    p.add_argument('config')
    p.add_argument('--output', required=True)
    p.set_defaults(handler=_import)
    p = parsers.add_parser('validate-spatial', help='validate assay hashes, exact IDs and raw-count semantics')
    p.add_argument('assay')
    p.set_defaults(handler=_validate)
    p = parsers.add_parser('link-spatial', help='link assay point centers to tissue regions using an explicit affine')
    p.add_argument('assay')
    p.add_argument('--source', required=True)
    p.add_argument('--regions', required=True)
    p.add_argument('--transform', required=True)
    p.add_argument('--boundary-uncertainty-um', type=float, default=0)
    p.add_argument('--output', required=True)
    p.set_defaults(handler=_link)
    p = parsers.add_parser('attach-molecular-context', help='attach processed transcript genotype/TCR calls by exact ID')
    p.add_argument('assay')
    p.add_argument('--calls', required=True)
    p.add_argument('--output', required=True)
    p.set_defaults(handler=_context)
    p = parsers.add_parser('demo-spatial', help='synthetic tissue/RNA/processed-molecular integration example')
    p.add_argument('--output', required=True)
    p.set_defaults(handler=_demo)
