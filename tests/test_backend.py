import pytest
import os
from fastapi.testclient import TestClient
from backend.main import app
from backend.parser import parse_excel
from backend.validation import validate_calibration_data
from backend.certificate import generate_certificate
from backend.ai_agent import load_config, save_config, test_ai_connection

client = TestClient(app)

def test_ai_agent_config():
    cfg = load_config()
    assert "provider" in cfg
    assert "ollama_url" in cfg

    new_cfg = save_config({"provider": "ollama", "ollama_model": "llama3:8b"})
    assert new_cfg["ollama_model"] == "llama3:8b"

    test_res = test_ai_connection(new_cfg)
    assert "status" in test_res
    assert "provider" in test_res

def test_parser_and_validation():
    sub_data = parse_excel("samples/submission_sample.xlsx")
    cal_data = parse_excel("samples/calibration_sample.xlsx")

    assert sub_data is not None
    assert cal_data is not None

    merged = {**sub_data, **cal_data}
    val = validate_calibration_data(merged)

    assert "status" in val
    assert "iso4037_checks" in val
    assert val["iso4037_checks"]["temperature_in_range"] is True
    assert val["iso4037_checks"]["humidity_in_range"] is True

def test_certificate_generation(tmp_path):
    sub_data = parse_excel("samples/submission_sample.xlsx")
    cal_data = parse_excel("samples/calibration_sample.xlsx")
    val = validate_calibration_data({**sub_data, **cal_data})

    output_path = str(tmp_path / "test_cert.docx")
    res = generate_certificate(sub_data, cal_data, val, "MCC15-07", output_path)

    assert os.path.exists(res)
    assert os.path.getsize(res) > 0

def test_api_endpoints():
    # 1. Health Endpoint
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "online"

    # 2. Config Endpoints
    r_cfg_get = client.get("/api/config")
    assert r_cfg_get.status_code == 200
    assert "provider" in r_cfg_get.json()

    r_cfg_post = client.post("/api/config", json={"provider": "ollama", "ollama_model": "llama3:8b"})
    assert r_cfg_post.status_code == 200
    assert r_cfg_post.json()["status"] == "SUCCESS"

    r_cfg_test = client.post("/api/config/test-ai", json={"provider": "heuristic"})
    assert r_cfg_test.status_code == 200
    assert r_cfg_test.json()["status"] == "CONNECTED"

    # 3. Upload & Extract Endpoint with Date Tracking
    with open('samples/submission_sample.xlsx', 'rb') as f_sub, open('samples/calibration_sample.xlsx', 'rb') as f_cal:
        files = {
            'submission_file': ('submission_sample.xlsx', f_sub, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'rawdata_file': ('calibration_sample.xlsx', f_cal, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        }
        r_up = client.post("/api/upload", files=files)
    assert r_up.status_code == 200
    up_data = r_up.json()
    assert "imported_at" in up_data
    assert "files" in up_data
    assert "imported_at" in up_data["files"][0]

    r_ext = client.post("/api/extract", json={"job_id": up_data["job_id"], "files": up_data["files"]})
    assert r_ext.status_code == 200
    ext_data = r_ext.json()
    assert "extracted_at" in ext_data
    assert "extracted_at" in ext_data["extracted"][0]

    r_gen = client.post("/api/generate-cert", json={"job_id": up_data["job_id"], "template": "MCC15-07"})
    assert r_gen.status_code == 200
    gen_data = r_gen.json()
    assert "created_at" in gen_data

    r_sign = client.post("/api/sign", json={"job_id": up_data["job_id"], "cert_no": "BOEC-CAL-2024-084"})
    assert r_sign.status_code == 200
    sign_data = r_sign.json()
    assert "signed_at" in sign_data

    # 4. Process Endpoint
    with open('samples/submission_sample.xlsx', 'rb') as f_sub2, open('samples/calibration_sample.xlsx', 'rb') as f_cal2:
        files2 = {
            'submission_file': ('submission_sample.xlsx', f_sub2, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'calibration_file': ('calibration_sample.xlsx', f_cal2, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        }
        data2 = {'template_type': 'MCC15-07'}
        r_proc = client.post("/api/process", files=files2, data=data2)

    assert r_proc.status_code == 200
    res_data = r_proc.json()
    assert "job_id" in res_data
    assert "validation" in res_data
    assert "download_url" in res_data

    # 4. Download Endpoint
    r_dl = client.get(res_data['download_url'])
    assert r_dl.status_code == 200
    assert len(r_dl.content) > 0

    # 5. Templates Registry Endpoints
    r_tpl_get = client.get("/api/templates")
    assert r_tpl_get.status_code == 200
    templates = r_tpl_get.json()
    assert isinstance(templates, list)
    assert len(templates) >= 2

    r_tpl_up = client.post("/api/templates/update", json={
        "id": "MCC15-07",
        "version": "v2.2-TEST",
        "status": "ACTIVE",
        "instrument_type": "Area Monitor Test",
        "required_fields": ["Client Name", "Instrument ID"]
    })
    assert r_tpl_up.status_code == 200
    assert r_tpl_up.json()["status"] == "SUCCESS"
    assert r_tpl_up.json()["template"]["version"] == "v2.2-TEST"

    # 6. Audit Endpoint
    r_audit = client.get("/api/audit")
    assert r_audit.status_code == 200
    assert isinstance(r_audit.json(), list)
    assert len(r_audit.json()) > 0
