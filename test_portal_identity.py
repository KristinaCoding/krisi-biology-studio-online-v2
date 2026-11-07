"""Offline regression tests for Supabase-to-portal identity mapping.

Run: PORTAL_SECRET=local-test-secret-at-least-32-characters python -m unittest discover -p 'test_portal_identity.py'
Requires the packages in requirements.txt; no live Supabase connection is made.
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

os.environ.setdefault("PORTAL_SECRET", "local-test-secret-at-least-32-characters")
import portal


class PortalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "portal.db"
        self.db_patch = patch.object(portal, "DB", self.db)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        with portal.conn() as c:
            c.execute("""CREATE TABLE users (
                id INTEGER PRIMARY KEY, email TEXT UNIQUE,
                display TEXT, role TEXT, passhash TEXT,
                supabase_user_id TEXT UNIQUE
            )""")

    def identity(self, user_id="supabase-1", email="Student@Example.com", role="student"):
        return {"supabase_user_id": user_id, "email": email, "role": role}

    def test_first_login_creates_account(self):
        uid = portal.find_or_create_portal_user(self.identity())
        with portal.conn() as c:
            user = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        self.assertEqual(user["email"], "student@example.com")
        self.assertEqual(user["supabase_user_id"], "supabase-1")
        self.assertEqual(user["role"], "student")

    def test_repeat_login_reuses_account(self):
        first = portal.find_or_create_portal_user(self.identity())
        second = portal.find_or_create_portal_user(self.identity())
        self.assertEqual(first, second)

    def test_role_change_is_rejected(self):
        portal.find_or_create_portal_user(self.identity())
        with self.assertRaises(HTTPException) as caught:
            portal.find_or_create_portal_user(self.identity(role="teacher"))
        self.assertEqual(caught.exception.status_code, 403)

    def test_email_collision_does_not_claim_account(self):
        portal.find_or_create_portal_user(self.identity())
        with self.assertRaises(HTTPException) as caught:
            portal.find_or_create_portal_user(self.identity(user_id="supabase-2"))
        self.assertEqual(caught.exception.status_code, 403)

    def test_missing_identity_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            portal.find_or_create_portal_user(self.identity(user_id=""))
        self.assertEqual(caught.exception.status_code, 403)

    def test_unsupported_role_is_rejected(self):
        with self.assertRaises(HTTPException) as caught:
            portal.find_or_create_portal_user(self.identity(role="admin"))
        self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
