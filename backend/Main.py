from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import uuid
from backend.parser import parse_excel
from backend.validation import validate_calibration_data
from backend.certificate import generate_certificate
from backend.audit import log_event, get_audit_trail
from backend.llm_agent import ai_review, get_llama_client

app = FastAPI(
    title="BOEC AI Workflow Agent",
    version="2.0.0",
    description="SANAS Accredited Calibration Lab - MCC15-07/MCC16-07 Automation + Llama API"
)

# FIXED CORS - was [""] which blocks frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://boec-calibration-agent.onrender.com",
        "https://ramjeew-boec.onrender.com",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR = "storage"
CERTS_DIR = os.path.join(STORAGE_DIR, "certs")
os.makedirs(CERTS_DIR, exist_ok=True)

@app.get("/health")
async def health():
    llama = get_llama_client() is not None
    return {
        "status": "online",
        "mode": "POPIA-safe local" if not llama else "Llama API hybrid",
        "sanas": "ready",
        "llama_configured": llama,
        "version": "2.0.0"
    }

@app.get("/api/llama-status")
async def llama_status():
    client = get_llama_client()
    return {
        "configured": client is not None,
        "model": os.getenv("LLAMA_MODEL", "Llama-4-Maverick"),
        "has_key": bool(os.getenv("LLAMA_API_KEY")),
        "mode": "live" if client else "local-fallback"
    }

@app.post("/api/process")
async def process_submission(
    submission_file: UploadFile = File(...),
    calibration_file: UploadFile = File(...),
    template_type: str = Form("MCC15-07")
):
    job_id = str(uuid.uuid4())[:8]
    try:
        # Save uploads
        sub_path = f"/tmp/{job_id}_sub.xlsx"
        cal_path = f"/tmp/{job_id}_cal.xlsx"
        with open(sub_path, "wb") as f:
            shutil.copyfileobj(submission_file.file, f)
        with open(cal_path, "wb") as f:
            shutil.copyfileobj(calibration_file.file, f)

        # Parse
        sub_data = parse_excel(sub_path)
        cal_data = parse_excel(cal_path)

        # Validate ISO4037-3 + BOEC rules
        validation = validate_calibration_data(cal_data)

        # NEW: Llama AI review (non-blocking, POPIA-safe fallback)
        ai_result = ai_review(validation, sub_data, cal_data)
        validation["ai_review"] = ai_result

        # Generate certificate (MCC15-07 / MCC16-07)
        output_path = os.path.join(CERTS_DIR, f"BOEC_CERT_{job_id}.docx")
        generate_certificate(sub_data, cal_data, validation, template_type, output_path)

        # Audit trail (hash-chained)
        await log_event(job_id, "PROCESS", {
            "template": template_type,
            "validation": validation["status"],
            "ai_mode": ai_result.get("mode")
        })

        return {
            "job_id": job_id,
            "validation": validation,
            "sub_data": sub_data,
            "cal_data_summary": {k: str(v)[:200] for k,v in list(cal_data.items())[:20]} if isinstance(cal_data, dict) else str(cal_data)[:1000],
            "certificate_path": output_path,
            "download_url": f"/api/download/{job_id}",
            "ai_review": ai_result
        }

    except Exception as e:
        await log_event(job_id, "ERROR", {"error": str(e)})
        raise HTTPException(500, str(e))

@app.get("/api/audit")
async def audit(limit: int = 100):
    return await get_audit_trail(limit)

@app.get("/api/certificates")
async def list_certs():
    files = os.listdir(CERTS_DIR) if os.path.exists(CERTS_DIR) else []
    return {"certificates": files}

@app.get("/api/download/{job_id}")
async def download(job_id: str):
    path = os.path.join(CERTS_DIR, f"BOEC_CERT_{job_id}.docx")
    if not os.path.exists(path):
        raise HTTPException(404, "Certificate not found")
    return FileResponse(path, filename=f"BOEC_Calibration_Certificate_{job_id}.docx")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
