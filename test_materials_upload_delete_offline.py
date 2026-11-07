"""Offline upload/delete authorization checks. No Supabase calls or real DB access."""
import unittest
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import materials_library

TEACHER = "11111111-1111-4111-8111-111111111111"
STUDENT = "22222222-2222-4222-8222-222222222222"

class Cursor:
    def __init__(self, assigned=False):
        self.assigned = assigned
    def execute(self, sql, params=()):
        self.sql, self.params = sql, params
    def fetchone(self):
        if "SELECT 1 FROM public.teacher_students" in self.sql:
            return (1,) if self.assigned else None
        if "FOR UPDATE" in self.sql:
            return ("biology-private-materials", "sample/path.pdf") if self.assigned else None
        return None
    def __enter__(self): return self
    def __exit__(self, *args): return False

class Connection:
    def __init__(self, assigned=False): self.assigned = assigned
    def cursor(self): return Cursor(self.assigned)
    def __enter__(self): return self
    def __exit__(self, *args): return False

def client_for(role):
    app = FastAPI()
    def require(req, expected):
        if role != expected:
            raise HTTPException(403, "Forbidden")
        return {"id": TEACHER if role == "teacher" else STUDENT, "role": role}
    materials_library.register(app, require, lambda title, body: body,
                               lambda req: "", lambda req, csrf: None, str)
    return TestClient(app)

class UploadDeleteAuthorizationTests(unittest.TestCase):
    def upload(self, client):
        return client.post("/materials", data={
            "title": "Test", "student_id": STUDENT, "csrf": "test"
        }, files={"file": ("sample.pdf", b"%PDF-1.4\nmock", "application/pdf")})

    def test_unassigned_teacher_upload_is_denied_before_storage(self):
        client = client_for("teacher")
        with patch.object(materials_library, "get_connection", return_value=Connection(False)), \
             patch.object(materials_library, "storage_request") as storage:
            response = self.upload(client)
        self.assertEqual(response.status_code, 403)
        storage.assert_not_called()

    def test_student_upload_is_denied_before_storage(self):
        client = client_for("student")
        with patch.object(materials_library, "get_connection") as db, \
             patch.object(materials_library, "storage_request") as storage:
            response = self.upload(client)
        self.assertEqual(response.status_code, 403)
        db.assert_not_called()
        storage.assert_not_called()

    def test_student_delete_is_denied_before_storage(self):
        client = client_for("student")
        with patch.object(materials_library, "get_connection") as db, \
             patch.object(materials_library, "storage_request") as storage:
            response = client.post("/materials/42/delete", data={"csrf": "test"})
        self.assertEqual(response.status_code, 403)
        db.assert_not_called()
        storage.assert_not_called()

    def test_unassigned_teacher_delete_is_denied_before_storage(self):
        client = client_for("teacher")
        with patch.object(materials_library, "get_connection", return_value=Connection(False)), \
             patch.object(materials_library, "storage_request") as storage:
            response = client.post("/materials/42/delete", data={"csrf": "test"})
        self.assertEqual(response.status_code, 404)
        storage.assert_not_called()

if __name__ == "__main__":
    unittest.main()
