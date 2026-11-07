"""Offline authorization regression tests; no database or Supabase credentials needed."""
import unittest
from unittest.mock import patch
from uuid import UUID
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import materials_library

TEACHER = str(UUID("11111111-1111-4111-8111-111111111111"))
STUDENT = str(UUID("22222222-2222-4222-8222-222222222222"))
OTHER = str(UUID("33333333-3333-4333-8333-333333333333"))

class FakeCursor:
    def __init__(self, permitted):
        self.permitted = permitted
        self.sql = ""
        self.params = ()
    def execute(self, sql, params=()):
        self.sql, self.params = sql, params
    def fetchone(self):
        # Model an authorized record only if the SQL scopes by both assignment and viewer.
        if ("teacher_students" in self.sql and "m.id=%s" in self.sql
                and "m.teacher_id=%s" in self.sql and "m.student_id=%s" in self.sql
                and self.permitted):
            return ("sample.txt", "biology-private-materials", "integration-tests/sample.txt")
        return None
    def __enter__(self): return self
    def __exit__(self, *args): return False

class FakeConnection:
    def __init__(self, permitted): self.permitted = permitted
    def cursor(self): return FakeCursor(self.permitted)
    def __enter__(self): return self
    def __exit__(self, *args): return False

class MaterialsAuthorizationTests(unittest.TestCase):
    def make_client(self, role, uid, permitted):
        app = FastAPI()
        def require(req, expected):
            if role != expected: raise HTTPException(403)
            return {"id": uid, "role": role}
        materials_library.register(app, require, lambda title, body: body,
                                   lambda req: "", lambda req, csrf: None, str)
        return TestClient(app, raise_server_exceptions=True)

    def test_unassigned_teacher_cannot_download(self):
        client = self.make_client("teacher", TEACHER, False)
        with patch.object(materials_library, "get_connection", return_value=FakeConnection(False)), \
             patch.object(materials_library, "storage_request") as storage, \
             patch("auth_service.get_user_role", return_value="teacher"):
            # Mock session access without requiring a live Supabase session.
            from starlette.requests import Request
            with patch.object(Request, "session", new_callable=lambda: property(lambda self: {"supabase_user_id": TEACHER})):
                response = client.get("/materials/42/download")
            self.assertEqual(response.status_code, 404)
            storage.assert_not_called()

    def test_unassigned_student_cannot_download(self):
        client = self.make_client("student", OTHER, False)
        with patch.object(materials_library, "get_connection", return_value=FakeConnection(False)), \
             patch.object(materials_library, "storage_request") as storage, \
             patch("auth_service.get_user_role", return_value="student"):
            from starlette.requests import Request
            with patch.object(Request, "session", new_callable=lambda: property(lambda self: {"supabase_user_id": OTHER})):
                response = client.get("/materials/42/download")
            self.assertEqual(response.status_code, 404)
            storage.assert_not_called()

    def test_authorized_student_download(self):
        client = self.make_client("student", STUDENT, True)
        with patch.object(materials_library, "get_connection", return_value=FakeConnection(True)), \
             patch.object(materials_library, "storage_request", return_value=b"sample") as storage, \
             patch("auth_service.get_user_role", return_value="student"):
            from starlette.requests import Request
            with patch.object(Request, "session", new_callable=lambda: property(lambda self: {"supabase_user_id": STUDENT})):
                response = client.get("/materials/42/download")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"sample")
            storage.assert_called_once()

if __name__ == "__main__":
    unittest.main()
