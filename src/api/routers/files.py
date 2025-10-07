from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from ..schemas import UploadResponse
from ...app.engine import get_engine

router = APIRouter()

@router.post("/upload", response_model=UploadResponse)
async def upload_csv(
    table: str = Form(...),
    has_header: bool = Form(True),
    file: UploadFile = File(...)
):
    try:
        content = await file.read()
        rows_loaded = get_engine().load_csv_bytes(table, content, has_header=has_header)
        return UploadResponse(ok=True, table=table, rows_loaded=rows_loaded)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
