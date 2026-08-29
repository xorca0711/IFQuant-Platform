# Frozen G-SURF compatibility boundary

This directory is an isolated compatibility and regression edge for the
historical G-SURF implementation. It is not an authority directory and is not a
template for the new platform.

The separate historical `IFQuant-Lung` source repository remains read-only. Any
compatibility exercise must identify an explicit committed revision and the
specific legacy behavior being checked. An uncommitted working tree is never an
input or dependency.

This directory may contain:

- documentation of a pinned legacy interface;
- small, purpose-built compatibility descriptors;
- adapters that translate explicitly supplied legacy-shaped test data; and
- synthetic or separately governed regression fixtures with documented origin.

It must not contain copied authority state, settled release outputs, production
pipeline trees, historical scripts imported as new-core code, or mutable links
that make `ifquant_platform` depend on the source repository. Fiji is retained
only as a frozen comparison/regression reference.

Compatibility means that a declared legacy case can be inspected or translated.
It does not mean Fiji and QuPath are scientifically equivalent, that legacy
thresholds transfer to a new acquisition domain, or that historical outputs are
valid training labels.
