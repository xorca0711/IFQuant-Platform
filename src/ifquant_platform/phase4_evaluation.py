"""Deterministic Phase 4 instance-segmentation evaluation.

The evaluator consumes explicit pixel sets.  It deliberately does not infer
reference labels from predictions or raw images.  A passing report is evidence
that the declared computation completed; it is not scientific validation.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from math import floor
from pathlib import Path
from typing import Any

from .canonical import ContractError, canonical_sha256, file_sha256, parse_strict_json
from .phase3_validation import _parse_polygon_geometry, validate_split_manifest

PLAN_SCHEMA = "https://ifquant.org/contracts/platform/v1/segmentation-evaluation-plan.schema.json"
INSTANCE_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/segmentation-evaluation-instance.schema.json"
)
_PLAN_FIELDS = {
    "$schema",
    "contract_type",
    "contract_version",
    "evaluation_plan_id",
    "state",
    "declared_at",
    "backend_id",
    "split_manifest",
    "reference_set_sha256",
    "reference_instances",
    "partitions",
    "thresholds",
    "acceptance_criteria",
    "claims",
}
_CRITERIA_FIELDS = {
    "scope",
    "minimum_evaluable_image_count",
    "minimum_reference_object_count",
    "minimum_precision",
    "minimum_recall",
    "minimum_f1",
    "minimum_boundary_f1",
    "maximum_split_rate",
    "maximum_merge_rate",
    "maximum_mean_absolute_count_error_per_image",
    "maximum_measurement_mae",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{location} must be an object")
    return value


def _load_jsonl(path: Path) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        for number, line in enumerate(stream, 1):
            _require(line.endswith("\n"), f"{path}:{number} must end with LF")
            raw = parse_strict_json(line.encode("utf-8"), source=f"{path}:{number}")
            records.append(_mapping(raw, f"{path}:{number}"))
    return records


def _pixels(record: Mapping[str, Any], location: str) -> frozenset[tuple[int, int]]:
    raw = record.get("pixels")
    _require(isinstance(raw, list) and raw, f"{location}.pixels must be a nonempty array")
    result: set[tuple[int, int]] = set()
    previous: tuple[int, int] | None = None
    for index, pair in enumerate(raw):
        _require(
            isinstance(pair, list)
            and len(pair) == 2
            and all(
                isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in pair
            ),
            f"{location}.pixels[{index}] must be [nonnegative integer x, y]",
        )
        point = (pair[0], pair[1])
        _require(
            previous is None or point > previous, f"{location}.pixels must be unique and x/y sorted"
        )
        result.add(point)
        previous = point
    return frozenset(result)


def _point_in_ring(x: Decimal, y: Decimal, ring: tuple[tuple[Decimal, Decimal], ...]) -> bool:
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < crossing_x:
                inside = not inside
    return inside


def _rasterize_wkt(geometry_type: str, wkt: str, location: str) -> frozenset[tuple[int, int]]:
    """Rasterize WKT polygons by testing integer-pixel centers (x+.5, y+.5)."""
    geometry = _parse_polygon_geometry(geometry_type, wkt, location)
    all_points = [point for polygon in geometry.polygons for ring in polygon for point in ring]
    min_x = floor(min(point[0] for point in all_points))
    max_x = floor(max(point[0] for point in all_points))
    min_y = floor(min(point[1] for point in all_points))
    max_y = floor(max(point[1] for point in all_points))
    half = Decimal("0.5")
    pixels: set[tuple[int, int]] = set()
    for x in range(max(0, min_x), max_x + 1):
        for y in range(max(0, min_y), max_y + 1):
            center_x, center_y = Decimal(x) + half, Decimal(y) + half
            if any(
                _point_in_ring(center_x, center_y, polygon[0])
                and not any(_point_in_ring(center_x, center_y, hole) for hole in polygon[1:])
                for polygon in geometry.polygons
            ):
                pixels.add((x, y))
    return frozenset(pixels)


def _verify_reference_rasterization(
    split_path: Path,
    selected_images: list[str],
    references: Mapping[str, list[_Instance]],
) -> None:
    split_document = parse_strict_json(split_path.read_bytes())
    reference_manifest = (
        split_path.parent / split_document["reference_set"]["manifest_relative_path"]
    ).resolve()
    reference_document = parse_strict_json(reference_manifest.read_bytes())
    object_artifact = (
        reference_manifest.parent
        / reference_document["artifacts"]["nuclear_reference_objects"]["relative_path"]
    ).resolve()
    records = _load_jsonl(object_artifact)
    expected: dict[tuple[str, str], frozenset[tuple[int, int]]] = {}
    for index, record in enumerate(records):
        if record["image_id"] not in selected_images:
            continue
        geometry = _mapping(record.get("geometry"), f"reference_objects[{index}].geometry")
        expected[(record["image_id"], record["reference_object_id"])] = _rasterize_wkt(
            str(geometry.get("geometry_type")),
            str(geometry.get("wkt")),
            f"reference_objects[{index}].geometry",
        )
    actual = {
        (image_id, instance.object_id): instance.pixels
        for image_id, instances in references.items()
        for instance in instances
    }
    _require(
        set(actual) == set(expected),
        "reference raster identities do not exactly match frozen Phase 3 objects",
    )
    for key, pixels in expected.items():
        _require(
            actual[key] == pixels, f"reference raster pixels do not match frozen WKT for {key}"
        )


@dataclass(frozen=True, slots=True)
class _Instance:
    image_id: str
    object_id: str
    pixels: frozenset[tuple[int, int]]
    crowded: bool
    measurements: Mapping[str, float]


def _instances(records: list[Mapping[str, Any]], label: str) -> dict[str, list[_Instance]]:
    by_image: dict[str, list[_Instance]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    prior: tuple[str, str] | None = None
    for index, record in enumerate(records):
        location = f"{label}[{index}]"
        _require(
            set(record)
            == {"$schema", "image_id", "object_id", "pixels", "crowded", "measurements"},
            f"{location} fields are invalid",
        )
        _require(record.get("$schema") == INSTANCE_SCHEMA, f"{location} has unsupported schema")
        image_id = record.get("image_id")
        object_id = record.get("object_id")
        _require(isinstance(image_id, str) and image_id, f"{location}.image_id is required")
        _require(isinstance(object_id, str) and object_id, f"{location}.object_id is required")
        key = (image_id, object_id)
        _require(prior is None or key > prior, f"{label} must be image_id/object_id sorted")
        _require(key not in seen, f"duplicate {label} identity {key}")
        raw_measurements = record.get("measurements", [])
        _require(isinstance(raw_measurements, list), f"{location}.measurements must be an array")
        measurements: dict[str, float] = {}
        prior_measurement: str | None = None
        for measurement_index, raw_measurement in enumerate(raw_measurements):
            measurement = _mapping(raw_measurement, f"{location}.measurements[{measurement_index}]")
            _require(
                set(measurement) == {"measurement_id", "value"},
                f"{location}.measurements[{measurement_index}] fields are invalid",
            )
            name, value = measurement["measurement_id"], measurement["value"]
            _require(isinstance(name, str) and name, f"{location} measurement name is invalid")
            _require(
                prior_measurement is None or name > prior_measurement,
                f"{location}.measurements must be measurement_id sorted and unique",
            )
            _require(
                isinstance(value, (int, float)) and not isinstance(value, bool),
                f"{location}.measurements.{name} must be numeric",
            )
            measurements[name] = float(value)
            prior_measurement = name
        crowded = record.get("crowded", False)
        _require(isinstance(crowded, bool), f"{location}.crowded must be boolean")
        by_image[image_id].append(
            _Instance(image_id, object_id, _pixels(record, location), crowded, measurements)
        )
        seen.add(key)
        prior = key
    return dict(by_image)


def _iou(left: frozenset[tuple[int, int]], right: frozenset[tuple[int, int]]) -> float:
    return len(left & right) / len(left | right)


def _maximum_cardinality_matches(
    references: list[_Instance], predictions: list[_Instance], threshold: float
) -> list[tuple[int, int, float]]:
    """Hopcroft-Karp cardinality matching with deterministic IoU/index ordering."""
    scored = {
        i: sorted(
            ((j, _iou(ref.pixels, pred.pixels)) for j, pred in enumerate(predictions)),
            key=lambda item: (-item[1], predictions[item[0]].object_id),
        )
        for i, ref in enumerate(references)
    }
    adjacency = {
        i: [j for j, score in values if score >= threshold] for i, values in scored.items()
    }
    pair_u: dict[int, int | None] = {i: None for i in range(len(references))}
    pair_v: dict[int, int | None] = {j: None for j in range(len(predictions))}
    distance: dict[int, int] = {}

    def bfs() -> bool:
        queue: deque[int] = deque()
        found = False
        for u, value in pair_u.items():
            if value is None:
                distance[u] = 0
                queue.append(u)
            else:
                distance[u] = -1
        while queue:
            u = queue.popleft()
            for v in adjacency[u]:
                mate = pair_v[v]
                if mate is None:
                    found = True
                elif distance[mate] < 0:
                    distance[mate] = distance[u] + 1
                    queue.append(mate)
        return found

    def dfs(u: int) -> bool:
        for v in adjacency[u]:
            mate = pair_v[v]
            if mate is None or (distance.get(mate) == distance[u] + 1 and dfs(mate)):
                pair_u[u] = v
                pair_v[v] = u
                return True
        distance[u] = -1
        return False

    while bfs():
        for u, value in pair_u.items():
            if value is None:
                dfs(u)
    return [
        (u, v, _iou(references[u].pixels, predictions[v].pixels))
        for u, v in pair_u.items()
        if v is not None
    ]


def _boundary(pixels: frozenset[tuple[int, int]]) -> frozenset[tuple[int, int]]:
    return frozenset(
        (x, y)
        for x, y in pixels
        if any((x + dx, y + dy) not in pixels for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    )


def _within(
    boundary: frozenset[tuple[int, int]], target: frozenset[tuple[int, int]], tolerance: int
) -> int:
    return sum(
        any(
            (x + dx, y + dy) in target
            for dx in range(-tolerance, tolerance + 1)
            for dy in range(-tolerance, tolerance + 1)
        )
        for x, y in boundary
    )


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


@dataclass(frozen=True, slots=True)
class Phase4EvaluationReport:
    status: str
    evaluation_plan_id: str
    evaluation_plan_sha256: str
    split_manifest_sha256: str
    reference_set_sha256: str
    reference_instances_sha256: str
    prediction_instances_sha256: str
    image_count: int
    reference_count: int
    prediction_count: int
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float
    recall: float
    f1: float
    mean_matched_iou: float
    split_reference_count: int
    merge_prediction_count: int
    boundary_precision: float
    boundary_recall: float
    boundary_f1: float
    signed_count_error: int
    absolute_count_error: int
    per_object_matches: tuple[Mapping[str, Any], ...]
    per_image_counts: tuple[Mapping[str, Any], ...]
    size_strata: Mapping[str, Mapping[str, Any]]
    crowding_strata: Mapping[str, Mapping[str, Any]]
    measurement_bias: Mapping[str, Mapping[str, float | int]]
    acceptance_scope: str
    acceptance_passed: bool
    acceptance_checks: tuple[Mapping[str, Any], ...]
    authorization: str = "none"
    scientific_validation: bool = False
    biological_ground_truth: bool = False
    backend_equivalence: bool = False
    model_universality: bool = False
    validation_scope: str = (
        "deterministic engineering evaluation against supplied frozen pixel labels only"
    )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["per_object_matches"] = list(self.per_object_matches)
        value["per_image_counts"] = list(self.per_image_counts)
        value["acceptance_checks"] = list(self.acceptance_checks)
        return value


def _acceptance_checks(
    criteria: Mapping[str, Any],
    metrics: Mapping[str, float | int],
    measurement_bias: Mapping[str, Mapping[str, float | int]],
) -> tuple[Mapping[str, Any], ...]:
    rules = (
        ("minimum_evaluable_image_count", "image_count", ">="),
        ("minimum_reference_object_count", "reference_count", ">="),
        ("minimum_precision", "precision", ">="),
        ("minimum_recall", "recall", ">="),
        ("minimum_f1", "f1", ">="),
        ("minimum_boundary_f1", "boundary_f1", ">="),
        ("maximum_split_rate", "split_rate", "<="),
        ("maximum_merge_rate", "merge_rate", "<="),
        (
            "maximum_mean_absolute_count_error_per_image",
            "mean_absolute_count_error_per_image",
            "<=",
        ),
    )
    checks: list[Mapping[str, Any]] = []
    for criterion, metric, operator in rules:
        threshold = criteria.get(criterion)
        _require(
            isinstance(threshold, (int, float)) and not isinstance(threshold, bool),
            f"acceptance_criteria.{criterion} must be numeric",
        )
        observed = metrics[metric]
        passed = observed >= threshold if operator == ">=" else observed <= threshold
        checks.append(
            {
                "criterion": criterion,
                "metric": metric,
                "operator": operator,
                "threshold": threshold,
                "observed": observed,
                "passed": passed,
            }
        )
    measurement_limits = criteria.get("maximum_measurement_mae")
    _require(
        isinstance(measurement_limits, list) and measurement_limits,
        "acceptance_criteria.maximum_measurement_mae must be a nonempty array",
    )
    prior_name: str | None = None
    for index, raw_limit in enumerate(measurement_limits):
        limit = _mapping(raw_limit, f"acceptance_criteria.maximum_measurement_mae[{index}]")
        _require(
            set(limit) == {"measurement_id", "maximum_mae"},
            f"acceptance measurement limit {index} fields are invalid",
        )
        name, threshold = limit["measurement_id"], limit["maximum_mae"]
        _require(
            isinstance(name, str) and name, f"acceptance measurement limit {index} name is invalid"
        )
        _require(
            prior_name is None or name > prior_name,
            "acceptance measurement limits must be measurement_id sorted and unique",
        )
        _require(
            isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and threshold >= 0,
            f"acceptance measurement limit {name} must be nonnegative",
        )
        observed = measurement_bias.get(name, {}).get("mean_absolute_error")
        passed = isinstance(observed, (int, float)) and observed <= threshold
        checks.append(
            {
                "criterion": "maximum_measurement_mae",
                "metric": name,
                "operator": "<=",
                "threshold": threshold,
                "observed": observed,
                "passed": passed,
            }
        )
        prior_name = name
    return tuple(checks)


def evaluate_segmentation(
    plan_path: str | Path, predictions_path: str | Path
) -> Phase4EvaluationReport:
    plan_file = Path(plan_path).resolve()
    plan = _mapping(parse_strict_json(plan_file.read_bytes()), "plan")
    _require(set(plan) == _PLAN_FIELDS, "plan fields are invalid")
    _require(plan.get("$schema") == PLAN_SCHEMA, "plan has unsupported schema")
    _require(
        plan.get("contract_type") == "ifquant_platform_segmentation_evaluation_plan",
        "plan contract_type is invalid",
    )
    _require(plan.get("contract_version") == "1.0.0", "plan contract_version is invalid")
    _require(
        isinstance(plan.get("evaluation_plan_id"), str) and plan["evaluation_plan_id"],
        "plan evaluation_plan_id is required",
    )
    _require(plan.get("state") == "frozen", "plan.state must be frozen")
    _require(
        plan.get("backend_id") == "native_qupath", "Phase 4 plan backend_id must be native_qupath"
    )
    split_ref = _mapping(plan.get("split_manifest"), "plan.split_manifest")
    _require(
        set(split_ref) == {"relative_path", "sha256"}, "plan.split_manifest fields are invalid"
    )
    split_path = (plan_file.parent / str(split_ref.get("relative_path"))).resolve()
    split = validate_split_manifest(split_path)
    _require(
        split.split_manifest_sha256 == split_ref.get("sha256"), "split-manifest SHA-256 mismatch"
    )
    _require(
        split.reference_set_sha256 == plan.get("reference_set_sha256"),
        "reference-set SHA-256 mismatch",
    )
    artifact = _mapping(plan.get("reference_instances"), "plan.reference_instances")
    _require(
        set(artifact) == {"relative_path", "sha256"}, "plan.reference_instances fields are invalid"
    )
    reference_path = (plan_file.parent / str(artifact.get("relative_path"))).resolve()
    _require(
        file_sha256(reference_path) == artifact.get("sha256"),
        "reference-instance artifact SHA-256 mismatch",
    )
    predictions_file = Path(predictions_path).resolve()
    references = _instances(_load_jsonl(reference_path), "references")
    predictions = _instances(_load_jsonl(predictions_file), "predictions")
    assignments = parse_strict_json(split_path.read_bytes())["image_assignments"]
    allowed_partitions = plan.get("partitions")
    _require(
        isinstance(allowed_partitions, list) and allowed_partitions,
        "plan.partitions must be nonempty",
    )
    selected_images = sorted(
        item["image_id"] for item in assignments if item["partition"] in allowed_partitions
    )
    _require(
        set(references) == set(selected_images),
        "reference ledger must exactly cover selected images",
    )
    _verify_reference_rasterization(split_path, selected_images, references)
    _require(
        set(predictions).issubset(set(selected_images)),
        "prediction ledger contains an unselected image",
    )
    thresholds = _mapping(plan.get("thresholds"), "plan.thresholds")
    _require(
        set(thresholds)
        == {
            "match_iou",
            "split_merge_overlap_fraction",
            "boundary_tolerance_pixels",
            "size_strata_pixels",
        },
        "plan.thresholds fields are invalid",
    )
    match_iou = float(thresholds.get("match_iou"))
    overlap_fraction = float(thresholds.get("split_merge_overlap_fraction"))
    boundary_tolerance = thresholds.get("boundary_tolerance_pixels")
    _require(0 < match_iou <= 1, "match_iou must be in (0, 1]")
    _require(0 < overlap_fraction <= 1, "split_merge_overlap_fraction must be in (0, 1]")
    _require(
        isinstance(boundary_tolerance, int) and boundary_tolerance >= 0,
        "boundary tolerance must be nonnegative integer",
    )
    size_edges = thresholds.get("size_strata_pixels")
    _require(
        isinstance(size_edges, list) and len(size_edges) == 2 and 0 < size_edges[0] < size_edges[1],
        "size_strata_pixels must contain two increasing positive cut points",
    )

    matches_out: list[Mapping[str, Any]] = []
    per_image: list[Mapping[str, Any]] = []
    total_ref = total_pred = tp = splits = merges = 0
    boundary_hit_pred = boundary_total_pred = boundary_hit_ref = boundary_total_ref = 0
    stratum_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    crowd_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    measurement_errors: dict[str, list[float]] = defaultdict(list)
    matched_ious: list[float] = []
    for image_id in selected_images:
        refs = references.get(image_id, [])
        preds = predictions.get(image_id, [])
        matches = _maximum_cardinality_matches(refs, preds, match_iou)
        total_ref += len(refs)
        total_pred += len(preds)
        tp += len(matches)
        splits += sum(
            sum(
                len(ref.pixels & pred.pixels) / len(ref.pixels) >= overlap_fraction
                for pred in preds
            )
            >= 2
            for ref in refs
        )
        merges += sum(
            sum(
                len(ref.pixels & pred.pixels) / len(pred.pixels) >= overlap_fraction for ref in refs
            )
            >= 2
            for pred in preds
        )
        matched_ref = {i for i, _, _ in matches}
        for index, ref in enumerate(refs):
            stratum = (
                "small"
                if len(ref.pixels) < size_edges[0]
                else "medium"
                if len(ref.pixels) < size_edges[1]
                else "large"
            )
            stratum_counts[stratum][1] += 1
            stratum_counts[stratum][0] += index in matched_ref
            crowd = "crowded" if ref.crowded else "not_crowded"
            crowd_counts[crowd][1] += 1
            crowd_counts[crowd][0] += index in matched_ref
        for ref_index, pred_index, iou in matches:
            ref, pred = refs[ref_index], preds[pred_index]
            ref_boundary, pred_boundary = _boundary(ref.pixels), _boundary(pred.pixels)
            boundary_hit_pred += _within(pred_boundary, ref_boundary, boundary_tolerance)
            boundary_total_pred += len(pred_boundary)
            boundary_hit_ref += _within(ref_boundary, pred_boundary, boundary_tolerance)
            boundary_total_ref += len(ref_boundary)
            shared_measurements = sorted(set(ref.measurements) & set(pred.measurements))
            errors = {
                name: pred.measurements[name] - ref.measurements[name]
                for name in shared_measurements
            }
            for name, error in errors.items():
                measurement_errors[name].append(error)
            matches_out.append(
                {
                    "image_id": image_id,
                    "reference_object_id": ref.object_id,
                    "prediction_object_id": pred.object_id,
                    "iou": iou,
                    "signed_measurement_errors": errors,
                }
            )
            matched_ious.append(iou)
        per_image.append(
            {
                "image_id": image_id,
                "reference_count": len(refs),
                "prediction_count": len(preds),
                "signed_count_error": len(preds) - len(refs),
                "absolute_count_error": abs(len(preds) - len(refs)),
            }
        )

    fp, fn = total_pred - tp, total_ref - tp
    precision, recall = _ratio(tp, total_pred), _ratio(tp, total_ref)
    boundary_precision = _ratio(boundary_hit_pred, boundary_total_pred)
    boundary_recall = _ratio(boundary_hit_ref, boundary_total_ref)
    measurement_bias = {
        name: {
            "pair_count": len(errors),
            "mean_signed_error": sum(errors) / len(errors),
            "mean_absolute_error": sum(abs(error) for error in errors) / len(errors),
        }
        for name, errors in sorted(measurement_errors.items())
    }
    metrics = {
        "image_count": len(selected_images),
        "reference_count": total_ref,
        "precision": precision,
        "recall": recall,
        "f1": _ratio(2 * precision * recall, precision + recall),
        "boundary_f1": _ratio(
            2 * boundary_precision * boundary_recall, boundary_precision + boundary_recall
        ),
        "split_rate": _ratio(splits, total_ref),
        "merge_rate": _ratio(merges, total_pred),
        "mean_absolute_count_error_per_image": _ratio(
            sum(item["absolute_count_error"] for item in per_image), len(selected_images)
        ),
    }
    criteria = _mapping(plan.get("acceptance_criteria"), "plan.acceptance_criteria")
    _require(set(criteria) == _CRITERIA_FIELDS, "plan.acceptance_criteria fields are invalid")
    claims = _mapping(plan.get("claims"), "plan.claims")
    _require(
        claims
        == {
            "scientific_validation": False,
            "backend_equivalence": False,
            "model_universality": False,
            "authorization": "none",
        },
        "plan claims must retain all non-claims and authorization none",
    )
    scope = criteria.get("scope")
    _require(isinstance(scope, str) and scope, "acceptance_criteria.scope is required")
    acceptance_checks = _acceptance_checks(criteria, metrics, measurement_bias)
    return Phase4EvaluationReport(
        status="valid_engineering_evaluation",
        evaluation_plan_id=str(plan.get("evaluation_plan_id")),
        evaluation_plan_sha256=canonical_sha256(plan),
        split_manifest_sha256=split.split_manifest_sha256,
        reference_set_sha256=split.reference_set_sha256,
        reference_instances_sha256=file_sha256(reference_path),
        prediction_instances_sha256=file_sha256(predictions_file),
        image_count=len(selected_images),
        reference_count=total_ref,
        prediction_count=total_pred,
        true_positive_count=tp,
        false_positive_count=fp,
        false_negative_count=fn,
        precision=precision,
        recall=recall,
        f1=float(metrics["f1"]),
        mean_matched_iou=sum(matched_ious) / len(matched_ious) if matched_ious else 0.0,
        split_reference_count=splits,
        merge_prediction_count=merges,
        boundary_precision=boundary_precision,
        boundary_recall=boundary_recall,
        boundary_f1=float(metrics["boundary_f1"]),
        signed_count_error=total_pred - total_ref,
        absolute_count_error=sum(item["absolute_count_error"] for item in per_image),
        per_object_matches=tuple(matches_out),
        per_image_counts=tuple(per_image),
        size_strata={
            name: {
                "matched": values[0],
                "reference_count": values[1],
                "recall": _ratio(values[0], values[1]),
            }
            for name, values in sorted(stratum_counts.items())
        },
        crowding_strata={
            name: {
                "matched": values[0],
                "reference_count": values[1],
                "recall": _ratio(values[0], values[1]),
            }
            for name, values in sorted(crowd_counts.items())
        },
        measurement_bias=measurement_bias,
        acceptance_scope=scope,
        acceptance_passed=all(check["passed"] for check in acceptance_checks),
        acceptance_checks=acceptance_checks,
    )
