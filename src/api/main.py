from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .routers import sql, files

app = FastAPI(title="DB-mini")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(sql.router, prefix="/api", tags=["sql"])
app.include_router(files.router, prefix="/api", tags=["files"])

app.mount("/", StaticFiles(directory="frontend/static", html=True), name="static")