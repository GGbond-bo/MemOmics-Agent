"""Bioinformatics input, workflow, QC and reference-registry API."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from webui.bioinformatics import QCGate, WorkflowStep, inspect_input, validate_workflow
from webui.security import UnsafePathError, resolve_within_roots


class InputRequest(BaseModel):
    path: str


class WorkflowStepRequest(BaseModel):
    id: str
    operation: str
    depends_on: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    qc_gates: list[str] = Field(default_factory=list)


class WorkflowRequest(BaseModel):
    steps: list[WorkflowStepRequest]


class QCRequest(BaseModel):
    metrics: dict
    gates: list[dict]


class ReferenceRequest(BaseModel):
    name: str
    kind: str
    path: str
    version: str = ""
    organism: str = ""


def create_bioinformatics_router(registry, allowed_roots) -> APIRouter:
    router = APIRouter(prefix="/api/bioinformatics", tags=["bioinformatics"])

    @router.post("/inputs/inspect")
    async def inspect_analysis_input(request: InputRequest):
        try:
            path = resolve_within_roots(request.path, allowed_roots)
            return inspect_input(path)
        except (UnsafePathError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @router.post("/workflows/validate")
    async def validate_analysis_workflow(request: WorkflowRequest):
        return validate_workflow([
            WorkflowStep(
                id=item.id, operation=item.operation,
                depends_on=tuple(item.depends_on), inputs=tuple(item.inputs),
                outputs=tuple(item.outputs), qc_gates=tuple(item.qc_gates),
            ) for item in request.steps
        ])

    @router.post("/qc/evaluate")
    async def evaluate_qc(request: QCRequest):
        try:
            results = [QCGate(**item).evaluate(request.metrics) for item in request.gates]
            return {"passed": all(item["passed"] for item in results), "gates": results}
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @router.get("/references")
    async def list_references():
        return {"references": registry.list()}

    @router.post("/references")
    async def register_reference(request: ReferenceRequest):
        try:
            return {"reference": registry.register(**request.model_dump())}
        except (UnsafePathError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @router.delete("/references/{name}")
    async def remove_reference(name: str):
        if not registry.remove(name):
            return JSONResponse({"error": "Reference not found"}, status_code=404)
        return {"removed": name}

    return router
