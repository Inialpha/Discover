from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..deps import owned_analysis
from ..models import Analysis
from ..services import exports as ex
from ..services.views import merged_result

router = APIRouter(prefix="/api/analyses", tags=["exports"])

TYPES = {"pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "json": "application/json", "md": "text/markdown"}


@router.get("/{analysis_id}/export")
def export(format: str = Query("pptx", pattern="^(pptx|docx|json|md)$"), a: Analysis = Depends(owned_analysis)) -> Response:
    if a.status != "complete" or not a.result:
        raise HTTPException(409, "The analysis is not finished yet")
    res = merged_result(a)
    if format == "pptx":
        body = ex.build_pptx(a.intake, res)
    elif format == "docx":
        body = ex.build_docx(a.intake, res)
    elif format == "md":
        body = (a.report_md or "").encode("utf-8")
    else:
        body = json.dumps({"intake": a.intake, "result": res}, indent=2, ensure_ascii=False).encode("utf-8")
    name = re.sub(r"[^A-Za-z0-9]+", "-", a.intake.get("name", "personas")).strip("-").lower() or "personas"
    return Response(body, media_type=TYPES[format], headers={"Content-Disposition": f'attachment; filename="{name}-personas.{format}"'})
