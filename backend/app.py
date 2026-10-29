"""Small API used by the delivery proof of concept."""

from fastapi import FastAPI


app = FastAPI(title="Preview API")


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/message")
def message() -> dict[str, str]:
    return {"message": "Hello from the Python API"}
