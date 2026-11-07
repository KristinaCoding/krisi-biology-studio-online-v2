"""Offline recovery tests for failed material uploads. No network or real database."""
import unittest
from unittest.mock import patch, call
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import materials_library

TEACHER = "11111111-1111-4111-8111-111111111111"
STUDENT = "22222222-2222-4222-8222-222222222222"

class Cursor:
    def __init__(self, db):
        self.db = db
        self.sql = ""
    def execute(self, sql, params=()):
        self.sql = sql
        if "INSERT INTO public.materials" in sql:
            if self.db.fail_insert:
                raise RuntimeError("Simulated PostgreSQL insert failure")
    def fetchone(self):
        if "SELECT 1 FROM public.teacher_students" in self.sql:
            return (1,)
        if "INSERT INTO public.materials" in self.sql:
            return (42,)
        return None
    def __enter__(self): return self
    def __exit__(self, *args): return False

class Connection:
    def __init__(self, fail_insert=False):
        self.fail_insert = fail_insert
    def cursor(self): return Cursor(self)
    def __enter__(self): return self
    def __exit__(self, *args): return False

def make_client():
    app = FastAPI()
    def require(req, role):
        if role != "teacher":
            raise HTTPException(403)
        return {"id": TEACHER, "role": "teacher"}
    materials_library.register(app, require, lambda title, body: body,
                               lambda req: "", lambda req, csrf: None, str)
    return TestClient(app, raise_server_exceptions=False)

def upload(client):
    return client.post("/materials", data={
        "title": "Recovery test", "student_id": STUDENT, "csrf": "test"
    }, files={"file": ("test.pdf", b"%PDF-1.4\nmock", "application/pdf")}, follow_redirects=False)

class UploadRecoveryTests(unittest.TestCase):
    def test_database_insert_failure_triggers_storage_cleanup(self):
        client = make_client()
        with patch.object(materials_library, "get_connection", side_effect=[
            Connection(), Connection(fail_insert=True)
        ]), patch.object(materials_library, "storage_config", return_value=(
            "https://example.supabase.co", "mock-only", "biology-private-materials"
        )), patch.object(materials_library, "storage_request", return_value=b"") as storage:
            response = upload(client)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(storage.call_count, 2)
        self.assertEqual(storage.call_args_list[0].args[0], "POST")
        self.assertEqual(storage.call_args_list[1].args[0], "DELETE")
        self.assertEqual(storage.call_args_list[0].args[1:3],
                         storage.call_args_list[1].args[1:3])

    def test_storage_upload_failure_does_not_insert_metadata(self):
        client = make_client()
        with patch.object(materials_library, "get_connection", side_effect=[
            Connection(), AssertionError("Metadata insert must not run")
        ]), patch.object(materials_library, "storage_config", return_value=(
            "https://example.supabase.co", "mock-only", "biology-private-materials"
        )), patch.object(materials_library, "storage_request",
                         side_effect=HTTPException(503, "Simulated storage outage")) as storage:
            response = upload(client)
        self.assertEqual(response.status_code, 503)
        storage.assert_called_once()
        self.assertEqual(storage.call_args.args[0], "POST")

if __name__ == "__main__":
    unittest.main()
