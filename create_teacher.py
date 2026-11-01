import getpass, sqlite3
from portal import DB, hashpw
email=input("Teacher email: ").strip().lower()
name=input("Display name: ").strip()
password=getpass.getpass("Password (14+ characters): ")
if len(password)<14: raise SystemExit("Password too short")
with sqlite3.connect(DB) as c:
    if c.execute("SELECT COUNT(*) FROM users WHERE role='teacher'").fetchone()[0]: raise SystemExit("Teacher already exists")
    c.execute("INSERT INTO users(email,display,role,passhash) VALUES(?,?,'teacher',?)",(email,name,hashpw(password)))
print("Teacher account created. Start the portal and sign in.")
