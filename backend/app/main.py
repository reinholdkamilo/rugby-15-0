from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router
from .startup import initialise_database_on_startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialise_database_on_startup()
    yield


app = FastAPI(title="Rugby 15-0 API", lifespan=lifespan)
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
