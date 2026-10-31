"""Checks against the running Compose API and its actual runtime SQL login."""

import json
import os
import sys
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg


BASE = "http://127.0.0.1:8000"


def request(path, data=None):
    body = None if data is None else json.dumps(data).encode()
    req = Request(BASE + path, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=8) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


class IntegrationTests(unittest.TestCase):
    def test_round_trip_and_parameter_binding(self):
        text = "Robert'); DROP TABLE public.messages; -- " + str(uuid4())
        status, saved = request("/api/messages", {"text": text})
        self.assertEqual(status, 201)
        self.assertEqual(saved["text"], text)
        self.assertTrue(saved["created_at"])
        self.assertEqual(request("/api/messages/" + saved["id"]), (200, saved))

    def test_validation_and_missing_record(self):
        for text in ["", "   ", "x" * 501]:
            self.assertEqual(request("/api/messages", {"text": text})[0], 422)
        self.assertEqual(request("/api/messages/not-a-uuid")[0], 422)
        self.assertEqual(request("/api/messages/" + str(uuid4()))[0], 404)

    def test_runtime_permissions(self):
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
            row = connection.execute("""
                SELECT current_user = 'app_runtime',
                       NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb,
                       NOT has_database_privilege(current_user, current_database(), 'CREATE'),
                       NOT has_schema_privilege(current_user, 'public', 'CREATE')
                FROM pg_roles WHERE rolname = current_user
            """).fetchone()
            self.assertEqual(row, (True, True, True, True))
            for sql in [
                "CREATE TABLE public.forbidden (id integer)",
                "CREATE ROLE forbidden_role",
                "ALTER TABLE public.messages ADD COLUMN forbidden integer",
                "DELETE FROM public.messages",
                "SELECT * FROM atlas.atlas_schema_revisions",
            ]:
                with self.assertRaises(psycopg.errors.InsufficientPrivilege, msg=sql):
                    connection.execute(sql)
            with self.assertRaises(psycopg.errors.CheckViolation):
                connection.execute(
                    "INSERT INTO public.messages (id, text) VALUES (%s, %s)",
                    (uuid4(), "   "),
                )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "test"
    if mode == "seed":
        status, saved = request("/api/messages", {"text": "Seed retained across repeat migration and restart"})
        assert status == 201, (status, saved)
        print(saved["id"])
    elif mode == "verify":
        status, saved = request("/api/messages/" + sys.argv[2])
        assert status == 200 and saved["text"] == "Seed retained across repeat migration and restart"
        print("Seed preserved")
    elif mode == "unavailable":
        assert request("/api/healthz") == (200, {"status": "ok"})
        for path, body in [
            ("/api/readyz", None),
            ("/api/messages/" + str(uuid4()), None),
            ("/api/messages", {"text": "DB unavailable"}),
        ]:
            assert request(path, body) == (503, {"detail": "Database unavailable"})
        print("Database outage handled; process remains healthy")
    else:
        unittest.main(argv=[sys.argv[0]])
