import os
import json
import requests
from typing import Dict, Any, Optional

def get_llama_client():
    api_key = os.getenv("LLAMA_API_KEY", "")
    if not api_key:
        return None
    return {
        "api_key": api_key,
        "model": os.getenv("LLAMA_MODEL", "Llama-4-Maverick"),
        "base_url": os.getenv("LLAMA_API_BASE", "https://api.llama.com/v1")
    }

def ai_review(validation: Dict[str, Any], sub_data: Dict[str, Any], cal_data: Dict[str, Any]) -> Dict[str, Any]:
    client = get_llama_client()
    if not client:
        return {
            "status": "COMPLETED",
            "mode": "POPIA-safe local rules engine",
            "summary": f"ISO4037-3 checks completed locally. Validation status: {validation.get('status', 'PASS')}.",
            "recommended_action": "Proceed with certificate release" if validation.get("status") == "PASS" else "Perform technical signatory review"
        }

    # If Llama API key is configured, perform Llama API AI review call
    try:
        model = client["model"]
        url = f"{client['base_url']}/chat/completions"
        headers = {
            "Authorization": f"Bearer {client['api_key']}",
            "Content-Type": "application/json"
        }
        prompt = f"""You are the BOEC Calibration Quality Reviewer. Review these calibration validation results:
Validation Status: {validation.get('status')}
Issues: {validation.get('issues')}
Customer: {sub_data.get('customer')}
Serial: {sub_data.get('serial')}

Provide a brief technical review summary and recommended action."""

        r = requests.post(url, headers=headers, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }, timeout=5)

        if r.status_code == 200:
            res_json = r.json()
            content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "status": "COMPLETED",
                "mode": f"Llama API ({model})",
                "summary": content,
                "recommended_action": "Reviewed by Llama AI model"
            }
        else:
            return {
                "status": "FALLBACK",
                "mode": "POPIA-safe local rules engine",
                "summary": f"Llama API returned HTTP {r.status_code}. Local ISO4037-3 validation status: {validation.get('status')}.",
                "recommended_action": "Proceed with local review"
            }
    except Exception as e:
        return {
            "status": "FALLBACK",
            "mode": "POPIA-safe local rules engine",
            "summary": f"Llama API connection error: {str(e)}. Local ISO4037-3 validation status: {validation.get('status')}.",
            "recommended_action": "Proceed with local review"
        }
