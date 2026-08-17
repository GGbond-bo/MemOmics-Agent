"""Typed, dependency-free contracts for bioinformatics analysis workflows."""

from __future__ import annotations

import gzip
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


_FORMATS = {
    ".h5ad": ("anndata", "single_cell"),
    ".h5": ("hdf5", "single_cell"),
    ".loom": ("loom", "single_cell"),
    ".rds": ("rds", "single_cell"),
    ".fastq": ("fastq", "sequencing"),
    ".fq": ("fastq", "sequencing"),
    ".bam": ("bam", "alignment"),
    ".cram": ("cram", "alignment"),
    ".vcf": ("vcf", "variants"),
    ".csv": ("csv", "table"),
    ".tsv": ("tsv", "table"),
}


def inspect_input(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.exists():
        return {"valid": False, "path": str(candidate), "errors": ["Input does not exist"]}
    if candidate.is_dir():
        try:
            names = {item.name.lower() for item in candidate.iterdir()}
        except OSError as exc:
            return {"valid": False, "path": str(candidate), "errors": [f"Input directory is not readable: {exc}"]}
        matrix = any(name in names for name in ("matrix.mtx", "matrix.mtx.gz"))
        barcodes = any(name in names for name in ("barcodes.tsv", "barcodes.tsv.gz"))
        features = any(name in names for name in ("features.tsv", "features.tsv.gz", "genes.tsv", "genes.tsv.gz"))
        missing = [label for label, found in (("matrix", matrix), ("barcodes", barcodes), ("features", features)) if not found]
        return {
            "valid": not missing,
            "path": str(candidate.resolve()),
            "format": "10x_mtx_directory",
            "modality": "single_cell",
            "errors": [f"Missing 10x component: {item}" for item in missing],
        }
    suffixes = [value.lower() for value in candidate.suffixes]
    compressed = suffixes[-1:] == [".gz"]
    data_suffix = suffixes[-2] if compressed and len(suffixes) > 1 else (suffixes[-1] if suffixes else "")
    format_name, modality = _FORMATS.get(data_suffix, ("unknown", "unknown"))
    errors = []
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        size = 0
        errors.append(f"Input is not stat-able: {exc}")
    if size == 0:
        errors.append("Input is empty")
    try:
        magic = candidate.read_bytes()[:8]
    except OSError as exc:
        magic = b""
        errors.append(f"Input is not readable: {exc}")
    if compressed and not magic.startswith(b"\x1f\x8b"):
        errors.append("File extension is .gz but gzip magic bytes are missing")
    if data_suffix in (".h5", ".h5ad") and magic != b"\x89HDF\r\n\x1a\n":
        errors.append("HDF5 magic bytes are missing")
    return {
        "valid": not errors and format_name != "unknown",
        "path": str(candidate.resolve()),
        "format": format_name + (".gz" if compressed else ""),
        "modality": modality,
        "size_bytes": size,
        "errors": errors + (["Unsupported input format"] if format_name == "unknown" else []),
    }


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    operation: str
    depends_on: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    qc_gates: tuple[str, ...] = ()


def validate_workflow(steps: list[WorkflowStep]) -> dict[str, Any]:
    errors: list[str] = []
    ids = [step.id for step in steps]
    if any(not item or not item.replace("-", "_").isalnum() for item in ids):
        errors.append("Step ids must be non-empty alphanumeric identifiers")
    if len(ids) != len(set(ids)):
        errors.append("Workflow step ids must be unique")
    known = set(ids)
    for step in steps:
        missing = sorted(set(step.depends_on) - known)
        if missing:
            errors.append(f"Step {step.id} has missing dependencies: {', '.join(missing)}")
        if step.id in step.depends_on:
            errors.append(f"Step {step.id} depends on itself")
    owners: dict[str, str] = {}
    for step in steps:
        for output in step.outputs:
            if output in owners:
                errors.append(f"Output {output} is produced by both {owners[output]} and {step.id}")
            owners[output] = step.id

    visiting: set[str] = set()
    visited: set[str] = set()
    by_id = {step.id: step for step in steps}

    def visit(step_id: str) -> None:
        if step_id in visiting:
            errors.append(f"Workflow contains a cycle at {step_id}")
            return
        if step_id in visited or step_id not in by_id:
            return
        visiting.add(step_id)
        for dependency in by_id[step_id].depends_on:
            visit(dependency)
        visiting.remove(step_id)
        visited.add(step_id)

    for step_id in ids:
        visit(step_id)
    return {"valid": not errors, "errors": list(dict.fromkeys(errors)), "steps": [asdict(step) for step in steps]}


@dataclass(frozen=True)
class QCGate:
    metric: str
    operator: str
    threshold: float
    required: bool = True

    def evaluate(self, metrics: dict[str, Any]) -> dict[str, Any]:
        value = metrics.get(self.metric)
        if not isinstance(value, (int, float)):
            return {"passed": not self.required, "metric": self.metric, "value": value, "reason": "metric_missing"}
        comparators = {
            ">=": lambda a, b: a >= b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: a == b,
        }
        if self.operator not in comparators:
            raise ValueError(f"Unsupported QC operator: {self.operator}")
        passed = comparators[self.operator](float(value), self.threshold)
        return {"passed": passed, "metric": self.metric, "value": value, "operator": self.operator, "threshold": self.threshold}
