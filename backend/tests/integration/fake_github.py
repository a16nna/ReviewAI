"""TEST-ONLY stand-in for GitHub used by verify_stack.py. Never imported by the application."""

import base64
from urllib.parse import parse_qs
from fastapi import FastAPI, HTTPException, Request

app = FastAPI()
TOKEN = "fake-token-good-code"
RECORDED: list[dict] = []
FILE = "import os\n\nx = eval(input())\nprint(x)\n"
PATCH = "@@ -0,0 +1,4 @@\n+import os\n+\n+x = eval(input())\n+print(x)"


def auth(request: Request):
    if request.headers.get("authorization") != f"Bearer {TOKEN}":
        raise HTTPException(401, "Bad credentials")


@app.post("/login/oauth/access_token")
async def token(request: Request):
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    if form.get("code") != "good-code" or form.get("client_secret") != "fake-secret":
        return {"error": "bad_verification_code"}
    return {"access_token": TOKEN, "token_type": "bearer"}


@app.get("/user")
def user(request: Request):
    auth(request)
    return {"login": "fake-octocat"}


@app.get("/user/repos")
def repos(request: Request):
    auth(request)
    return [{"full_name": "fake/repo", "private": False, "default_branch": "main"}]


@app.get("/repos/fake/repo/branches")
def branches(request: Request):
    auth(request)
    return [{"name": "main", "protected": True}]


@app.get("/repos/fake/repo/pulls")
def pulls(request: Request):
    auth(request)
    return [
        {"number": 1, "title": "Add app", "user": {"login": "dev"}, "head": {"ref": "feat"}, "base": {"ref": "main"}}
    ]


@app.get("/repos/fake/repo/pulls/{n}")
def pull(n: int, request: Request):
    auth(request)
    return {"head": {"sha": "abc1234def"}}


@app.get("/repos/fake/repo/pulls/{n}/files")
def files(n: int, request: Request, page: int = 1):
    auth(request)
    return [{"filename": "app.py", "status": "added", "patch": PATCH}] if page == 1 else []


@app.get("/repos/fake/repo/contents/{path:path}")
def contents(path: str, request: Request):
    auth(request)
    return {"encoding": "base64", "size": len(FILE), "content": base64.b64encode(FILE.encode()).decode()}


@app.post("/repos/fake/repo/pulls/{n}/reviews")
async def review(n: int, request: Request):
    auth(request)
    RECORDED.append(await request.json())
    return {"id": len(RECORDED)}


@app.get("/__recorded")  # test-only introspection
def recorded():
    return RECORDED
