"""
BOEC LLM Agent - Llama API Integration
POPIA-safe: runs only when LLAMA_API_KEY is set, otherwise falls back to local rules
"""
import os
import logging

logger = logging.getLogger("boec.llm")

def get_llama_client():
    api_key = os.getenv("LLAMA_API_KEY")
    if not api_key:
        return None
    try:
        from llama_api_client import LlamaAPIClient
        return LlamaAPIClient(api_key=api_key)
    except Exception as e:
        logger.warning(f"Llama client init failed: {e}")
        return None

def ai_review(validation: dict, sub_data: dict, cal_data: dict) -> dict:
    """
    Called after ISO4037-3 validation. If Llama key missing, returns local fallback.
    """
    client = get_llama_client()
    
    # Fallback when offline / no key (POPIA mode)
    if not client:
        return {
            "mode": "local-fallback",
            "summary": f"Local validation: {validation.get('status','REVIEW')} - {len(validation.get('checks',[]))} checks",
            "recommendation": "Operator review required per SANAS TR-18 §5.4"
        }

    try:
        checks_str = "\n".join([f"- {c.get('check','')}: {c.get('status','')} - {c.get('detail','')}" for c in validation.get('checks',[])[:15]])
        
        prompt = f"""You are BOEC SANAS TR-18 Technical Reviewer for radiation calibration lab.

Equipment: {sub_data.get('Equipment Model','Unknown')} S/N {sub_data.get('Serial Number','')}
Customer: {sub_data.get('Customer','')}
Env: {sub_data.get('Env Temp / Humidity','')}

ISO4037-3 Validation Results:
{checks_str}
Overall: {validation.get('status')}

Task:
1. If any FLAGGED (especially dose rate linearity), explain root cause per ISO4037-3 Clause 7.
2. Is this REVIEW or FAIL? When to require repeat measurement?
3. Provide one sentence for audit log.

Keep response under 150 words, SANAS compliant."""

        resp = client.chat.completions.create(
            model=os.getenv("LLAMA_MODEL", "Llama-4-Maverick"),
            messages=[
                {"role": "system", "content": "You are a SANAS accredited calibration technical reviewer. Be concise, compliant, no hallucination."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        text = resp.choices[0].message.content
        
        return {
            "mode": "llama-api",
            "model": os.getenv("LLAMA_MODEL", "Llama-4-Maverick"),
            "summary": text,
            "recommendation": "AI review complete - operator must approve per S4 checkpoint"
        }
    except Exception as e:
        logger.error(f"Llama API error: {e}")
        return {
            "mode": "error-fallback",
            "summary": f"Llama API error: {str(e)[:200]} - fallback to local",
            "recommendation": validation.get('status','REVIEW')
        }
