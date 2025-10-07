# src/app/main.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import os

from ..parser.sql_parser import parser as lark_parser
from ..parser.sql_transformer import SQLTransformer
from .engine import get_engine

app = FastAPI(title="MiniDB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

# ✅ monta archivos estáticos en /static (css/js si los hubiera)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ✅ sirve el index.html en la raíz sin romper /api/*
@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

class SQLPayload(BaseModel):
    query: str

@app.post("/api/sql")
async def run_sql(payload: SQLPayload):
    q = payload.query.strip()
    if not q.endswith(";"):
        raise HTTPException(400, "La consulta debe terminar en ';'")
    try:
        tree = lark_parser.parse(q)
        stmt = SQLTransformer().transform(tree)
        res = get_engine().execute(stmt)
        return res
    except Exception as e:
        raise HTTPException(400, f"Error al procesar SQL: {e}")

@app.post("/api/upload")
async def upload_csv(table: str = Form(...), file: UploadFile = File(...), has_header: bool = Form(True)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Solo se aceptan CSV")
    content = await file.read()
    try:
        inserted = get_engine().load_csv_bytes(table, content, has_header=has_header)
        return {"ok": True, "inserted": inserted}
    except Exception as e:
        raise HTTPException(400, f"Error al cargar CSV: {e}")

@app.get("/api/tables")
async def list_tables():
    data_dir = get_engine().data_dir
    names = [fn[:-5] for fn in os.listdir(data_dir) if fn.endswith(".meta")]
    return {"tables": sorted(names)}

@app.get("/api/tables/{name}/schema")
async def table_schema(name: str):
    try:
        t = get_engine()._get_table(name)
        return {"table": name, "schema": t.schema, "indexes": getattr(t, "index_specs", [])}
    except Exception as e:
        raise HTTPException(404, str(e))