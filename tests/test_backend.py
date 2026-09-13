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

    # 3. Process Endpoint
    with open('samples/submission_sample.xlsx', 'rb') as f_sub, open('samples/calibration_sample.xlsx', 'rb') as f_cal:
        files = {
            'submission_file': ('submission_sample.xlsx', f_sub, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'calibration_file': ('calibration_sample.xlsx', f_cal, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        }
        data = {'template_type': 'MCC15-07'}
        r_proc = client.post("/api/process", files=files, data=data)

    assert r_proc.status_code == 200
    res_data = r_proc.json()
    assert res_data["status"] == "SUCCESS"
    assert "job_id" in res_data
    assert "audit_hash" in res_data

    # 4. Download Endpoint
    r_dl = client.get(res_data['download_url'])
    assert r_dl.status_code == 200
    assert len(r_dl.content) > 0

    # 5. Audit Endpoint
    r_audit = client.get("/api/audit")
    assert r_audit.status_code == 200
    assert isinstance(r_audit.json(), list)
    assert len(r_audit.json()) > 0
