"""Static safety checks for the staged PostgreSQL biology activities module.

Run: python -m unittest test_v3_postgres_integration.py
Does not connect to or modify Supabase.
"""
import ast
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parent

class BiologyActivityIntegrationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module=(ROOT/"biology_activities.py").read_text(encoding="utf-8")
        cls.portal=(ROOT/"portal.py").read_text(encoding="utf-8")
        cls.migration=(ROOT/"migrations/20261107_v3_biology_activities.sql").read_text(encoding="utf-8")

    def test_syntax(self):
        ast.parse(self.module)
        ast.parse(self.portal)

    def test_postgres_connection_and_json(self):
        self.assertIn("from database import get_connection",self.module)
        self.assertIn("Jsonb(",self.module)
        self.assertNotIn("sqlite3",self.module)

    def test_membership_filter(self):
        self.assertIn("public.teacher_students",self.module)
        self.assertIn("ts.teacher_id=%s AND ts.student_id=%s",self.module)

    def test_session_authorization(self):
        self.assertIn("viewer=require(req,role)",self.module)
        self.assertIn("verifycsrf(req",self.module)

    def test_routes_registered(self):
        self.assertIn("register_biology_activities(app, require, page, token, verifycsrf, E)",self.portal)

    def test_additive_migration(self):
        self.assertIn("CREATE TABLE IF NOT EXISTS",self.migration)
        for forbidden in ("DROP TABLE","TRUNCATE","DELETE FROM","ALTER TABLE"):
            self.assertNotIn(forbidden,self.migration.upper())

if __name__=="__main__":
    unittest.main()
