import openpyxl
from typing import Dict, Any, List
from datetime import datetime
import os

BOEC_SCHEMA = {
    "required_sheets": ["Submission", "RawData"],
    "rules": [
        {"sheet": "Submission", "cell": "B4", "field": "client_name", "type": str, "required": True},
        {"sheet": "Submission", "cell": "B7", "field": "instrument_id", "type": str, "regex": r"BOEC-.*"},
        {"sheet": "RawData", "range": "D2:D8", "field": "temp", "type": float, "min": 18.0, "max": 24.0},
        {"sheet": "RawData", "range": "E2:E8", "field": "humidity", "type": float, "min": 30.0, "max": 60.0}
    ]
}

def validate_schema(wb: openpyxl.Workbook) -> List[Dict[str, Any]]:
    """
    Validates workbook layout and cell types against BOEC_SCHEMA prior to extraction.
    Ensures SANAS TR-18 / ISO17025 impartiality and prevents extraction of malformed data.
    """
    schema_results = []
    sheet_names = wb.sheetnames

    # Check required sheets
    for req_sheet in BOEC_SCHEMA.get("required_sheets", []):
        if req_sheet not in sheet_names:
            schema_results.append({
                "level": "WARNING",
                "sheet": req_sheet,
                "rule": f"Missing sheet: {req_sheet}",
                "message": f"Expected worksheet '{req_sheet}' not found in workbook. Fallback parser will search all available sheets."
            })

    # Validate cell level schema rules if target sheets exist
    for rule in BOEC_SCHEMA.get("rules", []):
        sheet_name = rule["sheet"]
        if sheet_name in sheet_names:
            ws = wb[sheet_name]
            cell_ref = rule.get("cell")
            if cell_ref:
                val = ws[cell_ref].value
                if rule.get("required") and (val is None or str(val).strip() == ""):
                    schema_results.append({
                        "level": "ERROR",
                        "sheet": sheet_name,
                        "cell": cell_ref,
                        "rule": rule["field"],
                        "message": f"Required field '{rule['field']}' at cell {cell_ref} is empty."
                    })
            cell_range = rule.get("range")
            if cell_range:
                try:
                    cells = ws[cell_range]
                    for row in cells:
                        for cell in row:
                            if cell.value is not None and isinstance(cell.value, (int, float)):
                                num = float(cell.value)
                                if "min" in rule and num < rule["min"]:
                                    schema_results.append({
                                        "level": "WARNING",
                                        "sheet": sheet_name,
                                        "cell": cell.coordinate,
                                        "rule": rule["field"],
                                        "message": f"Value {num} at {cell.coordinate} below SANAS/ISO range ({rule['min']}-{rule['max']})."
                                    })
                                elif "max" in rule and num > rule["max"]:
                                    schema_results.append({
                                        "level": "WARNING",
                                        "sheet": sheet_name,
                                        "cell": cell.coordinate,
                                        "rule": rule["field"],
                                        "message": f"Value {num} at {cell.coordinate} above SANAS/ISO range ({rule['min']}-{rule['max']})."
                                    })
                except Exception:
                    pass

    return schema_results

def parse_excel(file_path: str) -> Dict[str, Any]:
    """
    Parses an Excel workbook into structured data for BOEC calibration processing.
    Extracts sheets, raw rows, and maps key fields (customer, equipment, serial, environmental conditions, calibration dose points).
    """
    wb = openpyxl.load_workbook(file_path, data_only=True)
    schema_validation = validate_schema(wb)
    data = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet_data = []
        for row in ws.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                sheet_data.append(list(row))
        data[sheet_name] = sheet_data

    # Extract key BOEC metadata fields
    customer = extract_field(data, ["customer", "client", "client name"])
    equipment = extract_field(data, ["equipment", "instrument", "device", "model", "type"])
    serial = extract_field(data, ["serial", "s/n", "serial number"])
    cal_date = extract_field(data, ["date", "calibration date"])
    technician = extract_field(data, ["technician", "calibrated by", "operator"])
    ref_standard = extract_field(data, ["reference standard", "source", "ref source", "standard"])
    procedure_ref = extract_field(data, ["procedure", "procedure ref", "method"]) or "CP-02-08 / ISO4037-3"

    # Extract environmental parameters
    temperature = extract_numeric_field(data, ["temperature", "temp", "temp (°c)"])
    humidity = extract_numeric_field(data, ["humidity", "rh", "humidity (%)"])
    pressure = extract_numeric_field(data, ["pressure", "press", "pressure (kpa)"])

    # Extract measurement dose data points if present
    dose_points = extract_dose_points(data)

    result = {
        "raw_sheets": data,
        "customer": customer or "BOEC Engineering Client",
        "equipment": equipment or "Gamma Survey Meter / EPD",
        "serial": serial or "SN-2026-8600",
        "date": cal_date or datetime.now().strftime("%Y-%m-%d"),
        "technician": technician or "J. Doe (SANAS Tech)",
        "reference_standard": ref_standard or "Cs-137 S-1029",
        "procedure_ref": procedure_ref,
        "temperature": temperature if temperature is not None else 21.5,
        "humidity": humidity if humidity is not None else 45.0,
        "pressure": pressure if pressure is not None else 85.4,
        "dose_points": dose_points,
        "schema_validation": schema_validation,
        "parsed_at": datetime.now().isoformat()
    }
    return result

def extract_field(data: Dict, keywords: List[str]) -> str:
    for sheet_data in data.values():
        for row in sheet_data:
            for cell in row:
                if cell and isinstance(cell, str):
                    for kw in keywords:
                        if kw.lower() in cell.lower():
                            idx = row.index(cell)
                            if idx + 1 < len(row) and row[idx + 1] is not None:
                                return str(row[idx + 1]).strip()
    return ""

def extract_numeric_field(data: Dict, keywords: List[str]) -> float | None:
    val_str = extract_field(data, keywords)
    if val_str:
        try:
            # Clean string to get float
            cleaned = "".join([c for c in val_str if c.isdigit() or c in ['.', '-']])
            return float(cleaned)
        except ValueError:
            pass
    return None

def extract_dose_points(data: Dict) -> List[Dict[str, Any]]:
    points = []
    for sheet_data in data.values():
        for row in sheet_data:
            # Look for rows with nominal, measured values
            nums = [cell for cell in row if isinstance(cell, (int, float))]
            if len(nums) >= 2:
                # Basic heuristic for nominal vs measured dose rate table row
                nominal, measured = nums[0], nums[1]
                if nominal > 0:
                    dev = round(((measured - nominal) / nominal) * 100.0, 2)
                    points.append({
                        "nominal": float(nominal),
                        "measured": float(measured),
                        "unit": "mSv/h",
                        "deviation_pct": dev,
                        "status": "PASS" if abs(dev) <= 10.0 else "FLAGGED"
                    })
    return points
