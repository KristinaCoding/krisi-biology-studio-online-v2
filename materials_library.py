"""Private materials: PostgreSQL metadata and durable Supabase Storage objects."""
import os
import secrets
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError, URLError
from uuid import UUID
from fastapi import Request, Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse, Response
from database import get_connection

MAX_BYTES=10*1024*1024
ALLOWED={".pdf":"application/pdf",".png":"image/png",".jpg":"image/jpeg",
         ".jpeg":"image/jpeg",".pptx":"application/vnd.openxmlformats-officedocument.presentationml.presentation",
         ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def storage_config():
    base=os.environ.get("SUPABASE_URL","").rstrip("/")
    key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
    bucket=os.environ.get("BIOLOGY_MATERIALS_BUCKET","biology-private-materials")
    if not base.startswith("https://") or not key or not bucket:
        raise HTTPException(503,"Private Supabase Storage is not configured")
    return base,key,bucket


def storage_request(method,bucket,path,data=None,mime=None):
    base,key,_=storage_config()
    url=f"{base}/storage/v1/object/{quote(bucket,safe='')}/{quote(path,safe='/')}"
    headers={"apikey":key,"Authorization":"Bearer "+key}
    if mime:
        headers["Content-Type"]=mime
    request=URLRequest(url,data=data,headers=headers,method=method)
    try:
        with urlopen(request,timeout=30) as response:
            result=response.read(MAX_BYTES+1)
            if len(result)>MAX_BYTES and method=="GET":
                raise HTTPException(413,"Stored file exceeds maximum size")
            return result
    except HTTPError as exc:
        if exc.code==404:
            raise HTTPException(404,"Stored material not found")
        raise HTTPException(502,"Storage service error")
    except (URLError,TimeoutError):
        raise HTTPException(503,"Storage service unavailable")


def register(app,require,page,token,verifycsrf,E):
    def viewer(req):
        from auth_service import get_user_role
        try:
            uid=str(UUID(str(req.session.get("supabase_user_id"))))
        except (TypeError,ValueError):
            raise HTTPException(401,"Sign in required")
        role=get_user_role(uid)
        if role not in ("teacher","student"):
            raise HTTPException(403,"Access denied")
        return require(req,role)

    @app.get("/materials")
    def teacher_materials(req:Request):
        teacher=require(req,"teacher")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT s.id,s.display_name FROM public.student_profiles s
                JOIN public.teacher_students ts ON ts.student_id=s.id
                WHERE ts.teacher_id=%s ORDER BY s.display_name""",(teacher["id"],))
            students=cur.fetchall()
            cur.execute("""SELECT m.id,m.title,m.original_name,s.display_name
                FROM public.materials m
                JOIN public.teacher_students ts ON ts.teacher_id=m.teacher_id AND ts.student_id=m.student_id
                JOIN public.student_profiles s ON s.id=m.student_id
                WHERE m.teacher_id=%s ORDER BY m.id DESC""",(teacher["id"],))
            items=cur.fetchall()
        options="".join(f'<option value="{sid}">{E(name)}</option>' for sid,name in students)
        listing="".join(f'<li><a href="/materials/{mid}/download">{E(title)}</a> — {E(name)} ({E(original)}) '
                        f'<form method="post" action="/materials/{mid}/delete" style="display:inline">'
                        f'{token(req)}<button>Delete</button></form></li>'
                        for mid,title,original,name in items)
        body=('<p><a href="/teacher">← Teacher dashboard</a></p>'
              '<article><h2>Upload learning material</h2>'
              '<p>PDF, PNG, JPG, PPTX, DOCX · maximum 10 MB.</p>'
              f'<form action="/materials" method="post" enctype="multipart/form-data">{token(req)}'
              '<label>Title<input name="title" maxlength="150" required></label>'
              f'<label>Student<select name="student_id" required>{options}</select></label>'
              '<label>File<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.pptx,.docx" required></label>'
              '<button>Upload material</button></form></article>'
              f'<article><h2>Shared materials</h2><ul>{listing or "<li>No materials yet.</li>"}</ul></article>')
        return page("Materials Library",body)

    @app.post("/materials")
    async def upload_material(req:Request,title:str=Form(...),student_id:str=Form(...),
                              csrf:str=Form(...),file:UploadFile=File(...)):
        teacher=require(req,"teacher")
        verifycsrf(req,csrf)
        try:
            sid=str(UUID(student_id))
        except ValueError:
            raise HTTPException(400,"Invalid student")
        title=title.strip()
        original=Path((file.filename or "").replace("\\","/")).name
        suffix=Path(original).suffix.lower()
        if not 1<=len(title)<=150 or not 1<=len(original)<=255 or suffix not in ALLOWED:
            raise HTTPException(400,"Invalid title or file type")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT 1 FROM public.teacher_students
                WHERE teacher_id=%s AND student_id=%s""",(teacher["id"],sid))
            if not cur.fetchone():
                raise HTTPException(403,"Student not assigned to this teacher")
        data=await file.read(MAX_BYTES+1)
        await file.close()
        if not data or len(data)>MAX_BYTES:
            raise HTTPException(413,"File must be between 1 byte and 10 MB")
        signatures={".pdf":b"%PDF-",".png":bytes.fromhex("89504e470d0a1a0a"),
                    ".jpg":bytes.fromhex("ffd8ff"),".jpeg":bytes.fromhex("ffd8ff"),
                    ".pptx":bytes.fromhex("504b0304"),".docx":bytes.fromhex("504b0304")}
        signature=signatures[suffix]
        if not data.startswith(signature):
            raise HTTPException(400,"File signature does not match type")
        _,_,bucket=storage_config()
        path=f"{teacher['id']}/{sid}/{secrets.token_hex(24)}{suffix}"
        storage_request("POST",bucket,path,data,ALLOWED[suffix])
        try:
            with get_connection() as db,db.cursor() as cur:
                cur.execute("""INSERT INTO public.materials
                    (teacher_id,student_id,title,original_name,storage_bucket,storage_path)
                    SELECT ts.teacher_id,ts.student_id,%s,%s,%s,%s
                    FROM public.teacher_students ts
                    WHERE ts.teacher_id=%s AND ts.student_id=%s RETURNING id""",
                    (title,original,bucket,path,teacher["id"],sid))
                if not cur.fetchone():
                    raise HTTPException(403,"Student no longer assigned")
        except Exception:
            try:
                storage_request("DELETE",bucket,path)
            except HTTPException:
                pass
            raise
        return RedirectResponse("/materials",status_code=303)

    @app.get("/materials/{material_id}/download")
    def download_material(req:Request,material_id:int):
        u=viewer(req)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT m.original_name,m.storage_bucket,m.storage_path
                FROM public.materials m
                JOIN public.teacher_students ts ON ts.teacher_id=m.teacher_id AND ts.student_id=m.student_id
                WHERE m.id=%s AND ((m.teacher_id=%s AND %s='teacher')
                                  OR (m.student_id=%s AND %s='student'))""",
                (material_id,u["id"],u["role"],u["id"],u["role"]))
            row=cur.fetchone()
        if not row:
            raise HTTPException(404,"Material not found")
        original,bucket,path=row
        data=storage_request("GET",bucket,path)
        safe_name=quote(original,safe="")
        return Response(data,media_type="application/octet-stream",
                        headers={"Content-Disposition":f"attachment; filename*=UTF-8''{safe_name}",
                                 "Cache-Control":"private, no-store"})

    @app.post("/materials/{material_id}/delete")
    def delete_material(req:Request,material_id:int,csrf:str=Form(...)):
        teacher=require(req,"teacher")
        verifycsrf(req,csrf)
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT m.storage_bucket,m.storage_path FROM public.materials m
                WHERE m.id=%s AND m.teacher_id=%s FOR UPDATE""",(material_id,teacher["id"]))
            row=cur.fetchone()
            if not row:
                raise HTTPException(404,"Material not found")
            bucket,path=row
            storage_request("DELETE",bucket,path)
            cur.execute("DELETE FROM public.materials WHERE id=%s AND teacher_id=%s",
                        (material_id,teacher["id"]))
        return RedirectResponse("/materials",status_code=303)

    @app.get("/my-materials")
    def my_materials(req:Request):
        student=require(req,"student")
        with get_connection() as db,db.cursor() as cur:
            cur.execute("""SELECT m.id,m.title,m.original_name FROM public.materials m
                JOIN public.teacher_students ts ON ts.teacher_id=m.teacher_id AND ts.student_id=m.student_id
                WHERE m.student_id=%s ORDER BY m.id DESC""",(student["id"],))
            items=cur.fetchall()
        listing="".join(f'<li><a href="/materials/{mid}/download">{E(title)}</a> — {E(original)}</li>'
                        for mid,title,original in items)
        return page("My Materials",'<p><a href="/student">← Student dashboard</a></p>'
                    f'<article><h2>Learning materials</h2><ul>{listing or "<li>No shared materials yet.</li>"}</ul></article>')
