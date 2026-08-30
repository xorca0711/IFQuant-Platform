"""Fail-closed validation for Phase 3 nuclear references and split designs.

The validators in this module are intentionally read-only.  They validate a
reviewed DAPI nuclear-instance reference ledger and an image-level split
manifest while recursively retaining the Phase 2 governed-observation
boundary.  Passing either validator is an engineering integrity result; it is
not biological ground truth, scientific validation, or downstream
authorization.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .canonical import (
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    parse_strict_json,
)
from .dataset_governance import (
    GOVERNED_OBSERVATION_SET_SCHEMA,
    GovernedObservationSetReport,
    validate_governed_observation_set,
)
from .package_validation import (
    _array,
    _enum,
    _exact,
    _identifier,
    _integer,
    _load_mapping,
    _nonempty,
    _object,
    _require,
    _safe_relative,
    _semver,
    _sha256,
    _timestamp,
    _tokenize_wkt,
    _validate_wkt,
)


NUCLEAR_REFERENCE_OBJECT_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/nuclear-reference-object.schema.json"
)
REFERENCE_IGNORE_REGION_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/reference-ignore-region.schema.json"
)
NUCLEAR_REFERENCE_SET_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/nuclear-reference-set.schema.json"
)
SPLIT_MANIFEST_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/split-manifest.schema.json"
)

_PARTITIONS = ("train", "tuning", "held_out_test")
_HARD_SEPARATION_KEYS = ("mouse_id", "slide_id", "source_family_id")
_DOMAIN_KEYS = ("batch_id", "scanner_id")
HELD_OUT_REFERENCE_CONTENT_PROFILE = "ifquant_held_out_reference_content_v1"
_IGNORE_CODES = {
    "physical_edge": {"physical_image_edge", "physical_specimen_edge"},
    "ambiguity": {
        "ambiguous_nuclear_boundary",
        "overlapping_nuclei_not_separable",
    },
    "artifact": {
        "acquisition_artifact",
        "staining_artifact",
        "processing_artifact",
    },
    "unscorable": {
        "insufficient_dapi_signal",
        "saturated_dapi_signal",
        "out_of_focus",
        "other_unscorable",
    },
}


@dataclass(frozen=True, slots=True)
class NuclearReferenceSetReport:
    """Deterministic summary of Phase 3 nuclear-reference integrity checks."""

    status: str
    reference_set_id: str
    study_id: str
    revision: int
    reference_set_sha256: str
    governed_observation_set_id: str
    governed_observation_set_revision: int
    governed_observation_set_sha256: str
    image_count: int
    source_family_count: int
    region_count: int
    nuclear_reference_object_count: int
    reference_ignore_region_count: int
    model_assisted_object_count: int
    model_assisted_single_review_count: int
    model_assisted_nonconfirmatory_review_count: int
    confirmatory_reference_ready: bool
    authorization: str = "none"
    scientific_validation: bool = False
    biological_ground_truth: bool = False
    backend_equivalence: bool = False
    model_universality: bool = False
    validation_scope: str = (
        "reviewed nuclear-reference structure, canonical polygon topology, image/ROI "
        "containment, nuclear/ignore separation, edge-reason consistency, per-image "
        "readiness, full governed-revision chronology, nonempty observation-set producer-code "
        "attestation, lineage, source-family coverage, and byte integrity only; not biological "
        "correctness, scientific validation, holdout independence, model universality, or "
        "downstream authorization"
    )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SplitManifestReport:
    """Deterministic summary of Phase 3 image-split integrity checks."""

    status: str
    split_manifest_id: str
    study_id: str
    revision: int
    split_manifest_sha256: str
    reference_set_id: str
    reference_set_revision: int
    reference_set_sha256: str
    assignment_count: int
    train_count: int
    tuning_count: int
    held_out_test_count: int
    held_out_test_image_ids_sha256: str
    held_out_test_reference_content_sha256: str
    held_out_test_locked: bool
    hard_separation_keys: tuple[str, ...] = _HARD_SEPARATION_KEYS
    hard_group_overlap_count: int = 0
    authorization: str = "none"
    scientific_validation: bool = False
    biological_ground_truth: bool = False
    backend_equivalence: bool = False
    model_universality: bool = False
    split_optimality: bool = False
    population_representativeness: bool = False
    domain_generalizability: bool = False
    validation_scope: str = (
        "exact image assignment, all-governed-image hard-component separation, declared "
        "domain controls, recursive reference integrity, successor chronology, and an exact "
        "held-out reference-content lock only; not proof of hidden relatedness, biological "
        "correctness, statistical adequacy, domain generalizability, scientific validation, "
        "or downstream authorization"
    )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["hard_separation_keys"] = list(self.hard_separation_keys)
        return value


@dataclass(frozen=True, slots=True)
class _ImageContext:
    image_id: str
    biological_unit_id: str
    coordinate_space_id: str
    mouse_id: str
    slide_id: str
    batch_id: str
    scanner_id: str
    source_sha256: str
    width_pixels: int
    height_pixels: int
    include_annotation_ids: frozenset[str]
    include_annotation_geometries: Mapping[str, _ParsedGeometry]


@dataclass(frozen=True, slots=True)
class _GovernedContext:
    report: GovernedObservationSetReport
    document: Mapping[str, Any]
    images: Mapping[str, _ImageContext]
    observations_by_image: Mapping[str, Mapping[str, Any]]
    upstream_timestamps: tuple[tuple[str, datetime], ...]
    revision_chronology: tuple[tuple[str, datetime, str, datetime], ...]


@dataclass(frozen=True, slots=True)
class _ReferenceContext:
    report: NuclearReferenceSetReport
    document: Mapping[str, Any]
    governed: _GovernedContext
    source_family_by_image: Mapping[str, str]
    reference_image_ids: frozenset[str]
    confirmatory_ready_by_image: Mapping[str, bool]
    regions_by_scope: Mapping[tuple[str, str], Mapping[str, Any]]
    nuclear_records: tuple[Mapping[str, Any], ...]
    ignore_records: tuple[Mapping[str, Any], ...]
    parent: _ReferenceContext | None


@dataclass(frozen=True, slots=True)
class _SplitContext:
    report: SplitManifestReport
    document: Mapping[str, Any]
    assignments_by_image: Mapping[str, Mapping[str, Any]]
    reference: _ReferenceContext
    parent: _SplitContext | None


_Point = tuple[Decimal, Decimal]
_Ring = tuple[_Point, ...]
_Polygon = tuple[_Ring, ...]


@dataclass(frozen=True, slots=True)
class _ParsedGeometry:
    geometry_type: str
    polygons: tuple[_Polygon, ...]


def _canonical_decimal(token: str) -> str:
    number = Decimal(token)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _parse_polygon_geometry(
    geometry_type: str,
    wkt: str,
    location: str,
) -> _ParsedGeometry:
    prefix = geometry_type
    _require(wkt.startswith(prefix), f"{location}.wkt does not match geometry_type")
    tokens = _tokenize_wkt(wkt[len(prefix) :], location)
    cursor = 0

    def consume(expected: str | None = None) -> str:
        nonlocal cursor
        _require(cursor < len(tokens), f"{location}.wkt ends unexpectedly")
        token = tokens[cursor]
        if expected is not None:
            _require(token == expected, f"{location}.wkt expected '{expected}'")
        cursor += 1
        return token

    def coordinate() -> _Point:
        x = consume()
        y = consume()
        _require(
            x not in {"(", ")", ","} and y not in {"(", ")", ","},
            f"{location}.wkt coordinate is incomplete",
        )
        return Decimal(x), Decimal(y)

    def ring() -> _Ring:
        consume("(")
        points = [coordinate()]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            points.append(coordinate())
        consume(")")
        return tuple(points)

    def polygon() -> _Polygon:
        consume("(")
        rings = [ring()]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            rings.append(ring())
        consume(")")
        return tuple(rings)

    if geometry_type == "POLYGON":
        polygons = (polygon(),)
    else:
        consume("(")
        values = [polygon()]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            values.append(polygon())
        consume(")")
        polygons = tuple(values)
    _require(cursor == len(tokens), f"{location}.wkt has trailing tokens")
    return _ParsedGeometry(geometry_type=geometry_type, polygons=polygons)


def _cross(left: _Point, middle: _Point, right: _Point) -> Decimal:
    return (
        (middle[0] - left[0]) * (right[1] - left[1])
        - (middle[1] - left[1]) * (right[0] - left[0])
    )


def _ring_area_twice(ring: _Ring) -> Decimal:
    return sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(ring, ring[1:])
    )


def _point_on_segment(point: _Point, left: _Point, right: _Point) -> bool:
    return (
        _cross(left, right, point) == 0
        and min(left[0], right[0]) <= point[0] <= max(left[0], right[0])
        and min(left[1], right[1]) <= point[1] <= max(left[1], right[1])
    )


def _segments_intersect(
    left_a: _Point,
    left_b: _Point,
    right_a: _Point,
    right_b: _Point,
) -> bool:
    first = _cross(left_a, left_b, right_a)
    second = _cross(left_a, left_b, right_b)
    third = _cross(right_a, right_b, left_a)
    fourth = _cross(right_a, right_b, left_b)
    if first == 0 and _point_on_segment(right_a, left_a, left_b):
        return True
    if second == 0 and _point_on_segment(right_b, left_a, left_b):
        return True
    if third == 0 and _point_on_segment(left_a, right_a, right_b):
        return True
    if fourth == 0 and _point_on_segment(left_b, right_a, right_b):
        return True
    return (first > 0) != (second > 0) and (third > 0) != (fourth > 0)


def _ring_segments(ring: _Ring) -> tuple[tuple[_Point, _Point], ...]:
    return tuple(zip(ring, ring[1:]))


def _boundaries_intersect(left: _Polygon, right: _Polygon) -> bool:
    return any(
        _segments_intersect(left_a, left_b, right_a, right_b)
        for left_ring in left
        for left_a, left_b in _ring_segments(left_ring)
        for right_ring in right
        for right_a, right_b in _ring_segments(right_ring)
    )


def _point_in_ring(point: _Point, ring: _Ring) -> int:
    """Return -1 outside, 0 on the boundary, or 1 inside a simple ring."""

    inside = False
    for left, right in _ring_segments(ring):
        if _point_on_segment(point, left, right):
            return 0
        if (left[1] > point[1]) == (right[1] > point[1]):
            continue
        left_side = (right[0] - left[0]) * (point[1] - left[1])
        right_side = (point[0] - left[0]) * (right[1] - left[1])
        crosses_to_right = (
            left_side > right_side
            if right[1] > left[1]
            else left_side < right_side
        )
        if crosses_to_right:
            inside = not inside
    return 1 if inside else -1


def _point_in_polygon(point: _Point, polygon: _Polygon) -> int:
    exterior = _point_in_ring(point, polygon[0])
    if exterior <= 0:
        return exterior
    for hole in polygon[1:]:
        status = _point_in_ring(point, hole)
        if status == 0:
            return 0
        if status == 1:
            return -1
    return 1


def _point_in_geometry(point: _Point, geometry: _ParsedGeometry) -> int:
    boundary = False
    for polygon in geometry.polygons:
        status = _point_in_polygon(point, polygon)
        if status == 1:
            return 1
        boundary = boundary or status == 0
    return 0 if boundary else -1


def _strict_ring_interior_point(ring: _Ring, location: str) -> _Point:
    y_values = sorted({point[1] for point in ring[:-1]})
    for lower, upper in zip(y_values, y_values[1:]):
        if lower == upper:
            continue
        y_value = (lower + upper) / 2
        intersections: list[Decimal] = []
        for left, right in _ring_segments(ring):
            if (left[1] > y_value) == (right[1] > y_value):
                continue
            x_value = left[0] + (
                (y_value - left[1]) * (right[0] - left[0])
                / (right[1] - left[1])
            )
            intersections.append(x_value)
        intersections.sort()
        for left_x, right_x in zip(intersections[::2], intersections[1::2]):
            candidate = ((left_x + right_x) / 2, y_value)
            if _point_in_ring(candidate, ring) == 1:
                return candidate
    raise ContractError(f"{location} has no resolvable strict interior point")


def _validate_simple_ring(ring: _Ring, location: str) -> None:
    _require(len(ring) >= 4, f"{location} must contain at least four points")
    _require(ring[0] == ring[-1], f"{location} must be closed")
    vertices = ring[:-1]
    _require(len(set(vertices)) >= 3, f"{location} must contain three distinct vertices")
    _require(
        len(vertices) == len(set(vertices)),
        f"{location} repeats a non-closing vertex",
    )
    _require(
        all(left != right for left, right in _ring_segments(ring)),
        f"{location} contains a zero-length segment",
    )
    _require(_ring_area_twice(ring) != 0, f"{location} is degenerate")
    for index, current in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % len(vertices)]
        _require(
            _cross(previous, current, following) != 0,
            f"{location} contains a noncanonical collinear vertex",
        )
    segments = _ring_segments(ring)
    for left_index, (left_a, left_b) in enumerate(segments):
        for right_index in range(left_index + 1, len(segments)):
            if right_index == left_index + 1 or (
                left_index == 0 and right_index == len(segments) - 1
            ):
                continue
            right_a, right_b = segments[right_index]
            _require(
                not _segments_intersect(left_a, left_b, right_a, right_b),
                f"{location} self-intersects",
            )


def _validate_polygon_topology(geometry: _ParsedGeometry, location: str) -> None:
    if geometry.geometry_type == "MULTIPOLYGON":
        _require(
            len(geometry.polygons) >= 2,
            f"{location} must use POLYGON for a single polygon member",
        )
    for polygon_index, polygon in enumerate(geometry.polygons):
        polygon_location = f"{location}.polygons[{polygon_index}]"
        _require(bool(polygon), f"{polygon_location} must contain an exterior ring")
        for ring_index, ring in enumerate(polygon):
            _validate_simple_ring(ring, f"{polygon_location}.rings[{ring_index}]")
        exterior = polygon[0]
        for hole_index, hole in enumerate(polygon[1:], start=1):
            _require(
                not any(
                    _segments_intersect(left_a, left_b, right_a, right_b)
                    for left_a, left_b in _ring_segments(exterior)
                    for right_a, right_b in _ring_segments(hole)
                ),
                f"{polygon_location}.rings[{hole_index}] intersects the exterior",
            )
            _require(
                _point_in_ring(hole[0], exterior) == 1,
                f"{polygon_location}.rings[{hole_index}] is not strictly inside the exterior",
            )
        holes = polygon[1:]
        for left_index, left in enumerate(holes):
            for right_index in range(left_index + 1, len(holes)):
                right = holes[right_index]
                _require(
                    not any(
                        _segments_intersect(left_a, left_b, right_a, right_b)
                        for left_a, left_b in _ring_segments(left)
                        for right_a, right_b in _ring_segments(right)
                    ),
                    f"{polygon_location} holes intersect",
                )
                _require(
                    _point_in_ring(left[0], right) == -1
                    and _point_in_ring(right[0], left) == -1,
                    f"{polygon_location} holes overlap or nest",
                )

    for left_index, left in enumerate(geometry.polygons):
        for right_index in range(left_index + 1, len(geometry.polygons)):
            right = geometry.polygons[right_index]
            _require(
                not _boundaries_intersect(left, right),
                f"{location} multipolygon members intersect",
            )
            _require(
                _point_in_polygon(left[0][0], right) == -1
                and _point_in_polygon(right[0][0], left) == -1,
                f"{location} multipolygon members overlap or nest",
            )


def _canonical_ring(ring: _Ring, *, positive_area: bool) -> _Ring:
    vertices = list(ring[:-1])
    if (_ring_area_twice(ring) > 0) != positive_area:
        vertices.reverse()
    start = min(range(len(vertices)), key=vertices.__getitem__)
    ordered = vertices[start:] + vertices[:start]
    return tuple(ordered + [ordered[0]])


def _canonicalize_geometry(geometry: _ParsedGeometry) -> _ParsedGeometry:
    polygons: list[_Polygon] = []
    for polygon in geometry.polygons:
        exterior = _canonical_ring(polygon[0], positive_area=True)
        holes = sorted(
            (_canonical_ring(ring, positive_area=False) for ring in polygon[1:]),
            key=lambda ring: ring,
        )
        polygons.append((exterior, *holes))
    return _ParsedGeometry(
        geometry_type=geometry.geometry_type,
        polygons=tuple(sorted(polygons, key=lambda polygon: polygon)),
    )


def _render_geometry_wkt(geometry: _ParsedGeometry) -> str:
    def render_ring(ring: _Ring) -> str:
        return "(" + ", ".join(
            f"{_canonical_decimal(str(x))} {_canonical_decimal(str(y))}"
            for x, y in ring
        ) + ")"

    def render_polygon(polygon: _Polygon) -> str:
        return "(" + ", ".join(render_ring(ring) for ring in polygon) + ")"

    if geometry.geometry_type == "POLYGON":
        body = render_polygon(geometry.polygons[0])
    else:
        body = "(" + ", ".join(render_polygon(polygon) for polygon in geometry.polygons) + ")"
    return f"{geometry.geometry_type} {body}"


def _canonical_wkt(geometry_type: str, wkt: str, location: str) -> str:
    """Return topology-checked canonical WKT with stable rings and members."""

    parsed = _parse_polygon_geometry(geometry_type, wkt, location)
    _validate_polygon_topology(parsed, location)
    return _render_geometry_wkt(_canonicalize_geometry(parsed))


def _validate_canonical_geometry(
    raw: Any,
    location: str,
) -> tuple[Mapping[str, Any], _ParsedGeometry]:
    geometry = _object(raw, location)
    wkt = _validate_wkt(geometry, location)
    canonical = _canonical_wkt(str(geometry["geometry_type"]), wkt, location)
    _require(wkt == canonical, f"{location}.wkt is not in canonical WKT1 form")
    return geometry, _parse_polygon_geometry(str(geometry["geometry_type"]), wkt, location)


def _geometry_segments(
    geometry: _ParsedGeometry,
) -> tuple[tuple[_Point, _Point], ...]:
    return tuple(
        segment
        for polygon in geometry.polygons
        for ring in polygon
        for segment in _ring_segments(ring)
    )


def _segment_boundary_parameters(
    left: _Point,
    right: _Point,
    boundary_left: _Point,
    boundary_right: _Point,
) -> tuple[Decimal, ...]:
    direction = (right[0] - left[0], right[1] - left[1])
    boundary_direction = (
        boundary_right[0] - boundary_left[0],
        boundary_right[1] - boundary_left[1],
    )
    offset = (boundary_left[0] - left[0], boundary_left[1] - left[1])
    denominator = (
        direction[0] * boundary_direction[1]
        - direction[1] * boundary_direction[0]
    )
    if denominator != 0:
        parameter = (
            offset[0] * boundary_direction[1]
            - offset[1] * boundary_direction[0]
        ) / denominator
        boundary_parameter = (
            offset[0] * direction[1] - offset[1] * direction[0]
        ) / denominator
        if 0 <= parameter <= 1 and 0 <= boundary_parameter <= 1:
            return (parameter,)
        return ()
    if offset[0] * direction[1] - offset[1] * direction[0] != 0:
        return ()
    if direction[0] != 0:
        values = (
            (boundary_left[0] - left[0]) / direction[0],
            (boundary_right[0] - left[0]) / direction[0],
        )
    else:
        values = (
            (boundary_left[1] - left[1]) / direction[1],
            (boundary_right[1] - left[1]) / direction[1],
        )
    return tuple(value for value in values if 0 <= value <= 1)


def _geometry_covered_by(
    container: _ParsedGeometry,
    subject: _ParsedGeometry,
) -> bool:
    if any(
        _point_in_geometry(point, container) == -1
        for polygon in subject.polygons
        for ring in polygon
        for point in ring[:-1]
    ):
        return False

    container_segments = _geometry_segments(container)
    for left, right in _geometry_segments(subject):
        parameters = {Decimal(0), Decimal(1)}
        for boundary_left, boundary_right in container_segments:
            parameters.update(
                _segment_boundary_parameters(
                    left,
                    right,
                    boundary_left,
                    boundary_right,
                )
            )
        ordered = sorted(parameters)
        for start, end in zip(ordered, ordered[1:]):
            if start == end:
                continue
            midpoint = (start + end) / 2
            point = (
                left[0] + midpoint * (right[0] - left[0]),
                left[1] + midpoint * (right[1] - left[1]),
            )
            if _point_in_geometry(point, container) == -1:
                return False

    # A subject enclosing a container hole includes area excluded by the
    # container even when their boundaries never cross.
    for polygon in container.polygons:
        for hole_index, hole in enumerate(polygon[1:], start=1):
            interior = _strict_ring_interior_point(
                hole,
                f"container.polygons.holes[{hole_index}]",
            )
            if _point_in_geometry(interior, subject) == 1:
                return False
    return True


def _geometry_within_image(
    geometry: _ParsedGeometry,
    *,
    width_pixels: int,
    height_pixels: int,
) -> bool:
    width = Decimal(width_pixels)
    height = Decimal(height_pixels)
    return all(
        0 <= point[0] <= width and 0 <= point[1] <= height
        for polygon in geometry.polygons
        for ring in polygon
        for point in ring[:-1]
    )


def _geometry_intersects_image_boundary(
    geometry: _ParsedGeometry,
    *,
    width_pixels: int,
    height_pixels: int,
) -> bool:
    width = Decimal(width_pixels)
    height = Decimal(height_pixels)
    return any(
        point[0] in {Decimal(0), width} or point[1] in {Decimal(0), height}
        for polygon in geometry.polygons
        for ring in polygon
        for point in ring[:-1]
    )


def _geometry_intersects_geometry_boundary(
    subject: _ParsedGeometry,
    boundary: _ParsedGeometry,
) -> bool:
    return any(
        _segments_intersect(left, right, boundary_left, boundary_right)
        for left, right in _geometry_segments(subject)
        for boundary_left, boundary_right in _geometry_segments(boundary)
    )


def _geometries_intersect_inclusive(
    left: _ParsedGeometry,
    right: _ParsedGeometry,
) -> bool:
    if _geometry_intersects_geometry_boundary(left, right):
        return True
    return any(
        _point_in_geometry(polygon[0][0], right) >= 0
        for polygon in left.polygons
    ) or any(
        _point_in_geometry(polygon[0][0], left) >= 0
        for polygon in right.polygons
    )


def _validate_reference_geometry_scope(
    geometry: _ParsedGeometry,
    *,
    image: _ImageContext,
    annotation_id: str,
    location: str,
) -> _ParsedGeometry:
    _require(
        _geometry_within_image(
            geometry,
            width_pixels=image.width_pixels,
            height_pixels=image.height_pixels,
        ),
        f"{location} extends outside image dimensions",
    )
    roi = image.include_annotation_geometries[annotation_id]
    _require(
        _geometry_covered_by(roi, geometry),
        f"{location} extends outside its governed inclusion ROI",
    )
    return roi


def _validate_adjudicated_review(
    raw: Any,
    location: str,
) -> tuple[tuple[str, ...], str]:
    review = _object(raw, location)
    _exact(review, {"state", "reviewer_ids", "reviewed_at", "adjudication"}, location)
    _require(review["state"] == "accepted", f"{location}.state must be accepted")
    reviewers = tuple(
        _identifier(value, f"{location}.reviewer_ids[{index}]")
        for index, value in enumerate(_array(review["reviewer_ids"], f"{location}.reviewer_ids"))
    )
    _require(bool(reviewers), f"{location}.reviewer_ids must not be empty")
    _require(
        list(reviewers) == sorted(reviewers) and len(reviewers) == len(set(reviewers)),
        f"{location}.reviewer_ids must be unique and ascending",
    )
    _timestamp(review["reviewed_at"], f"{location}.reviewed_at")

    adjudication = _object(review["adjudication"], f"{location}.adjudication")
    _exact(adjudication, {"method", "adjudicator_id", "notes"}, f"{location}.adjudication")
    method = _enum(
        adjudication["method"],
        {
            "single_reviewer",
            "independent_second_review",
            "consensus",
            "adjudicator_decision",
        },
        f"{location}.adjudication.method",
    )
    if method == "adjudicator_decision":
        adjudicator_id = _identifier(
            adjudication["adjudicator_id"],
            f"{location}.adjudication.adjudicator_id",
        )
        _require(
            adjudicator_id not in reviewers,
            f"{location}.adjudication.adjudicator_id must be distinct from all reviewers",
        )
    else:
        _require(
            adjudication["adjudicator_id"] is None,
            f"{location}.adjudication.adjudicator_id must be null unless an adjudicator decided",
        )
    if method == "single_reviewer":
        _require(len(reviewers) == 1, f"{location}: single_reviewer requires exactly one reviewer")
    if method in {"independent_second_review", "consensus"}:
        _require(len(reviewers) >= 2, f"{location}: {method} requires at least two reviewers")
    if adjudication["notes"] is not None:
        _nonempty(adjudication["notes"], f"{location}.adjudication.notes")
    return reviewers, method


def _load_canonical_ndjson(
    root: Path,
    raw_reference: Any,
    location: str,
    *,
    record_schema: str,
) -> tuple[list[Mapping[str, Any]], Path]:
    reference = _object(raw_reference, location)
    _exact(
        reference,
        {
            "relative_path",
            "media_type",
            "sha256",
            "size_bytes",
            "record_count",
            "record_schema",
            "canonicalization_profile",
            "ordering",
        },
        location,
    )
    path = _safe_relative(root, reference["relative_path"], f"{location}.relative_path")
    _require(
        reference["media_type"] == "application/x-ndjson",
        f"{location}.media_type must be application/x-ndjson",
    )
    _require(reference["record_schema"] == record_schema, f"{location}.record_schema is unsupported")
    _require(
        reference["canonicalization_profile"] == "ifquant_canonical_json_v1",
        f"{location}.canonicalization_profile is unsupported",
    )
    _require(
        reference["ordering"] == "image_id_annotation_id_record_id_ascending",
        f"{location}.ordering is unsupported",
    )
    expected_hash = _sha256(reference["sha256"], f"{location}.sha256")
    expected_size = _integer(reference["size_bytes"], f"{location}.size_bytes")
    expected_count = _integer(reference["record_count"], f"{location}.record_count")
    payload = path.read_bytes()
    _require(len(payload) == expected_size, f"{location}.size_bytes does not match the artifact")
    _require(file_sha256(path) == expected_hash, f"{location}.sha256 does not match the artifact")

    if not payload:
        raw_lines: list[bytes] = []
    else:
        _require(payload.endswith(b"\n"), f"{location} canonical NDJSON must end with LF")
        raw_lines = payload[:-1].split(b"\n")
        _require(all(raw_lines), f"{location} canonical NDJSON must not contain blank lines")

    records: list[Mapping[str, Any]] = []
    for index, raw_line in enumerate(raw_lines):
        record_location = f"{location}.records[{index}]"
        parsed = parse_strict_json(raw_line, source=f"{path}:{index + 1}")
        record = _object(parsed, record_location)
        _require(
            raw_line == canonical_json_bytes(record),
            f"{record_location} is not canonical JSON",
        )
        records.append(record)
    _require(len(records) == expected_count, f"{location}.record_count does not match the artifact")
    return records, path


def _validate_nuclear_record(
    raw: Mapping[str, Any],
    *,
    reference_set_id: str,
    images: Mapping[str, _ImageContext],
    location: str,
) -> tuple[tuple[str, str, str], bool, bool]:
    _exact(
        raw,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "reference_object_id",
            "reference_set_id",
            "image_id",
            "biological_unit_id",
            "annotation_id",
            "coordinate_space_id",
            "target",
            "geometry",
            "creation_mode",
            "prediction_exposure",
            "review",
        },
        location,
    )
    _require(raw["$schema"] == NUCLEAR_REFERENCE_OBJECT_SCHEMA, f"{location}.$schema is unsupported")
    _require(
        raw["contract_type"] == "ifquant_platform_nuclear_reference_object",
        f"{location}.contract_type is unsupported",
    )
    _require(raw["contract_version"] == "1.0.0", f"{location}.contract_version is unsupported")
    reference_object_id = _sha256(raw["reference_object_id"], f"{location}.reference_object_id")
    _require(raw["reference_set_id"] == reference_set_id, f"{location}.reference_set_id does not match")
    image_id = _identifier(raw["image_id"], f"{location}.image_id")
    _require(image_id in images, f"{location}.image_id is not governed by the reference set")
    image = images[image_id]
    _require(
        raw["biological_unit_id"] == image.biological_unit_id,
        f"{location}.biological_unit_id does not match the governed image",
    )
    annotation_id = _identifier(raw["annotation_id"], f"{location}.annotation_id")
    _require(
        annotation_id in image.include_annotation_ids,
        f"{location}.annotation_id does not resolve to a governed include ROI",
    )
    _require(
        raw["coordinate_space_id"] == image.coordinate_space_id,
        f"{location}.coordinate_space_id does not match the governed image",
    )
    target = _object(raw["target"], f"{location}.target")
    _exact(target, {"object_type", "marker_id", "channel_role"}, f"{location}.target")
    _require(
        target == {"object_type": "nucleus", "marker_id": "DAPI", "channel_role": "nuclear"},
        f"{location}.target must identify a DAPI nuclear instance",
    )
    geometry, parsed_geometry = _validate_canonical_geometry(
        raw["geometry"],
        f"{location}.geometry",
    )
    _validate_reference_geometry_scope(
        parsed_geometry,
        image=image,
        annotation_id=annotation_id,
        location=f"{location}.geometry",
    )
    creation_mode = _enum(
        raw["creation_mode"],
        {"human_drawn", "human_corrected_prediction"},
        f"{location}.creation_mode",
    )
    exposure = raw["prediction_exposure"]
    if creation_mode == "human_drawn":
        _require(exposure is None, f"{location}.prediction_exposure must be null for human_drawn")
    else:
        exposure_object = _object(exposure, f"{location}.prediction_exposure")
        _exact(
            exposure_object,
            {
                "package_id",
                "package_sha256",
                "segmentation_run_id",
                "predicted_object_id",
                "predicted_geometry_sha256",
            },
            f"{location}.prediction_exposure",
        )
        _identifier(exposure_object["package_id"], f"{location}.prediction_exposure.package_id")
        _sha256(exposure_object["package_sha256"], f"{location}.prediction_exposure.package_sha256")
        _identifier(exposure_object["segmentation_run_id"], f"{location}.prediction_exposure.segmentation_run_id")
        _sha256(exposure_object["predicted_object_id"], f"{location}.prediction_exposure.predicted_object_id")
        _sha256(
            exposure_object["predicted_geometry_sha256"],
            f"{location}.prediction_exposure.predicted_geometry_sha256",
        )
    _reviewers, review_method = _validate_adjudicated_review(
        raw["review"],
        f"{location}.review",
    )
    descriptor = {
        "annotation_id": annotation_id,
        "geometry": geometry,
        "image_id": image_id,
        "reference_set_id": reference_set_id,
        "target": target,
    }
    _require(
        canonical_sha256(descriptor) == reference_object_id,
        f"{location}.reference_object_id does not match its deterministic descriptor",
    )
    model_assisted = creation_mode == "human_corrected_prediction"
    return (image_id, annotation_id, reference_object_id), model_assisted, (
        model_assisted and review_method == "single_reviewer"
    )


def _validate_ignore_record(
    raw: Mapping[str, Any],
    *,
    reference_set_id: str,
    images: Mapping[str, _ImageContext],
    location: str,
) -> tuple[str, str, str]:
    _exact(
        raw,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "ignore_region_id",
            "reference_set_id",
            "image_id",
            "biological_unit_id",
            "annotation_id",
            "coordinate_space_id",
            "geometry",
            "reason",
            "review",
        },
        location,
    )
    _require(raw["$schema"] == REFERENCE_IGNORE_REGION_SCHEMA, f"{location}.$schema is unsupported")
    _require(
        raw["contract_type"] == "ifquant_platform_reference_ignore_region",
        f"{location}.contract_type is unsupported",
    )
    _require(raw["contract_version"] == "1.0.0", f"{location}.contract_version is unsupported")
    ignore_id = _sha256(raw["ignore_region_id"], f"{location}.ignore_region_id")
    _require(raw["reference_set_id"] == reference_set_id, f"{location}.reference_set_id does not match")
    image_id = _identifier(raw["image_id"], f"{location}.image_id")
    _require(image_id in images, f"{location}.image_id is not governed by the reference set")
    image = images[image_id]
    _require(
        raw["biological_unit_id"] == image.biological_unit_id,
        f"{location}.biological_unit_id does not match the governed image",
    )
    annotation_id = _identifier(raw["annotation_id"], f"{location}.annotation_id")
    _require(
        annotation_id in image.include_annotation_ids,
        f"{location}.annotation_id does not resolve to a governed include ROI",
    )
    _require(
        raw["coordinate_space_id"] == image.coordinate_space_id,
        f"{location}.coordinate_space_id does not match the governed image",
    )
    geometry, parsed_geometry = _validate_canonical_geometry(
        raw["geometry"],
        f"{location}.geometry",
    )
    roi_geometry = _validate_reference_geometry_scope(
        parsed_geometry,
        image=image,
        annotation_id=annotation_id,
        location=f"{location}.geometry",
    )
    reason = _object(raw["reason"], f"{location}.reason")
    _exact(reason, {"category", "code", "notes"}, f"{location}.reason")
    category = _enum(reason["category"], set(_IGNORE_CODES), f"{location}.reason.category")
    reason_code = _enum(reason["code"], _IGNORE_CODES[category], f"{location}.reason.code")
    if reason_code == "physical_image_edge":
        _require(
            _geometry_intersects_image_boundary(
                parsed_geometry,
                width_pixels=image.width_pixels,
                height_pixels=image.height_pixels,
            ),
            f"{location}: physical_image_edge ignore geometry must intersect the physical image boundary",
        )
    if reason_code == "physical_specimen_edge":
        _require(
            _geometry_intersects_geometry_boundary(parsed_geometry, roi_geometry),
            f"{location}: physical_specimen_edge ignore geometry must intersect the governed ROI boundary",
        )
    if reason["notes"] is not None:
        _nonempty(reason["notes"], f"{location}.reason.notes")
    _validate_adjudicated_review(raw["review"], f"{location}.review")
    descriptor = {
        "annotation_id": annotation_id,
        "geometry": geometry,
        "image_id": image_id,
        "reason": reason,
        "reference_set_id": reference_set_id,
    }
    _require(
        canonical_sha256(descriptor) == ignore_id,
        f"{location}.ignore_region_id does not match its deterministic descriptor",
    )
    return image_id, annotation_id, ignore_id


def _validate_artifact_reference(root: Path, raw: Any, location: str) -> str:
    artifact = _object(raw, location)
    _exact(artifact, {"relative_path", "media_type", "sha256", "size_bytes"}, location)
    path = _safe_relative(root, artifact["relative_path"], f"{location}.relative_path")
    _nonempty(artifact["media_type"], f"{location}.media_type")
    expected_hash = _sha256(artifact["sha256"], f"{location}.sha256")
    expected_size = _integer(
        artifact["size_bytes"],
        f"{location}.size_bytes",
        minimum=1,
    )
    _require(path.stat().st_size == expected_size, f"{location}.size_bytes does not match the artifact")
    _require(file_sha256(path) == expected_hash, f"{location}.sha256 does not match the artifact")
    return expected_hash


def _validate_provenance(root: Path, raw: Any, location: str = "provenance") -> datetime:
    provenance = _object(raw, location)
    _exact(
        provenance,
        {"created_at", "producer_id", "producer_version", "code_sha256", "code_artifact"},
        location,
    )
    created_at = _timestamp(provenance["created_at"], f"{location}.created_at")
    _identifier(provenance["producer_id"], f"{location}.producer_id")
    _semver(provenance["producer_version"], f"{location}.producer_version")
    code_sha256 = _sha256(provenance["code_sha256"], f"{location}.code_sha256")
    artifact_sha256 = _validate_artifact_reference(
        root,
        provenance["code_artifact"],
        f"{location}.code_artifact",
    )
    _require(code_sha256 == artifact_sha256, f"{location}.code_sha256 does not match code_artifact")
    return created_at


def _validate_claims(raw: Any, location: str = "claims") -> None:
    claims = _object(raw, location)
    _exact(
        claims,
        {
            "scientific_validation",
            "biological_ground_truth",
            "backend_equivalence",
            "model_universality",
            "authorization",
        },
        location,
    )
    for field in (
        "scientific_validation",
        "biological_ground_truth",
        "backend_equivalence",
        "model_universality",
    ):
        _require(claims[field] is False, f"{location}.{field} must be false")
    _require(claims["authorization"] == "none", f"{location}.authorization must be 'none'")


def _validate_governed_provenance_code_artifact(
    root: Path,
    raw: Any,
    location: str,
) -> None:
    provenance = _object(raw, location)
    code_sha256 = _sha256(provenance["code_sha256"], f"{location}.code_sha256")
    artifact_sha256 = _validate_artifact_reference(
        root,
        provenance["code_artifact"],
        f"{location}.code_artifact",
    )
    _require(
        code_sha256 == artifact_sha256,
        f"{location}.code_sha256 does not match code_artifact",
    )


def _collect_governed_document_timestamps(
    root: Path,
    document: Mapping[str, Any],
    location: str,
) -> tuple[list[tuple[str, datetime]], datetime]:
    provenance_location = f"{location}.provenance"
    created_at = _timestamp(
        document["provenance"]["created_at"],
        f"{provenance_location}.created_at",
    )
    _validate_governed_provenance_code_artifact(
        root,
        document["provenance"],
        provenance_location,
    )
    timestamps: list[tuple[str, datetime]] = [
        (f"{provenance_location}.created_at", created_at)
    ]
    for observation_index, raw_observation in enumerate(document["observations"]):
        observation_location = f"{location}.observations[{observation_index}]"
        observation = _object(raw_observation, observation_location)

        image_reference = _object(
            observation["image"],
            f"{observation_location}.image",
        )
        image_path = _safe_relative(
            root,
            image_reference["manifest_relative_path"],
            f"{observation_location}.image.manifest_relative_path",
        )
        image_manifest_location = f"{observation_location}.image.manifest"
        image_manifest = _load_mapping(image_path, image_manifest_location)
        timestamps.append(
            (
                f"{image_manifest_location}.provenance.created_at",
                _timestamp(
                    image_manifest["provenance"]["created_at"],
                    f"{image_manifest_location}.provenance.created_at",
                ),
            )
        )
        acquired_at = image_manifest["acquisition"]["acquired_at"]
        if acquired_at is not None:
            timestamps.append(
                (
                    f"{image_manifest_location}.acquisition.acquired_at",
                    _timestamp(
                        acquired_at,
                        f"{image_manifest_location}.acquisition.acquired_at",
                    ),
                )
            )

        channel_reference = _object(
            observation["channel_map"],
            f"{observation_location}.channel_map",
        )
        channel_path = _safe_relative(
            root,
            channel_reference["manifest_relative_path"],
            f"{observation_location}.channel_map.manifest_relative_path",
        )
        channel_manifest_location = f"{observation_location}.channel_map.manifest"
        channel_manifest = _load_mapping(channel_path, channel_manifest_location)
        timestamps.append(
            (
                f"{channel_manifest_location}.provenance.created_at",
                _timestamp(
                    channel_manifest["provenance"]["created_at"],
                    f"{channel_manifest_location}.provenance.created_at",
                ),
            )
        )

        lineage_location = f"{observation_location}.annotation_lineage"
        for lineage_index, raw_annotation_reference in enumerate(
            _array(observation["annotation_lineage"], lineage_location)
        ):
            annotation_reference_location = f"{lineage_location}[{lineage_index}]"
            annotation_reference = _object(
                raw_annotation_reference,
                annotation_reference_location,
            )
            annotation_path = _safe_relative(
                root,
                annotation_reference["manifest_relative_path"],
                f"{annotation_reference_location}.manifest_relative_path",
            )
            annotation_manifest_location = f"{annotation_reference_location}.manifest"
            annotation_manifest = _load_mapping(
                annotation_path,
                annotation_manifest_location,
            )
            timestamps.append(
                (
                    f"{annotation_manifest_location}.provenance.created_at",
                    _timestamp(
                        annotation_manifest["provenance"]["created_at"],
                        f"{annotation_manifest_location}.provenance.created_at",
                    ),
                )
            )
            for annotation_index, annotation in enumerate(annotation_manifest["annotations"]):
                reviewed_at = annotation["review"]["reviewed_at"]
                if reviewed_at is None:
                    continue
                review_location = (
                    f"{annotation_manifest_location}.annotations[{annotation_index}]"
                    ".review.reviewed_at"
                )
                timestamps.append(
                    (review_location, _timestamp(reviewed_at, review_location))
                )

        identity_review_location = f"{observation_location}.identity_review.reviewed_at"
        timestamps.append(
            (
                identity_review_location,
                _timestamp(
                    observation["identity_review"]["reviewed_at"],
                    identity_review_location,
                ),
            )
        )
    return timestamps, created_at


def _collect_governed_parent_timestamps(
    root: Path,
    raw_parent: Any,
    *,
    child_created_at: datetime,
    child_location: str,
    location: str,
    ancestor_paths: frozenset[Path],
) -> tuple[
    list[tuple[str, datetime]],
    list[tuple[str, datetime, str, datetime]],
]:
    if raw_parent is None:
        return [], []
    parent = _object(raw_parent, location)
    _exact(
        parent,
        {"observation_set_id", "manifest_relative_path", "manifest_sha256"},
        location,
    )
    parent_path = _safe_relative(
        root,
        parent["manifest_relative_path"],
        f"{location}.manifest_relative_path",
    ).resolve()
    _require(
        parent_path not in ancestor_paths,
        "observation-set parent lineage contains a cycle",
    )
    _require(
        len(ancestor_paths) < 256,
        "observation-set parent lineage exceeds 256 revisions",
    )
    parent_document_location = f"{location}.manifest"
    parent_document = _load_mapping(parent_path, parent_document_location)
    _require(
        parent_document["$schema"] == GOVERNED_OBSERVATION_SET_SCHEMA,
        f"{parent_document_location}.$schema is unsupported",
    )
    parent_timestamps, parent_created_at = _collect_governed_document_timestamps(
        parent_path.parent.resolve(),
        parent_document,
        parent_document_location,
    )
    revision_chronology = [
        (
            parent_document_location,
            parent_created_at,
            child_location,
            child_created_at,
        )
    ]
    ancestor_timestamps, ancestor_chronology = _collect_governed_parent_timestamps(
        parent_path.parent.resolve(),
        parent_document["parent"],
        child_created_at=parent_created_at,
        child_location=parent_document_location,
        location=f"{parent_document_location}.parent",
        ancestor_paths=ancestor_paths | {parent_path},
    )
    parent_timestamps.extend(ancestor_timestamps)
    revision_chronology.extend(ancestor_chronology)
    return parent_timestamps, revision_chronology


def _load_governed_context(
    root: Path,
    raw_reference: Any,
    *,
    study_id: str,
) -> _GovernedContext:
    location = "governed_observation_set"
    reference = _object(raw_reference, location)
    _exact(
        reference,
        {"observation_set_id", "revision", "manifest_relative_path", "manifest_sha256"},
        location,
    )
    observation_set_id = _identifier(reference["observation_set_id"], f"{location}.observation_set_id")
    revision = _integer(reference["revision"], f"{location}.revision")
    expected_hash = _sha256(reference["manifest_sha256"], f"{location}.manifest_sha256")
    path = _safe_relative(root, reference["manifest_relative_path"], f"{location}.manifest_relative_path")
    report = validate_governed_observation_set(path)
    _require(report.observation_set_id == observation_set_id, f"{location}.observation_set_id does not match")
    _require(report.revision == revision, f"{location}.revision does not match")
    _require(report.study_id == study_id, f"{location}.study_id does not match the reference set")
    _require(report.observation_set_sha256 == expected_hash, f"{location}.manifest_sha256 does not match")

    document = _load_mapping(path, location)
    _require(document["$schema"] == GOVERNED_OBSERVATION_SET_SCHEMA, f"{location}.$schema is unsupported")
    governed_root = path.parent.resolve()
    images: dict[str, _ImageContext] = {}
    observations_by_image: dict[str, Mapping[str, Any]] = {}
    governed_created_at = _timestamp(
        document["provenance"]["created_at"],
        f"{location}.provenance.created_at",
    )
    _validate_governed_provenance_code_artifact(
        governed_root,
        document["provenance"],
        f"{location}.provenance",
    )
    upstream_timestamps: list[tuple[str, datetime]] = [
        (f"{location}.provenance.created_at", governed_created_at)
    ]
    ancestor_timestamps, revision_chronology = _collect_governed_parent_timestamps(
        governed_root,
        document["parent"],
        child_created_at=governed_created_at,
        child_location=location,
        location=f"{location}.parent",
        ancestor_paths=frozenset({path.resolve()}),
    )
    upstream_timestamps.extend(ancestor_timestamps)
    for index, raw_observation in enumerate(document["observations"]):
        observation = _object(raw_observation, f"{location}.observations[{index}]")
        image_reference = _object(observation["image"], f"{location}.observations[{index}].image")
        image_path = _safe_relative(
            governed_root,
            image_reference["manifest_relative_path"],
            f"{location}.observations[{index}].image.manifest_relative_path",
        )
        image_manifest_location = f"{location}.observations[{index}].image.manifest"
        image_manifest = _load_mapping(image_path, image_manifest_location)
        image_id = str(image_manifest["image_id"])
        upstream_timestamps.append(
            (
                f"{image_manifest_location}.provenance.created_at",
                _timestamp(
                    image_manifest["provenance"]["created_at"],
                    f"{image_manifest_location}.provenance.created_at",
                ),
            )
        )
        acquisition = _object(
            image_manifest["acquisition"],
            f"{image_manifest_location}.acquisition",
        )
        if acquisition["acquired_at"] is not None:
            upstream_timestamps.append(
                (
                    f"{image_manifest_location}.acquisition.acquired_at",
                    _timestamp(
                        acquisition["acquired_at"],
                        f"{image_manifest_location}.acquisition.acquired_at",
                    ),
                )
            )

        channel_reference_location = f"{location}.observations[{index}].channel_map"
        channel_reference = _object(observation["channel_map"], channel_reference_location)
        channel_path = _safe_relative(
            governed_root,
            channel_reference["manifest_relative_path"],
            f"{channel_reference_location}.manifest_relative_path",
        )
        channel_manifest_location = f"{channel_reference_location}.manifest"
        channel_manifest = _load_mapping(channel_path, channel_manifest_location)
        upstream_timestamps.append(
            (
                f"{channel_manifest_location}.provenance.created_at",
                _timestamp(
                    channel_manifest["provenance"]["created_at"],
                    f"{channel_manifest_location}.provenance.created_at",
                ),
            )
        )

        lineage_location = f"{location}.observations[{index}].annotation_lineage"
        annotation_lineage = _array(observation["annotation_lineage"], lineage_location)
        annotation_manifest: Mapping[str, Any] | None = None
        annotation_manifest_location = ""
        for lineage_index, raw_annotation_reference in enumerate(annotation_lineage):
            annotation_reference_location = f"{lineage_location}[{lineage_index}]"
            annotation_reference = _object(
                raw_annotation_reference,
                annotation_reference_location,
            )
            annotation_path = _safe_relative(
                governed_root,
                annotation_reference["manifest_relative_path"],
                f"{annotation_reference_location}.manifest_relative_path",
            )
            annotation_manifest_location = f"{annotation_reference_location}.manifest"
            annotation_manifest = _load_mapping(
                annotation_path,
                annotation_manifest_location,
            )
            upstream_timestamps.append(
                (
                    f"{annotation_manifest_location}.provenance.created_at",
                    _timestamp(
                        annotation_manifest["provenance"]["created_at"],
                        f"{annotation_manifest_location}.provenance.created_at",
                    ),
                )
            )
            for annotation_index, annotation in enumerate(annotation_manifest["annotations"]):
                if annotation["review"]["reviewed_at"] is None:
                    continue
                review_location = (
                    f"{annotation_manifest_location}.annotations[{annotation_index}]"
                    ".review.reviewed_at"
                )
                upstream_timestamps.append(
                    (
                        review_location,
                        _timestamp(annotation["review"]["reviewed_at"], review_location),
                    )
                )
        _require(
            annotation_manifest is not None,
            f"{lineage_location} must contain at least one annotation reference",
        )
        upstream_timestamps.append(
            (
                f"{location}.observations[{index}].identity_review.reviewed_at",
                _timestamp(
                    observation["identity_review"]["reviewed_at"],
                    f"{location}.observations[{index}].identity_review.reviewed_at",
                ),
            )
        )
        dimensions = _object(
            image_manifest["dimensions"],
            f"{location}.observations[{index}].image.dimensions",
        )
        width_pixels = _integer(
            dimensions["width_pixels"],
            f"{location}.observations[{index}].image.dimensions.width_pixels",
            minimum=1,
        )
        height_pixels = _integer(
            dimensions["height_pixels"],
            f"{location}.observations[{index}].image.dimensions.height_pixels",
            minimum=1,
        )
        include_geometries: dict[str, _ParsedGeometry] = {}
        for annotation_index, raw_annotation in enumerate(annotation_manifest["annotations"]):
            if raw_annotation["inclusion_policy"] != "include":
                continue
            annotation_id = str(raw_annotation["annotation_id"])
            geometry_location = (
                f"{annotation_manifest_location}"
                f".annotations[{annotation_index}].geometry"
            )
            geometry_object = _object(raw_annotation["geometry"], geometry_location)
            geometry_wkt = _validate_wkt(geometry_object, geometry_location)
            parsed_geometry = _parse_polygon_geometry(
                str(geometry_object["geometry_type"]),
                geometry_wkt,
                geometry_location,
            )
            _validate_polygon_topology(parsed_geometry, geometry_location)
            _require(
                _geometry_within_image(
                    parsed_geometry,
                    width_pixels=width_pixels,
                    height_pixels=height_pixels,
                ),
                f"{geometry_location} extends outside image dimensions",
            )
            include_geometries[annotation_id] = parsed_geometry
        include_ids = frozenset(include_geometries)
        biological = _object(observation["biological_unit"], f"{location}.observations[{index}].biological_unit")
        images[image_id] = _ImageContext(
            image_id=image_id,
            biological_unit_id=str(biological["biological_unit_id"]),
            coordinate_space_id=str(image_manifest["coordinate_space"]["coordinate_space_id"]),
            mouse_id=str(acquisition["mouse_id"]),
            slide_id=str(acquisition["slide_id"]),
            batch_id=str(acquisition["batch_id"]),
            scanner_id=str(acquisition["scanner_id"]),
            source_sha256=str(image_manifest["source_artifact"]["sha256"]),
            width_pixels=width_pixels,
            height_pixels=height_pixels,
            include_annotation_ids=include_ids,
            include_annotation_geometries=include_geometries,
        )
        observations_by_image[image_id] = observation
    _require(len(images) == report.observation_count, "governed observation image identities are not unique")
    return _GovernedContext(
        report=report,
        document=document,
        images=images,
        observations_by_image=observations_by_image,
        upstream_timestamps=tuple(upstream_timestamps),
        revision_chronology=tuple(revision_chronology),
    )


def _validate_reference_parent(
    root: Path,
    document: Mapping[str, Any],
    revision: int,
    ancestor_paths: frozenset[Path],
) -> _ReferenceContext | None:
    raw = document["parent"]
    if revision == 0:
        _require(raw is None, "parent must be null for reference-set revision 0")
        return None
    _require(raw is not None, "parent is required after reference-set revision 0")
    parent = _object(raw, "parent")
    _exact(parent, {"reference_set_id", "revision", "manifest_relative_path", "manifest_sha256"}, "parent")
    parent_id = _identifier(parent["reference_set_id"], "parent.reference_set_id")
    parent_revision = _integer(parent["revision"], "parent.revision")
    parent_hash = _sha256(parent["manifest_sha256"], "parent.manifest_sha256")
    parent_path = _safe_relative(root, parent["manifest_relative_path"], "parent.manifest_relative_path")
    context = _validate_nuclear_reference_set_path(parent_path, ancestor_paths)
    _require(context.report.reference_set_id == parent_id, "parent.reference_set_id does not match")
    _require(context.report.revision == parent_revision, "parent.revision does not match")
    _require(context.report.reference_set_sha256 == parent_hash, "parent.manifest_sha256 does not match")
    _require(parent_id == document["reference_set_id"], "parent must retain reference_set_id")
    _require(context.report.study_id == document["study_id"], "parent must retain study_id")
    _require(parent_revision == revision - 1, "parent revision must immediately precede revision")
    return context


def _validate_task_and_policies(root: Path, document: Mapping[str, Any]) -> None:
    task = _object(document["task"], "task")
    _exact(task, {"task_id", "task_type", "target"}, "task")
    _identifier(task["task_id"], "task.task_id")
    _require(task["task_type"] == "dapi_nucleus_instance_segmentation", "task.task_type is unsupported")
    target = _object(task["target"], "task.target")
    _exact(target, {"object_type", "marker_id", "channel_role"}, "task.target")
    _require(
        target == {"object_type": "nucleus", "marker_id": "DAPI", "channel_role": "nuclear"},
        "task.target must identify DAPI nuclei",
    )

    evaluation = _object(document["evaluation_policy"], "evaluation_policy")
    _exact(
        evaluation,
        {
            "evaluation_policy_id",
            "evaluation_policy_version",
            "detector_guard_inherited",
            "evaluation_extent",
            "ignore_region_handling",
            "unreviewed_region_policy",
            "artifact",
        },
        "evaluation_policy",
    )
    _identifier(evaluation["evaluation_policy_id"], "evaluation_policy.evaluation_policy_id")
    _semver(evaluation["evaluation_policy_version"], "evaluation_policy.evaluation_policy_version")
    _require(evaluation["detector_guard_inherited"] is False, "evaluation_policy must not inherit a detector guard")
    _require(
        evaluation["evaluation_extent"] == "reviewed_reference_regions_only",
        "evaluation_policy.evaluation_extent is unsupported",
    )
    _require(
        evaluation["ignore_region_handling"]
        == "exclude_explicit_reference_ignore_regions_before_scoring",
        "evaluation_policy.ignore_region_handling is unsupported",
    )
    _require(
        evaluation["unreviewed_region_policy"] == "not_evaluated",
        "evaluation_policy.unreviewed_region_policy is unsupported",
    )
    _validate_artifact_reference(root, evaluation["artifact"], "evaluation_policy.artifact")

    protocol = _object(document["selection_protocol"], "selection_protocol")
    _exact(protocol, {"protocol_id", "protocol_version", "artifact"}, "selection_protocol")
    _identifier(protocol["protocol_id"], "selection_protocol.protocol_id")
    _semver(protocol["protocol_version"], "selection_protocol.protocol_version")
    _validate_artifact_reference(root, protocol["artifact"], "selection_protocol.artifact")


def _validate_source_families(
    raw: Any,
    images: Mapping[str, _ImageContext],
) -> dict[str, str]:
    ledger = _object(raw, "source_family_ledger")
    _exact(ledger, {"completeness", "ordering", "families"}, "source_family_ledger")
    _require(
        ledger["completeness"] == "complete_for_governed_observation_set",
        "source_family_ledger.completeness is unsupported",
    )
    _require(
        ledger["ordering"] == "source_family_id_ascending_with_image_id_ascending",
        "source_family_ledger.ordering is unsupported",
    )
    families = _array(ledger["families"], "source_family_ledger.families")
    _require(bool(families), "source_family_ledger.families must not be empty")
    family_ids: list[str] = []
    family_by_image: dict[str, str] = {}
    family_by_source_sha256: dict[str, str] = {}
    for index, raw_family in enumerate(families):
        location = f"source_family_ledger.families[{index}]"
        family = _object(raw_family, location)
        _exact(family, {"source_family_id", "description", "image_ids"}, location)
        family_id = _identifier(family["source_family_id"], f"{location}.source_family_id")
        _nonempty(family["description"], f"{location}.description")
        image_ids = [
            _identifier(value, f"{location}.image_ids[{item_index}]")
            for item_index, value in enumerate(_array(family["image_ids"], f"{location}.image_ids"))
        ]
        _require(bool(image_ids), f"{location}.image_ids must not be empty")
        _require(
            image_ids == sorted(image_ids) and len(image_ids) == len(set(image_ids)),
            f"{location}.image_ids must be unique and ascending",
        )
        for image_id in image_ids:
            _require(image_id in images, f"{location}.image_ids contains an unknown governed image")
            _require(image_id not in family_by_image, "source-family image membership must be unique")
            family_by_image[image_id] = family_id
            source_sha256 = images[image_id].source_sha256
            if source_sha256 in family_by_source_sha256:
                _require(
                    family_by_source_sha256[source_sha256] == family_id,
                    "identical source SHA-256 values must not be assigned to conflicting source families",
                )
            else:
                family_by_source_sha256[source_sha256] = family_id
        family_ids.append(family_id)
    _require(
        family_ids == sorted(family_ids) and len(family_ids) == len(set(family_ids)),
        "source families must have unique ascending source_family_id",
    )
    _require(set(family_by_image) == set(images), "source-family ledger must cover every governed image exactly once")
    return family_by_image


def _validate_region_review(raw: Any, location: str) -> None:
    review = _object(raw, location)
    _exact(review, {"state", "reviewer_ids", "reviewed_at", "notes"}, location)
    _require(review["state"] == "accepted", f"{location}.state must be accepted")
    reviewer_ids = [
        _identifier(value, f"{location}.reviewer_ids[{index}]")
        for index, value in enumerate(_array(review["reviewer_ids"], f"{location}.reviewer_ids"))
    ]
    _require(bool(reviewer_ids), f"{location}.reviewer_ids must not be empty")
    _require(
        reviewer_ids == sorted(reviewer_ids) and len(reviewer_ids) == len(set(reviewer_ids)),
        f"{location}.reviewer_ids must be unique and ascending",
    )
    _timestamp(review["reviewed_at"], f"{location}.reviewed_at")
    if review["notes"] is not None:
        _nonempty(review["notes"], f"{location}.notes")


def _validate_region_ledger(
    raw: Any,
    *,
    images: Mapping[str, _ImageContext],
    source_family_by_image: Mapping[str, str],
) -> tuple[
    dict[tuple[str, str], Mapping[str, Any]],
    Mapping[str, int],
]:
    ledger = _object(raw, "region_ledger")
    _exact(ledger, {"completeness", "ordering", "regions", "counts"}, "region_ledger")
    _require(
        ledger["completeness"] == "exhaustive_for_governed_observation_set",
        "region_ledger.completeness is unsupported",
    )
    _require(
        ledger["ordering"] == "image_id_annotation_id_region_id_ascending",
        "region_ledger.ordering is unsupported",
    )

    regions = _array(ledger["regions"], "region_ledger.regions")
    _require(bool(regions), "region_ledger.regions must not be empty")
    by_scope: dict[tuple[str, str], Mapping[str, Any]] = {}
    region_ids: set[str] = set()
    ordering_keys: list[tuple[str, str, str]] = []
    disposition_counts: Counter[str] = Counter()
    nuclear_count = 0
    ignore_count = 0
    allowed_exclusion_reasons = {
        "outside_reference_sampling_scope",
        "duplicate_or_redundant_region",
        "insufficient_dapi_signal",
        "region_level_acquisition_artifact",
        "region_level_staining_artifact",
        "physical_edge_dominated",
        "other_protocol_defined_exclusion",
    }

    for index, raw_region in enumerate(regions):
        location = f"region_ledger.regions[{index}]"
        region = _object(raw_region, location)
        _exact(
            region,
            {
                "region_id",
                "image_id",
                "biological_unit_id",
                "annotation_id",
                "coordinate_space_id",
                "source_family_id",
                "disposition",
                "exclusion_reason",
                "counts",
                "review",
            },
            location,
        )
        region_id = _identifier(region["region_id"], f"{location}.region_id")
        _require(region_id not in region_ids, "region_ledger.region_id values must be unique")
        region_ids.add(region_id)
        image_id = _identifier(region["image_id"], f"{location}.image_id")
        _require(image_id in images, f"{location}.image_id is not governed")
        image = images[image_id]
        _require(
            region["biological_unit_id"] == image.biological_unit_id,
            f"{location}.biological_unit_id does not match its governed image",
        )
        annotation_id = _identifier(region["annotation_id"], f"{location}.annotation_id")
        _require(
            annotation_id in image.include_annotation_ids,
            f"{location}.annotation_id does not resolve to a governed include ROI",
        )
        _require(
            region["coordinate_space_id"] == image.coordinate_space_id,
            f"{location}.coordinate_space_id does not match its governed image",
        )
        _require(
            region["source_family_id"] == source_family_by_image[image_id],
            f"{location}.source_family_id does not match the source-family ledger",
        )
        disposition = _enum(
            region["disposition"],
            {"include", "exclude"},
            f"{location}.disposition",
        )
        if disposition == "exclude":
            _enum(
                region["exclusion_reason"],
                allowed_exclusion_reasons,
                f"{location}.exclusion_reason",
            )
        else:
            _require(
                region["exclusion_reason"] is None,
                f"{location}.exclusion_reason must be null unless disposition is exclude",
            )

        counts = _object(region["counts"], f"{location}.counts")
        _exact(
            counts,
            {"nuclear_reference_objects", "reference_ignore_regions"},
            f"{location}.counts",
        )
        region_nuclear_count = _integer(
            counts["nuclear_reference_objects"],
            f"{location}.counts.nuclear_reference_objects",
        )
        region_ignore_count = _integer(
            counts["reference_ignore_regions"],
            f"{location}.counts.reference_ignore_regions",
        )
        if disposition != "include":
            _require(
                region_nuclear_count == 0 and region_ignore_count == 0,
                f"{location}: excluded regions cannot bind reference artifacts",
            )
        _validate_region_review(region["review"], f"{location}.review")

        scope = (image_id, annotation_id)
        _require(scope not in by_scope, "region ledger must contain each governed ROI exactly once")
        by_scope[scope] = region
        ordering_keys.append((image_id, annotation_id, region_id))
        disposition_counts[disposition] += 1
        nuclear_count += region_nuclear_count
        ignore_count += region_ignore_count

    _require(
        ordering_keys == sorted(ordering_keys),
        "region_ledger.regions must use image/annotation/region ascending order",
    )
    expected_scopes = {
        (image_id, annotation_id)
        for image_id, image in images.items()
        for annotation_id in image.include_annotation_ids
    }
    _require(
        set(by_scope) == expected_scopes,
        "region ledger must exhaustively cover every governed include ROI exactly once",
    )

    declared = _object(ledger["counts"], "region_ledger.counts")
    _exact(
        declared,
        {
            "regions_total",
            "include",
            "exclude",
            "nuclear_reference_objects",
            "reference_ignore_regions",
        },
        "region_ledger.counts",
    )
    actual_counts = {
        "regions_total": len(regions),
        "include": disposition_counts["include"],
        "exclude": disposition_counts["exclude"],
        "nuclear_reference_objects": nuclear_count,
        "reference_ignore_regions": ignore_count,
    }
    for field, actual in actual_counts.items():
        declared_value = _integer(declared[field], f"region_ledger.counts.{field}")
        _require(
            declared_value == actual,
            f"region_ledger.counts.{field} does not match the region ledger",
        )
    return by_scope, actual_counts


def _validate_frozen_state(
    raw: Any,
    *,
    change_policy: str,
    location: str = "state",
) -> datetime:
    state = _object(raw, location)
    _exact(state, {"status", "frozen_at", "frozen_by", "change_policy"}, location)
    _require(state["status"] == "frozen", f"{location}.status must be frozen")
    frozen_at = _timestamp(state["frozen_at"], f"{location}.frozen_at")
    _identifier(state["frozen_by"], f"{location}.frozen_by")
    _require(
        state["change_policy"] == change_policy,
        f"{location}.change_policy is unsupported",
    )
    return frozen_at


def _validate_reference_artifacts(
    root: Path,
    raw: Any,
    *,
    reference_set_id: str,
    images: Mapping[str, _ImageContext],
    regions_by_scope: Mapping[tuple[str, str], Mapping[str, Any]],
    declared_region_counts: Mapping[str, int],
) -> tuple[
    list[tuple[str, str, str]],
    list[tuple[str, str, str]],
    int,
    int,
    Mapping[str, bool],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
]:
    artifacts = _object(raw, "artifacts")
    _exact(
        artifacts,
        {"nuclear_reference_objects", "reference_ignore_regions"},
        "artifacts",
    )
    nuclear_records, _nuclear_path = _load_canonical_ndjson(
        root,
        artifacts["nuclear_reference_objects"],
        "artifacts.nuclear_reference_objects",
        record_schema=NUCLEAR_REFERENCE_OBJECT_SCHEMA,
    )
    ignore_records, _ignore_path = _load_canonical_ndjson(
        root,
        artifacts["reference_ignore_regions"],
        "artifacts.reference_ignore_regions",
        record_schema=REFERENCE_IGNORE_REGION_SCHEMA,
    )

    nuclear_keys: list[tuple[str, str, str]] = []
    ignore_keys: list[tuple[str, str, str]] = []
    nuclear_by_scope: Counter[tuple[str, str]] = Counter()
    ignore_by_scope: Counter[tuple[str, str]] = Counter()
    model_assisted_count = 0
    model_assisted_single_review_count = 0
    nonconfirmatory_images: set[str] = set()
    nuclear_by_image: Counter[str] = Counter()
    nuclear_geometry_keys: set[tuple[str, str, str]] = set()
    ignore_geometry_keys: set[tuple[str, str]] = set()
    nuclear_geometries_by_image: dict[str, list[_ParsedGeometry]] = defaultdict(list)
    ignore_geometries_by_image: dict[str, list[_ParsedGeometry]] = defaultdict(list)

    for index, record in enumerate(nuclear_records):
        key, model_assisted, model_assisted_single_review = _validate_nuclear_record(
            record,
            reference_set_id=reference_set_id,
            images=images,
            location=f"artifacts.nuclear_reference_objects.records[{index}]",
        )
        scope = key[:2]
        _require(scope in regions_by_scope, "nuclear reference object does not resolve to a ledger region")
        _require(
            regions_by_scope[scope]["disposition"] == "include",
            "nuclear reference object targets a region not included for reference use",
        )
        geometry_key = (
            key[0],
            canonical_sha256(record["target"]),
            canonical_sha256(record["geometry"]),
        )
        _require(
            geometry_key not in nuclear_geometry_keys,
            "duplicate nuclear geometry within an image and target",
        )
        nuclear_geometry_keys.add(geometry_key)
        nuclear_geometries_by_image[key[0]].append(
            _parse_polygon_geometry(
                str(record["geometry"]["geometry_type"]),
                str(record["geometry"]["wkt"]),
                f"artifacts.nuclear_reference_objects.records[{index}].geometry",
            )
        )
        nuclear_keys.append(key)
        nuclear_by_scope[scope] += 1
        nuclear_by_image[key[0]] += 1
        model_assisted_count += int(model_assisted)
        model_assisted_single_review_count += int(model_assisted_single_review)
        if model_assisted_single_review:
            nonconfirmatory_images.add(key[0])

    for index, record in enumerate(ignore_records):
        key = _validate_ignore_record(
            record,
            reference_set_id=reference_set_id,
            images=images,
            location=f"artifacts.reference_ignore_regions.records[{index}]",
        )
        scope = key[:2]
        _require(scope in regions_by_scope, "reference ignore region does not resolve to a ledger region")
        _require(
            regions_by_scope[scope]["disposition"] == "include",
            "reference ignore region targets a region not included for reference use",
        )
        geometry_key = (key[0], canonical_sha256(record["geometry"]))
        _require(
            geometry_key not in ignore_geometry_keys,
            "duplicate ignore geometry within an image",
        )
        ignore_geometry_keys.add(geometry_key)
        ignore_geometries_by_image[key[0]].append(
            _parse_polygon_geometry(
                str(record["geometry"]["geometry_type"]),
                str(record["geometry"]["wkt"]),
                f"artifacts.reference_ignore_regions.records[{index}].geometry",
            )
        )
        ignore_keys.append(key)
        ignore_by_scope[scope] += 1

    for image_id, nuclear_geometries in nuclear_geometries_by_image.items():
        for nuclear_geometry in nuclear_geometries:
            _require(
                not any(
                    _geometries_intersect_inclusive(nuclear_geometry, ignore_geometry)
                    for ignore_geometry in ignore_geometries_by_image[image_id]
                ),
                "nuclear reference geometry intersects a same-image reference ignore geometry",
            )

    _require(
        nuclear_keys == sorted(nuclear_keys) and len(nuclear_keys) == len(set(nuclear_keys)),
        "nuclear reference records must have unique IDs in declared ascending order",
    )
    _require(
        ignore_keys == sorted(ignore_keys) and len(ignore_keys) == len(set(ignore_keys)),
        "reference ignore records must have unique IDs in declared ascending order",
    )
    _require(
        bool(nuclear_keys),
        "reference set must contain at least one nuclear reference object",
    )
    _require(
        len(nuclear_keys) == declared_region_counts["nuclear_reference_objects"],
        "nuclear reference artifact count does not match the region ledger",
    )
    _require(
        len(ignore_keys) == declared_region_counts["reference_ignore_regions"],
        "reference ignore artifact count does not match the region ledger",
    )
    for scope, region in regions_by_scope.items():
        counts = region["counts"]
        _require(
            nuclear_by_scope[scope] == counts["nuclear_reference_objects"],
            "region nuclear-reference count does not match canonical records",
        )
        _require(
            ignore_by_scope[scope] == counts["reference_ignore_regions"],
            "region ignore-reference count does not match canonical records",
        )
    confirmatory_ready_by_image = {
        image_id: nuclear_by_image[image_id] > 0 and image_id not in nonconfirmatory_images
        for image_id in images
    }
    return (
        nuclear_keys,
        ignore_keys,
        model_assisted_count,
        model_assisted_single_review_count,
        confirmatory_ready_by_image,
        tuple(nuclear_records),
        tuple(ignore_records),
    )


def _validate_nuclear_reference_set_path(
    manifest_path: Path,
    ancestor_paths: frozenset[Path],
) -> _ReferenceContext:
    manifest_path = manifest_path.resolve()
    _require(manifest_path not in ancestor_paths, "reference-set parent lineage contains a cycle")
    _require(len(ancestor_paths) < 256, "reference-set parent lineage exceeds 256 revisions")
    ancestor_paths = ancestor_paths | {manifest_path}
    root = manifest_path.parent.resolve()
    document = _load_mapping(manifest_path, "nuclear_reference_set")
    _exact(
        document,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "reference_set_id",
            "study_id",
            "revision",
            "revision_reason",
            "parent",
            "governed_observation_set",
            "task",
            "evaluation_policy",
            "selection_protocol",
            "source_family_ledger",
            "region_ledger",
            "artifacts",
            "state",
            "provenance",
            "claims",
        },
        "nuclear_reference_set",
    )
    _require(
        document["$schema"] == NUCLEAR_REFERENCE_SET_SCHEMA,
        "nuclear_reference_set.$schema is unsupported",
    )
    _require(
        document["contract_type"] == "ifquant_platform_nuclear_reference_set",
        "nuclear_reference_set.contract_type is unsupported",
    )
    _require(
        document["contract_version"] == "1.0.0",
        "nuclear_reference_set.contract_version is unsupported",
    )
    reference_set_id = _identifier(
        document["reference_set_id"],
        "nuclear_reference_set.reference_set_id",
    )
    study_id = _identifier(document["study_id"], "nuclear_reference_set.study_id")
    revision = _integer(document["revision"], "nuclear_reference_set.revision")
    _require(revision <= 255, "nuclear_reference_set.revision must be at most 255")
    _nonempty(document["revision_reason"], "nuclear_reference_set.revision_reason")
    parent = _validate_reference_parent(root, document, revision, ancestor_paths)

    governed = _load_governed_context(
        root,
        document["governed_observation_set"],
        study_id=study_id,
    )
    _validate_task_and_policies(root, document)
    source_family_by_image = _validate_source_families(
        document["source_family_ledger"],
        governed.images,
    )
    regions_by_scope, region_counts = _validate_region_ledger(
        document["region_ledger"],
        images=governed.images,
        source_family_by_image=source_family_by_image,
    )
    (
        nuclear_keys,
        ignore_keys,
        model_assisted_count,
        model_assisted_single_review_count,
        confirmatory_ready_by_image,
        nuclear_records,
        ignore_records,
    ) = _validate_reference_artifacts(
        root,
        document["artifacts"],
        reference_set_id=reference_set_id,
        images=governed.images,
        regions_by_scope=regions_by_scope,
        declared_region_counts=region_counts,
    )
    frozen_at = _validate_frozen_state(
        document["state"],
        change_policy="new_reference_set_revision_required",
    )
    created_at = _validate_provenance(root, document["provenance"])
    _require(created_at <= frozen_at, "provenance.created_at must not follow state.frozen_at")
    for upstream_location, upstream_at in governed.upstream_timestamps:
        _require(
            upstream_at <= frozen_at,
            f"{upstream_location} must not follow reference state.frozen_at",
        )
    for (
        parent_location,
        parent_created_at,
        child_location,
        child_created_at,
    ) in governed.revision_chronology:
        _require(
            parent_created_at <= child_created_at,
            f"{parent_location}.provenance.created_at must not follow its direct child "
            f"{child_location}.provenance.created_at",
        )
    if parent is not None:
        parent_frozen_at = _timestamp(
            parent.document["state"]["frozen_at"],
            "parent.state.frozen_at",
        )
        _require(
            parent_frozen_at <= created_at,
            "parent reference state.frozen_at must not follow successor provenance.created_at",
        )
    for region_index, region in enumerate(document["region_ledger"]["regions"]):
        reviewed_at = _timestamp(
            region["review"]["reviewed_at"],
            f"region_ledger.regions[{region_index}].review.reviewed_at",
        )
        _require(
            reviewed_at <= frozen_at,
            f"region_ledger.regions[{region_index}].review.reviewed_at must not follow state.frozen_at",
        )
    for artifact_name, records in (
        ("nuclear_reference_objects", nuclear_records),
        ("reference_ignore_regions", ignore_records),
    ):
        for record_index, record in enumerate(records):
            reviewed_at = _timestamp(
                record["review"]["reviewed_at"],
                f"artifacts.{artifact_name}.records[{record_index}].review.reviewed_at",
            )
            _require(
                reviewed_at <= frozen_at,
                f"artifacts.{artifact_name}.records[{record_index}].review.reviewed_at "
                "must not follow state.frozen_at",
            )
    _validate_claims(document["claims"])

    reference_image_ids = frozenset(
        image_id
        for (image_id, _annotation_id), region in regions_by_scope.items()
        if region["disposition"] == "include"
    )
    _require(bool(reference_image_ids), "reference set must include at least one reviewed region")
    reference_set_sha256 = canonical_sha256(document)
    report = NuclearReferenceSetReport(
        status="valid",
        reference_set_id=reference_set_id,
        study_id=study_id,
        revision=revision,
        reference_set_sha256=reference_set_sha256,
        governed_observation_set_id=governed.report.observation_set_id,
        governed_observation_set_revision=governed.report.revision,
        governed_observation_set_sha256=governed.report.observation_set_sha256,
        image_count=len(reference_image_ids),
        source_family_count=len(set(source_family_by_image.values())),
        region_count=region_counts["regions_total"],
        nuclear_reference_object_count=len(nuclear_keys),
        reference_ignore_region_count=len(ignore_keys),
        model_assisted_object_count=model_assisted_count,
        model_assisted_single_review_count=model_assisted_single_review_count,
        model_assisted_nonconfirmatory_review_count=model_assisted_single_review_count,
        confirmatory_reference_ready=(
            all(confirmatory_ready_by_image[image_id] for image_id in reference_image_ids)
        ),
    )
    return _ReferenceContext(
        report=report,
        document=document,
        governed=governed,
        source_family_by_image=source_family_by_image,
        reference_image_ids=reference_image_ids,
        confirmatory_ready_by_image=confirmatory_ready_by_image,
        regions_by_scope=regions_by_scope,
        nuclear_records=nuclear_records,
        ignore_records=ignore_records,
        parent=parent,
    )


def validate_nuclear_reference_set(
    reference_set: str | Path,
) -> NuclearReferenceSetReport:
    """Validate a frozen DAPI nuclear-reference set and every bound artifact."""

    supplied_path = Path(reference_set)
    manifest_path = (
        supplied_path / "nuclear-reference-set.json"
        if supplied_path.is_dir()
        else supplied_path
    )
    return _validate_nuclear_reference_set_path(manifest_path, frozenset()).report


def _held_out_reference_content_descriptor(
    reference: _ReferenceContext,
    image_ids: Sequence[str],
) -> Mapping[str, Any]:
    validated_image_ids = [
        _identifier(value, f"held_out_reference_image_ids[{index}]")
        for index, value in enumerate(_array(image_ids, "held_out_reference_image_ids"))
    ]
    _require(
        bool(validated_image_ids)
        and validated_image_ids == sorted(validated_image_ids)
        and len(validated_image_ids) == len(set(validated_image_ids)),
        "held-out reference image IDs must be nonempty, unique, and ascending",
    )
    _require(
        set(validated_image_ids) <= set(reference.reference_image_ids),
        "held-out reference image IDs must resolve to included reference images",
    )

    images: list[Mapping[str, Any]] = []
    for image_id in validated_image_ids:
        regions = sorted(
            (
                region
                for (region_image_id, _annotation_id), region
                in reference.regions_by_scope.items()
                if region_image_id == image_id
            ),
            key=lambda region: (region["annotation_id"], region["region_id"]),
        )
        nuclear_records = sorted(
            (
                record
                for record in reference.nuclear_records
                if record["image_id"] == image_id
            ),
            key=lambda record: (record["annotation_id"], record["reference_object_id"]),
        )
        ignore_records = sorted(
            (
                record
                for record in reference.ignore_records
                if record["image_id"] == image_id
            ),
            key=lambda record: (record["annotation_id"], record["ignore_region_id"]),
        )
        images.append(
            {
                "image_id": image_id,
                "observation": reference.governed.observations_by_image[image_id],
                "source_family_id": reference.source_family_by_image[image_id],
                "regions": regions,
                "nuclear_reference_objects": nuclear_records,
                "reference_ignore_regions": ignore_records,
            }
        )
    return {
        "profile": HELD_OUT_REFERENCE_CONTENT_PROFILE,
        "task": reference.document["task"],
        "evaluation_policy": reference.document["evaluation_policy"],
        "selection_protocol": reference.document["selection_protocol"],
        "images": images,
    }


def _held_out_reference_content_sha256(
    reference: _ReferenceContext,
    image_ids: Sequence[str],
) -> str:
    return canonical_sha256(_held_out_reference_content_descriptor(reference, image_ids))


def compute_held_out_reference_content_sha256(
    reference_set: str | Path,
    image_ids: Sequence[str],
) -> str:
    """Hash the exact held-out subset under the v1 content-lock profile."""

    supplied_path = Path(reference_set)
    manifest_path = (
        supplied_path / "nuclear-reference-set.json"
        if supplied_path.is_dir()
        else supplied_path
    )
    reference = _validate_nuclear_reference_set_path(manifest_path, frozenset())
    return _held_out_reference_content_sha256(reference, image_ids)


def _load_reference_context(
    root: Path,
    raw: Any,
    *,
    study_id: str,
) -> _ReferenceContext:
    location = "reference_set"
    reference = _object(raw, location)
    _exact(
        reference,
        {"reference_set_id", "revision", "manifest_relative_path", "manifest_sha256"},
        location,
    )
    reference_set_id = _identifier(reference["reference_set_id"], f"{location}.reference_set_id")
    revision = _integer(reference["revision"], f"{location}.revision")
    expected_hash = _sha256(reference["manifest_sha256"], f"{location}.manifest_sha256")
    path = _safe_relative(root, reference["manifest_relative_path"], f"{location}.manifest_relative_path")
    context = _validate_nuclear_reference_set_path(path, frozenset())
    _require(context.report.reference_set_id == reference_set_id, f"{location}.reference_set_id does not match")
    _require(context.report.revision == revision, f"{location}.revision does not match")
    _require(context.report.study_id == study_id, f"{location}.study_id does not match the split manifest")
    _require(context.report.reference_set_sha256 == expected_hash, f"{location}.manifest_sha256 does not match")
    return context


def _validate_split_design(raw: Any) -> Mapping[str, Mapping[str, Any]]:
    design = _object(raw, "design")
    _exact(
        design,
        {"assignment_unit", "partitions", "hard_separation_keys", "domain_controls"},
        "design",
    )
    _require(design["assignment_unit"] == "image", "design.assignment_unit must be image")
    _require(list(_array(design["partitions"], "design.partitions")) == list(_PARTITIONS), "design.partitions is unsupported")
    _require(
        list(_array(design["hard_separation_keys"], "design.hard_separation_keys"))
        == list(_HARD_SEPARATION_KEYS),
        "design.hard_separation_keys is unsupported",
    )
    controls = _object(design["domain_controls"], "design.domain_controls")
    _exact(controls, set(_DOMAIN_KEYS), "design.domain_controls")
    normalized: dict[str, Mapping[str, Any]] = {}
    for key in _DOMAIN_KEYS:
        location = f"design.domain_controls.{key}"
        control = _object(controls[key], location)
        _exact(control, {"mode", "leave_out_values"}, location)
        mode = _enum(control["mode"], {"partition_disjoint", "leave_values_out"}, f"{location}.mode")
        leave_values = [
            _identifier(value, f"{location}.leave_out_values[{index}]")
            for index, value in enumerate(_array(control["leave_out_values"], f"{location}.leave_out_values"))
        ]
        _require(
            leave_values == sorted(leave_values) and len(leave_values) == len(set(leave_values)),
            f"{location}.leave_out_values must be unique and ascending",
        )
        if mode == "partition_disjoint":
            _require(not leave_values, f"{location}.leave_out_values must be empty")
        else:
            _require(bool(leave_values), f"{location}.leave_out_values must not be empty")
        normalized[key] = control
    return normalized


def _validate_hard_components(
    assignments: Mapping[str, Mapping[str, Any]],
    reference: _ReferenceContext,
) -> None:
    parents = {
        image_id: image_id
        for image_id in reference.governed.images
    }

    def find(image_id: str) -> str:
        root = image_id
        while parents[root] != root:
            root = parents[root]
        while parents[image_id] != image_id:
            next_image = parents[image_id]
            parents[image_id] = root
            image_id = next_image
        return root

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for key in _HARD_SEPARATION_KEYS:
        first_by_value: dict[str, str] = {}
        for image_id, image in reference.governed.images.items():
            if key == "source_family_id":
                value = reference.source_family_by_image[image_id]
            else:
                value = str(getattr(image, key))
            if value in first_by_value:
                union(first_by_value[value], image_id)
            else:
                first_by_value[value] = image_id

    partitions_by_component: dict[str, set[str]] = defaultdict(set)
    for image_id, assignment in assignments.items():
        partitions_by_component[find(image_id)].add(str(assignment["partition"]))
    _require(
        all(len(partitions) == 1 for partitions in partitions_by_component.values()),
        "a mouse/slide/source-family connected component crosses split partitions",
    )


def _validate_domain_controls(
    controls: Mapping[str, Mapping[str, Any]],
    assignments: Mapping[str, Mapping[str, Any]],
) -> None:
    for key in _DOMAIN_KEYS:
        control = controls[key]
        mode = str(control["mode"])
        values_by_partition = {
            partition: {
                str(assignment[key])
                for assignment in assignments.values()
                if assignment["partition"] == partition
            }
            for partition in _PARTITIONS
        }
        location = f"design.domain_controls.{key}"
        if mode == "partition_disjoint":
            for left_index, left in enumerate(_PARTITIONS):
                for right in _PARTITIONS[left_index + 1 :]:
                    _require(
                        not (values_by_partition[left] & values_by_partition[right]),
                        f"{location}: a {key} value crosses {left} and {right}",
                    )
        else:
            leave_values = set(control["leave_out_values"])
            _require(
                values_by_partition["held_out_test"] == leave_values,
                f"{location}.leave_out_values must exactly equal held-out-test values",
            )
            _require(
                not leave_values & (values_by_partition["train"] | values_by_partition["tuning"]),
                f"{location}: leave-out values occur outside held_out_test",
            )


def _validate_assignments(
    raw: Any,
    reference: _ReferenceContext,
    controls: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], Counter[str]]:
    assignments = _array(raw, "image_assignments")
    _require(len(assignments) >= 3, "image_assignments must contain at least three images")
    by_image: dict[str, Mapping[str, Any]] = {}
    image_ids: list[str] = []
    partition_counts: Counter[str] = Counter()
    for index, raw_assignment in enumerate(assignments):
        location = f"image_assignments[{index}]"
        assignment = _object(raw_assignment, location)
        _exact(
            assignment,
            {
                "image_id",
                "mouse_id",
                "slide_id",
                "source_family_id",
                "batch_id",
                "scanner_id",
                "partition",
            },
            location,
        )
        image_id = _identifier(assignment["image_id"], f"{location}.image_id")
        _require(image_id in reference.reference_image_ids, f"{location}.image_id is not in reference scope")
        _require(image_id not in by_image, "image_assignments.image_id values must be unique")
        governed = reference.governed.images[image_id]
        expected = {
            "mouse_id": governed.mouse_id,
            "slide_id": governed.slide_id,
            "source_family_id": reference.source_family_by_image[image_id],
            "batch_id": governed.batch_id,
            "scanner_id": governed.scanner_id,
        }
        for key, expected_value in expected.items():
            _identifier(assignment[key], f"{location}.{key}")
            _require(
                assignment[key] == expected_value,
                f"{location}.{key} does not match the bound reference set",
            )
        partition = _enum(assignment["partition"], set(_PARTITIONS), f"{location}.partition")
        if partition == "held_out_test":
            _require(
                reference.confirmatory_ready_by_image[image_id],
                f"{location}: reference image is not held-out-test ready; it requires positive "
                "nuclear instances and confirmatory model-assisted review",
            )
        by_image[image_id] = assignment
        image_ids.append(image_id)
        partition_counts[partition] += 1

    _require(image_ids == sorted(image_ids), "image_assignments must use ascending image_id order")
    _require(
        set(by_image) == set(reference.reference_image_ids),
        "image_assignments must cover every included reference image exactly once",
    )
    _require(
        all(partition_counts[partition] > 0 for partition in _PARTITIONS),
        "train, tuning, and held_out_test must each contain at least one image",
    )
    _validate_hard_components(by_image, reference)
    _validate_domain_controls(controls, by_image)
    return by_image, partition_counts


def _validate_held_out_commitment(
    raw: Any,
    assignments: Mapping[str, Mapping[str, Any]],
    reference: _ReferenceContext,
) -> tuple[str, str]:
    commitment = _object(raw, "held_out_test_commitment")
    _exact(
        commitment,
        {
            "state",
            "partition",
            "image_ids",
            "image_ids_sha256",
            "canonicalization_profile",
            "ordering",
            "reference_content_profile",
            "reference_content_sha256",
            "committed_at",
            "committed_by",
            "change_policy",
            "successor_assignment_policy",
            "successor_new_image_policy",
            "successor_commitment_policy",
        },
        "held_out_test_commitment",
    )
    _require(commitment["state"] == "locked", "held_out_test_commitment.state must be locked")
    _require(
        commitment["partition"] == "held_out_test",
        "held_out_test_commitment.partition is unsupported",
    )
    image_ids = [
        _identifier(value, f"held_out_test_commitment.image_ids[{index}]")
        for index, value in enumerate(_array(commitment["image_ids"], "held_out_test_commitment.image_ids"))
    ]
    _require(
        bool(image_ids) and image_ids == sorted(image_ids) and len(image_ids) == len(set(image_ids)),
        "held_out_test_commitment.image_ids must be nonempty, unique, and ascending",
    )
    actual_held_out = sorted(
        image_id
        for image_id, assignment in assignments.items()
        if assignment["partition"] == "held_out_test"
    )
    _require(
        image_ids == actual_held_out,
        "held_out_test_commitment.image_ids must exactly match held-out-test assignments",
    )
    expected_hash = _sha256(
        commitment["image_ids_sha256"],
        "held_out_test_commitment.image_ids_sha256",
    )
    _require(
        canonical_sha256(image_ids) == expected_hash,
        "held_out_test_commitment.image_ids_sha256 does not match canonical image_ids",
    )
    _require(
        commitment["canonicalization_profile"] == "ifquant_canonical_json_v1",
        "held_out_test_commitment.canonicalization_profile is unsupported",
    )
    _require(
        commitment["ordering"] == "image_id_ascending",
        "held_out_test_commitment.ordering is unsupported",
    )
    _require(
        commitment["reference_content_profile"] == HELD_OUT_REFERENCE_CONTENT_PROFILE,
        "held_out_test_commitment.reference_content_profile is unsupported",
    )
    reference_content_sha256 = _sha256(
        commitment["reference_content_sha256"],
        "held_out_test_commitment.reference_content_sha256",
    )
    _require(
        _held_out_reference_content_sha256(reference, image_ids)
        == reference_content_sha256,
        "held_out_test_commitment.reference_content_sha256 does not match exact held-out reference content",
    )
    _timestamp(commitment["committed_at"], "held_out_test_commitment.committed_at")
    _identifier(commitment["committed_by"], "held_out_test_commitment.committed_by")
    _require(
        commitment["change_policy"] == "new_split_manifest_revision_required",
        "held_out_test_commitment.change_policy is unsupported",
    )
    _require(
        commitment["successor_assignment_policy"] == "preserve_all_prior_image_assignments",
        "held_out_test_commitment.successor_assignment_policy is unsupported",
    )
    _require(
        commitment["successor_new_image_policy"]
        == "new_images_may_enter_train_or_tuning_only",
        "held_out_test_commitment.successor_new_image_policy is unsupported",
    )
    _require(
        commitment["successor_commitment_policy"] == "preserve_held_out_test_commitment",
        "held_out_test_commitment.successor_commitment_policy is unsupported",
    )
    return expected_hash, reference_content_sha256


def _validate_split_claims(raw: Any) -> None:
    claims = _object(raw, "claims")
    _exact(
        claims,
        {
            "scientific_validation",
            "biological_ground_truth",
            "backend_equivalence",
            "model_universality",
            "split_optimality",
            "population_representativeness",
            "domain_generalizability",
            "authorization",
        },
        "claims",
    )
    for field in (
        "scientific_validation",
        "biological_ground_truth",
        "backend_equivalence",
        "model_universality",
        "split_optimality",
        "population_representativeness",
        "domain_generalizability",
    ):
        _require(claims[field] is False, f"claims.{field} must be false")
    _require(claims["authorization"] == "none", "claims.authorization must be 'none'")


def _reference_lineage_contains(
    current: _ReferenceContext,
    ancestor: _ReferenceContext,
) -> bool:
    target = (
        ancestor.report.reference_set_id,
        ancestor.report.revision,
        ancestor.report.reference_set_sha256,
    )
    cursor: _ReferenceContext | None = current
    while cursor is not None:
        identity = (
            cursor.report.reference_set_id,
            cursor.report.revision,
            cursor.report.reference_set_sha256,
        )
        if identity == target:
            return True
        cursor = cursor.parent
    return False


def _validate_split_successor(
    document: Mapping[str, Any],
    *,
    parent: _SplitContext | None,
    reference: _ReferenceContext,
    assignments: Mapping[str, Mapping[str, Any]],
) -> None:
    if parent is None:
        return
    _require(
        _reference_lineage_contains(reference, parent.reference),
        "successor split reference set must retain its parent's reference-set revision in lineage",
    )
    _require(document["design"] == parent.document["design"], "successor split must retain its design")
    _require(
        document["held_out_test_commitment"] == parent.document["held_out_test_commitment"],
        "successor split must retain the exact held-out-test commitment",
    )
    for image_id, parent_assignment in parent.assignments_by_image.items():
        _require(image_id in assignments, "successor split cannot remove a prior image assignment")
        _require(
            assignments[image_id] == parent_assignment,
            "successor split cannot change a prior image assignment",
        )
    for image_id in set(assignments) - set(parent.assignments_by_image):
        _require(
            assignments[image_id]["partition"] in {"train", "tuning"},
            "successor split additions are limited to train or tuning",
        )


def _validate_split_parent(
    root: Path,
    document: Mapping[str, Any],
    revision: int,
    ancestor_paths: frozenset[Path],
) -> _SplitContext | None:
    raw = document["parent"]
    if revision == 0:
        _require(raw is None, "parent must be null for split revision 0")
        return None
    _require(raw is not None, "parent is required after split revision 0")
    parent = _object(raw, "parent")
    _exact(parent, {"split_manifest_id", "revision", "manifest_relative_path", "manifest_sha256"}, "parent")
    parent_id = _identifier(parent["split_manifest_id"], "parent.split_manifest_id")
    parent_revision = _integer(parent["revision"], "parent.revision")
    expected_hash = _sha256(parent["manifest_sha256"], "parent.manifest_sha256")
    path = _safe_relative(root, parent["manifest_relative_path"], "parent.manifest_relative_path")
    context = _validate_split_manifest_path(path, ancestor_paths)
    _require(context.report.split_manifest_id == parent_id, "parent.split_manifest_id does not match")
    _require(context.report.revision == parent_revision, "parent.revision does not match")
    _require(context.report.split_manifest_sha256 == expected_hash, "parent.manifest_sha256 does not match")
    _require(parent_id == document["split_manifest_id"], "parent must retain split_manifest_id")
    _require(context.report.study_id == document["study_id"], "parent must retain study_id")
    _require(parent_revision == revision - 1, "parent revision must immediately precede revision")
    return context


def _validate_split_manifest_path(
    manifest_path: Path,
    ancestor_paths: frozenset[Path],
) -> _SplitContext:
    manifest_path = manifest_path.resolve()
    _require(manifest_path not in ancestor_paths, "split-manifest parent lineage contains a cycle")
    _require(len(ancestor_paths) < 256, "split-manifest parent lineage exceeds 256 revisions")
    ancestor_paths = ancestor_paths | {manifest_path}
    root = manifest_path.parent.resolve()
    document = _load_mapping(manifest_path, "split_manifest")
    _exact(
        document,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "split_manifest_id",
            "study_id",
            "revision",
            "revision_reason",
            "parent",
            "reference_set",
            "design",
            "assignment_order",
            "image_assignments",
            "held_out_test_commitment",
            "state",
            "provenance",
            "claims",
        },
        "split_manifest",
    )
    _require(document["$schema"] == SPLIT_MANIFEST_SCHEMA, "split_manifest.$schema is unsupported")
    _require(
        document["contract_type"] == "ifquant_platform_split_manifest",
        "split_manifest.contract_type is unsupported",
    )
    _require(document["contract_version"] == "1.0.0", "split_manifest.contract_version is unsupported")
    split_manifest_id = _identifier(document["split_manifest_id"], "split_manifest.split_manifest_id")
    study_id = _identifier(document["study_id"], "split_manifest.study_id")
    revision = _integer(document["revision"], "split_manifest.revision")
    _require(revision <= 255, "split_manifest.revision must be at most 255")
    _nonempty(document["revision_reason"], "split_manifest.revision_reason")
    parent = _validate_split_parent(root, document, revision, ancestor_paths)
    reference = _load_reference_context(root, document["reference_set"], study_id=study_id)
    controls = _validate_split_design(document["design"])
    _require(document["assignment_order"] == "image_id_ascending", "assignment_order is unsupported")
    assignments, partition_counts = _validate_assignments(
        document["image_assignments"],
        reference,
        controls,
    )
    commitment_hash, commitment_content_hash = _validate_held_out_commitment(
        document["held_out_test_commitment"],
        assignments,
        reference,
    )
    split_frozen_at = _validate_frozen_state(
        document["state"],
        change_policy="new_split_manifest_revision_required",
    )
    split_created_at = _validate_provenance(root, document["provenance"])
    committed_at = _timestamp(
        document["held_out_test_commitment"]["committed_at"],
        "held_out_test_commitment.committed_at",
    )
    reference_frozen_at = _timestamp(
        reference.document["state"]["frozen_at"],
        "reference_set.state.frozen_at",
    )
    _require(
        reference_frozen_at <= split_created_at,
        "reference_set.state.frozen_at must not follow split provenance.created_at",
    )
    if revision == 0:
        _require(
            reference_frozen_at <= committed_at,
            "reference_set.state.frozen_at must not follow held_out_test_commitment.committed_at",
        )
    _require(
        committed_at <= split_frozen_at,
        "held_out_test_commitment.committed_at must not follow state.frozen_at",
    )
    _require(
        split_created_at <= split_frozen_at,
        "provenance.created_at must not follow state.frozen_at",
    )
    if parent is not None:
        parent_frozen_at = _timestamp(
            parent.document["state"]["frozen_at"],
            "parent.state.frozen_at",
        )
        _require(
            parent_frozen_at <= split_created_at,
            "parent split state.frozen_at must not follow successor provenance.created_at",
        )
    _validate_split_claims(document["claims"])
    _validate_split_successor(
        document,
        parent=parent,
        reference=reference,
        assignments=assignments,
    )
    report = SplitManifestReport(
        status="valid",
        split_manifest_id=split_manifest_id,
        study_id=study_id,
        revision=revision,
        split_manifest_sha256=canonical_sha256(document),
        reference_set_id=reference.report.reference_set_id,
        reference_set_revision=reference.report.revision,
        reference_set_sha256=reference.report.reference_set_sha256,
        assignment_count=len(assignments),
        train_count=partition_counts["train"],
        tuning_count=partition_counts["tuning"],
        held_out_test_count=partition_counts["held_out_test"],
        held_out_test_image_ids_sha256=commitment_hash,
        held_out_test_reference_content_sha256=commitment_content_hash,
        held_out_test_locked=True,
    )
    return _SplitContext(
        report=report,
        document=document,
        assignments_by_image=assignments,
        reference=reference,
        parent=parent,
    )


def validate_split_manifest(split_manifest: str | Path) -> SplitManifestReport:
    """Validate a frozen image-level split and its recursive reference boundary."""

    supplied_path = Path(split_manifest)
    manifest_path = (
        supplied_path / "split-manifest.json"
        if supplied_path.is_dir()
        else supplied_path
    )
    return _validate_split_manifest_path(manifest_path, frozenset()).report
