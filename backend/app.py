"""Small PostgreSQL-backed API used by the delivery proof of concept."""

from datetime import datetime
import os
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from azure.core.exceptions import AzureError
from azure.identity import WorkloadIdentityCredential
import psycopg
from psycopg.rows import dict_row


app = FastAPI(title="Preview API")
DATABASE_URL = os.environ["DATABASE_URL"]
DATABASE_AUTH = os.environ.get("DATABASE_AUTH", "password")
DATABASE_CREDENTIAL = WorkloadIdentityCredential() if DATABASE_AUTH == "entra" else None
DATABASE_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def connect():
    credentials = {}
    if DATABASE_CREDENTIAL:
        # A new token is requested for each connection; the SDK caches it until
        # renewal is needed. No database password is stored in the release.
        credentials["password"] = DATABASE_CREDENTIAL.get_token(DATABASE_SCOPE).token
    return psycopg.connect(
        DATABASE_URL,
        **credentials,
        connect_timeout=3,
        options="-c statement_timeout=3000 -c lock_timeout=2000",
        row_factory=dict_row,
    )


class NewMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    text: str = Field(min_length=1, max_length=500)


class Message(NewMessage):
    id: UUID
    created_at: datetime


@app.exception_handler(psycopg.Error)
@app.exception_handler(AzureError)
def database_error(request, exc):
    # Connection errors can contain connection details. Do not return or log them.
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    # Keep liveness independent of the database readiness check.
    return {"status": "ok"}


@app.get("/api/readyz")
def readyz() -> dict[str, str]:
    # Readiness confirms the shared schema before a candidate can receive traffic.
    with connect() as connection:
        connection.execute("SELECT id, text, created_at FROM public.messages LIMIT 0")
    return {"status": "ready"}


@app.post("/api/messages", response_model=Message, status_code=201)
def create_message(body: NewMessage):
    with connect() as connection:
        return connection.execute(
            "INSERT INTO public.messages (id, text) VALUES (%s, %s) "
            "RETURNING id, text, created_at",
            (uuid4(), body.text),
        ).fetchone()


@app.get("/api/messages/{message_id}", response_model=Message)
def get_message(message_id: UUID):
    with connect() as connection:
        message = connection.execute(
            "SELECT id, text, created_at FROM public.messages WHERE id = %s",
            (message_id,),
        ).fetchone()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return message
