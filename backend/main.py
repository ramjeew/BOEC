from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import uuid
import tempfile
from typing import Dict, Any
from backend.parser import parse_excel
from backend.validation import validate_calibration_data
from backend.certificate import generate_certificate
from backend.audit import log_event, get_audit_trail
from backend.ai_agent import load_config, save_config, test_ai_connection, ai_extract_metadata

app = FastAPI(
    title="BOEC AI Workflow Agent",
    version="5.0.0",
    description="SANAS Accredited Calibration Lab - MCC15-07 / MCC16-07 Automation Pipeline"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR = "storage"
CERTS_DIR = os.path.join(STORAGE_DIR, "certs")
os.makedirs(CERTS_DIR, exist_ok=True)

@app.get("/health")
async def health():
    cfg = load_config()
    return {
        "status": "online",
        "mode": "POPIA-safe local",
        "ai_provider": cfg.get("provider", "ollama"),
        "ollama_model": cfg.get("ollama_model", "llama3:8b"),
        "sanas_accreditation": "CAL-2024-07",
        "standards": ["SANAS TR-18", "ISO4037-3:2019", "ISO/IEC 17025:2017"],
        "target_hardware": "BOEC Ryzen 5 8600G (32GB DDR5)"
    }

@app.get("/api/config")
async def get_configuration():
    return load_config()

@app.post("/api/config")
async def update_configuration(config: Dict[str, Any] = Body(...)):
    updated = save_config(config)
    await log_event("SYS_CONFIG", "CONFIG_UPDATE", {"provider": updated.get("provider"), "model": updated.get("ollama_model")})
    return {"status": "SUCCESS", "config": updated}

@app.post("/api/config/test-ai")
async def test_ai_settings(config: Dict[str, Any] = Body(None)):
    res = test_ai_connection(config)
    return res

@app.post("/api/process")
async def process_submission(
    submission_file: UploadFile = File(...),
    calibration_file: UploadFile = File(...),
    template_type: str = Form("MCC15-07")
):
    job_id = str(uuid.uuid4())[:8]
    temp_dir = tempfile.mkdtemp()
    try:
        sub_path = os.path.join(temp_dir, f"{job_id}_submission.xlsx")
        cal_path = os.path.join(temp_dir, f"{job_id}_calibration.xlsx")

        with open(sub_path, "wb") as f:
            shutil.copyfileobj(submission_file.file, f)
        with open(cal_path, "wb") as f:
            shutil.copyfileobj(calibration_file.file, f)

        # Stage 2: Data Extraction
        sub_data = parse_excel(sub_path)
        cal_data = parse_excel(cal_path)

        # Merge extracted metadata
        merged_data = {**sub_data, **cal_data}

        # Optional AI Extraction enhancement
        ai_extracted = ai_extract_metadata(str(merged_data.get("raw_sheets", {})))
        for k, v in ai_extracted.items():
            if v and not merged_data.get(k):
                merged_data[k] = v

        # Stage 3: ISO4037-3 & SANAS Validation
        validation = validate_calibration_data(merged_data)

        # Stage 4: Certificate Generation
        output_filename = f"BOEC_CERT_{job_id}.docx"
        output_path = os.path.join(CERTS_DIR, output_filename)
        generate_certificate(sub_data, cal_data, validation, template_type, output_path)

        # Stage 5: Hash-chained Audit Log Entry
        audit_hash = await log_event(job_id, "PROCESS", {
            "template": template_type,
            "validation_status": validation["status"],
            "customer": merged_data.get("customer"),
            "serial": merged_data.get("serial"),
            "certificate_file": output_filename
        })

        return {
            "job_id": job_id,
            "status": "SUCCESS",
            "validation": validation,
            "extracted_metadata": {
                "customer": merged_data.get("customer"),
                "equipment": merged_data.get("equipment"),
                "serial": merged_data.get("serial"),
                "calibration_date": merged_data.get("date"),
                "technician": merged_data.get("technician"),
                "temperature": merged_data.get("temperature"),
                "humidity": merged_data.get("humidity"),
                "pressure": merged_data.get("pressure")
            },
            "certificate_path": output_path,
            "audit_hash": audit_hash,
            "download_url": f"/api/download/{job_id}"
        }

    except Exception as e:
        await log_event(job_id, "ERROR", {"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.get("/api/audit")
async def audit(limit: int = 100):
    return await get_audit_trail(limit)

@app.get("/api/certificates")
async def list_certs():
    files = os.listdir(CERTS_DIR) if os.path.exists(CERTS_DIR) else []
    certs = []
    for f in sorted(files, reverse=True):
        if f.endswith(".docx"):
            job_id = f.replace("BOEC_CERT_", "").replace(".docx", "")
            certs.append({
                "job_id": job_id,
                "filename": f,
                "download_url": f"/api/download/{job_id}"
            })
    return {"certificates": certs}

@app.get("/api/download/{job_id}")
async def download(job_id: str):
    path = os.path.join(CERTS_DIR, f"BOEC_CERT_{job_id}.docx")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Calibration certificate not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"BOEC_Calibration_Certificate_{job_id}.docx"
    )

if os.path.exists("frontend"):
    app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
