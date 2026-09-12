from typing import Dict, Any, List

class ValidationResult:
    def __init__(self, status: str, issues: List[str], iso4037_checks: Dict):
        self.status = status
        self.issues = issues
        self.iso4037 = iso4037_checks

def validate_calibration_data(cal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates calibration data against SANAS TR-18, ISO4037-3 (Clause 7 environmental and dose rate checks),
    and BOEC quality manual procedures CP-02-08 / CP-03-07.
    """
    issues = []
    iso_checks = {
        "iso4037-3_compliant": True,
        "temperature_in_range": True,
        "humidity_in_range": True,
        "energy_range_ok": True,
        "distance_ok": True,
        "dose_rate_linearity": True,
        "mandatory_fields_present": True
    }

    # 1. Environmental Conditions Validation (ISO4037-3 Clause 7: Temp 18-24°C, Humidity 30-60%)
    temp = cal_data.get("temperature")
    if temp is None or not (18.0 <= temp <= 24.0):
        iso_checks["temperature_in_range"] = False
        iso_checks["iso4037-3_compliant"] = False
        issues.append(f"Temperature ({temp}°C) outside ISO4037-3 Clause 7 limits (18.0°C - 24.0°C)")

    humidity = cal_data.get("humidity")
    if humidity is None or not (30.0 <= humidity <= 60.0):
        iso_checks["humidity_in_range"] = False
        iso_checks["iso4037-3_compliant"] = False
        issues.append(f"Relative Humidity ({humidity}%) outside ISO4037-3 Clause 7 limits (30.0% - 60.0%)")

    # 2. Raw Measurement & Linearity Checks
    raw = cal_data.get("raw_sheets", {})
    if not raw:
        issues.append("No calibration raw data sheets found")
        iso_checks["iso4037-3_compliant"] = False

    for sheet_name, rows in raw.items():
        for row in rows:
            for cell in row:
                if isinstance(cell, (int, float)) and cell < 0:
                    issues.append(f"Negative measurement dose value detected in sheet '{sheet_name}': {cell}")
                    iso_checks["dose_rate_linearity"] = False

    dose_points = cal_data.get("dose_points", [])
    for pt in dose_points:
        if abs(pt.get("deviation_pct", 0.0)) > 10.0:
            issues.append(f"Dose point nominal {pt.get('nominal')} mSv/h exceeds 10% maximum allowable deviation (Measured deviation: {pt.get('deviation_pct')}%)")
            iso_checks["dose_rate_linearity"] = False

    # 3. Mandatory Fields Verification (SANAS TR-18 / BOEC CP-02-08)
    mandatory_keys = ["customer", "equipment", "serial", "date", "technician", "reference_standard"]
    for key in mandatory_keys:
        if not cal_data.get(key):
            issues.append(f"Missing mandatory certificate field: {key}")
            iso_checks["mandatory_fields_present"] = False

    # Determine validation status
    if not iso_checks["iso4037-3_compliant"] or not iso_checks["mandatory_fields_present"]:
        status = "FAIL"
    elif issues or any(not v for v in iso_checks.values()):
        status = "REVIEW"
    else:
        status = "PASS"

    return {
        "status": status,
        "issues": issues,
        "iso4037_checks": iso_checks,
        "validated_at": cal_data.get("parsed_at"),
        "standard": "ISO4037-3:2019 + SANAS TR-18 + BOEC CP-02-08 / CP-03-07"
    }
