from pydantic import BaseModel
from typing import Any, List, Optional, Dict

class SQLRequest(BaseModel):
    sql: str

class SQLResponse(BaseModel):
    ok: bool = True
    rows: Optional[List[List[Any]]] = None
    columns: Optional[List[str]] = None
    deleted: Optional[int] = None
    message: Optional[str] = None

class UploadResponse(BaseModel):
    ok: bool
    table: str
    rows_loaded: int

class UploadParams(BaseModel):
    table: str
    has_header: bool = True