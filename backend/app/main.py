from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .importers.schema_utils import ensure_database_schema
from .routes import router

ensure_database_schema()

app = FastAPI(title="Rugby 15-0 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root():
    return {"message": "Rugby 15-0 API running"}


@app.get("/health")
def health():
    return {"status": "ok"}
