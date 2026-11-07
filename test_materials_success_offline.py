"""Offline success-path checks for material upload and deletion."""
import unittest
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import materials_library

TEACHER = "11111111-1111-4111-8111-111111111111"
STUDENT = "22222222-2222-4222-8222-222222222222"
BUCKET = "biology-private-materials"

class FakeDB:
    def __init__(self):
        self.statements = []
        self.committed = False
    def cursor(self):
        return self
    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        self.last_sql = sql
    def fetchone(self):
        if "SELECT 1 FROM public.teacher_students" in self.last_sql:
            return (1,)
        if "INSERT INTO public.materials" in self.last_sql:
            return (42,)
        if "FOR UPDATE" in self.last_sql:
            return (BUCKET, "teacher/student/example.pdf")
        return None
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        self.committed = exc_type is None
        return False

def client():
    app = FastAPI()
    def require(req, role):
        if role != "teacher":
            raise HTTPException(403)
        return {"id": TEACHER, "role": "teacher"}
    materials_library.register(app, require, lambda title, body: body,
                               lambda req: "", lambda req, csrf: None, str)
    return TestClient(app)

class MaterialSuccessTests(unittest.TestCase):
    def test_successful_upload_writes_storage_and_metadata(self):
        c = client()
        authorization_db = FakeDB()
        metadata_db = FakeDB()
        with patch.object(materials_library, "get_connection",
                          side_effect=[authorization_db, metadata_db]), \
             patch.object(materials_library, "storage_config",
                          return_value=("https://example.supabase.co", "mock-key", BUCKET)), \
             patch.object(materials_library, "storage_request", return_value=b"") as storage:
            response = c.post("/materials", data={
                "title": "Biology notes", "student_id": STUDENT, "csrf": "mock"
            }, files={"file": ("notes.pdf", b"%PDF-1.4\nmock content", "application/pdf")},
                follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/materials")
        storage.assert_called_once()
        self.assertEqual(storage.call_args.args[0], "POST")
        self.assertEqual(storage.call_args.args[1], BUCKET)
        self.assertEqual(storage.call_args.args[3], b"%PDF-1.4\nmock content")
        self.assertTrue(any("INSERT INTO public.materials" in sql
                            for sql, _ in metadata_db.statements))
        self.assertTrue(metadata_db.committed)

    def test_successful_delete_removes_storage_and_metadata(self):
        c = client()
        db = FakeDB()
        with patch.object(materials_library, "get_connection", return_value=db), \
             patch.object(materials_library, "storage_request", return_value=b"") as storage:
            response = c.post("/materials/42/delete", data={"csrf": "mock"},
                              follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/materials")
        storage.assert_called_once_with("DELETE", BUCKET, "teacher/student/example.pdf")
        self.assertTrue(any("DELETE FROM public.materials" in sql
                            for sql, _ in db.statements))
        self.assertTrue(db.committed)

if __name__ == "__main__":
    unittest.main()
