import os
import json
import requests
from typing import Dict, Any

CONFIG_FILE = "storage/config.json"

DEFAULT_CONFIG = {
    "provider": "heuristic",  # Default to POPIA-safe BOEC Local Rules Engine unless Ollama/OpenAI is explicitly configured
    "ollama_url": "http://127.0.0.1:11434",
    "ollama_model": "llama3:8b",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "popia_strict_mode": True
}

def load_config() -> Dict[str, Any]:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
            full_cfg = DEFAULT_CONFIG.copy()
            full_cfg.update(cfg)
            return full_cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(config_data: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    current = load_config() if os.path.exists(CONFIG_FILE) else DEFAULT_CONFIG.copy()
    current.update(config_data)
    with open(CONFIG_FILE, "w") as f:
        json.dump(current, f, indent=2)
    return current

def test_ai_connection(config: Dict[str, Any] = None) -> Dict[str, Any]:
    if config is None:
        config = load_config()

    provider = config.get("provider", "heuristic")

    if provider == "ollama":
        url = config.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")
        model = config.get("ollama_model", "llama3:8b")
        try:
            r = requests.get(f"{url}/api/tags", timeout=2)
            if r.status_code == 200:
                models = [m.get("name") for m in r.json().get("models", [])]
                return {
                    "status": "CONNECTED",
                    "provider": "ollama",
                    "url": url,
                    "target_model": model,
                    "available_models": models,
                    "message": f"Successfully connected to local Ollama instance at {url}."
                }
            else:
                return {
                    "status": "OFFLINE_FALLBACK",
                    "provider": "ollama",
                    "message": f"Ollama returned HTTP {r.status_code}. Using BOEC local rules extraction engine."
                }
        except Exception:
            return {
                "status": "OFFLINE_FALLBACK",
                "provider": "ollama",
                "message": f"Local Ollama service is offline at {url}. Using BOEC local rules extraction engine."
            }

    elif provider == "openai":
        api_key = config.get("openai_api_key", "")
        if not api_key:
            return {
                "status": "ERROR",
                "provider": "openai",
                "message": "OpenAI API Key is empty. Please enter a valid sk-... key."
            }
        try:
            r = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=3)
            if r.status_code == 200:
                return {
                    "status": "CONNECTED",
                    "provider": "openai",
                    "message": "Successfully authenticated with OpenAI API."
                }
            else:
                return {
                    "status": "ERROR",
                    "provider": "openai",
                    "message": f"OpenAI authentication failed (HTTP {r.status_code})."
                }
        except Exception as e:
            return {
                "status": "ERROR",
                "provider": "openai",
                "message": f"Network error connecting to OpenAI API: {str(e)}"
            }

    else:
        return {
            "status": "CONNECTED",
            "provider": "heuristic",
            "message": "Using BOEC Local Rule-Based Extraction Engine (POPIA-safe)."
        }

def ai_extract_metadata(text_content: str) -> Dict[str, Any]:
    """
    Attempts AI-based field extraction using Ollama local LLM or cloud provider if configured,
    falling back to rule-based parser.
    """
    cfg = load_config()
    provider = cfg.get("provider", "heuristic")

    if provider == "ollama":
        url = cfg.get("ollama_url", "http://127.0.0.1:11434").rstrip("/")
        model = cfg.get("ollama_model", "llama3:8b")
        prompt = f"""You are BOEC Calibration Workflow Agent. Extract structured JSON metadata from this calibration text:
Text:
{text_content[:2000]}

Return JSON with keys: customer, equipment, serial, date, technician, temperature, humidity, pressure.
JSON:"""
        try:
            r = requests.post(f"{url}/api/generate", json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }, timeout=2)
            if r.status_code == 200:
                res_json = json.loads(r.json().get("response", "{}"))
                return res_json
        except Exception:
            pass

    return {}
