import pytest
import os
import requests
from backend.parser import parse_excel
from backend.validation import validate_calibration_data
from backend.certificate import generate_certificate
from backend.ai_agent import load_config, save_config, test_ai_connection

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
    base_url = "http://127.0.0.1:8000"

    # 1. Health Endpoint
    r_health = requests.get(f"{base_url}/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "online"

    # 2. Config Endpoints
    r_cfg_get = requests.get(f"{base_url}/api/config")
    assert r_cfg_get.status_code == 200
    assert "provider" in r_cfg_get.json()

    r_cfg_post = requests.post(f"{base_url}/api/config", json={"provider": "ollama", "ollama_model": "llama3:8b"})
    assert r_cfg_post.status_code == 200
    assert r_cfg_post.json()["status"] == "SUCCESS"

    r_cfg_test = requests.post(f"{base_url}/api/config/test-ai", json={"provider": "heuristic"})
    assert r_cfg_test.status_code == 200
    assert r_cfg_test.json()["status"] == "CONNECTED"

    # 3. Process Endpoint
    files = {
        'submission_file': ('submission_sample.xlsx', open('samples/submission_sample.xlsx', 'rb'), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        'calibration_file': ('calibration_sample.xlsx', open('samples/calibration_sample.xlsx', 'rb'), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    }
    data = {'template_type': 'MCC15-07'}
    r_proc = requests.post(f"{base_url}/api/process", files=files, data=data)
    assert r_proc.status_code == 200
    res_data = r_proc.json()
    assert res_data["status"] == "SUCCESS"
    assert "job_id" in res_data
    assert "audit_hash" in res_data

    # 4. Download Endpoint
    r_dl = requests.get(f"{base_url}{res_data['download_url']}")
    assert r_dl.status_code == 200
    assert len(r_dl.content) > 0

    # 5. Audit Endpoint
    r_audit = requests.get(f"{base_url}/api/audit")
    assert r_audit.status_code == 200
    assert isinstance(r_audit.json(), list)
    assert len(r_audit.json()) > 0
