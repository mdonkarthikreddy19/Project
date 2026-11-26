"""
    uvicorn app:app --host 0.0.0.0 --port 8000      (run from the backend folder)

Then open http://localhost:8000 - on a phone, use your PC's LAN address.
"""
from __future__ import annotations

from pathlib import Path

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import UnidentifiedImageError
from pydantic import BaseModel

from analysis.findings import combine, verdict
from analysis.forensics import cnn_enabled
from analysis.line_model import available as line_model_available
from analysis.image_check import analyse_image
from analysis.links import analyse_link

# the React app's production build (cd frontend && npm run build)
FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "dist"
MAX_UPLOAD = 12 * 1024 * 1024
ALLOWED = {"image/jpeg", "image/png", "image/webp", "image/jpg", "application/octet-stream", ""}

app = FastAPI(title="Payment receipt checker", docs_url="/api/docs", openapi_url="/api/openapi.json")

# the GitHub Pages copy of the site calls this API from another origin
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "https://mdonkarthikreddy19.github.io,http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"])


class LinkIn(BaseModel):
    url: str


@app.get("/api/health")
def health():
    return {"ok": True, "line_model": line_model_available(), "pixel_model": cnn_enabled()}


@app.post("/api/check/image")
def check_image(file: UploadFile = File(...)):
    if (file.content_type or "") not in ALLOWED:
        raise HTTPException(415, "Upload a JPG, PNG or WebP screenshot.")
    raw = file.file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "That file is over 12 MB. Send the original screenshot, not a scan.")
    if not raw:
        raise HTTPException(400, "The file is empty.")
    try:
        return analyse_image(raw)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "Couldn't open that file as an image. Try a JPG or PNG screenshot.")


@app.post("/api/check/link")
def check_link(body: LinkIn):
    text = body.url.strip()
    if not text or len(text) > 4000:
        raise HTTPException(400, "Paste a link to check.")
    res, err = analyse_link(text)
    if err:
        raise HTTPException(422, err)
    findings, details = res
    pct = combine(findings, prior=-0.3)
    key, label = verdict(pct)
    findings.sort(key=lambda f: -abs(f.weight))
    return {"kind": "link", "fake_percent": pct, "verdict": key, "verdict_label": label,
            "findings": [f.to_dict() for f in findings], "details": details}


if FRONTEND.exists():
    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND), name="static")
else:
    @app.get("/")
    def no_build():
        return {"message": "Frontend not built. Run `npm install && npm run build` in the frontend folder, "
                           "or use `npm run dev` there during development."}
