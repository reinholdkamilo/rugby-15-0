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
        "https://rugby-15-0.vercel.app",
        "https://rugby-15-0-84be.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
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
