---
title: BOEC AI Workflow Agent
emoji: ⚡
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# BOEC AI Workflow Agent for Calibration Certificate Automation
**SANAS TR-18 | ISO4037-3 | ISO/IEC 17025 Compliant**
Prepared for **BOEC Engineering Consultants** by **ITG Consulting**

## Overview
Automated end-to-end laboratory documentation pipeline:
- **Stage 1: File Intake** - Client submission & raw calibration Excel files
- **Stage 2: Extraction** - Structured metadata & dose measurement parsing
- **Stage 3: Validation Engine** - ISO4037-3 Clause 7 environmental & linearity verification
- **Stage 4: Certificate Generation** - MCC15-07 & MCC16-07 templates with RSA-2048 / SHA256 digital signature digests
- **Stage 5: Audit & Backup** - Hash-chained SQLite audit trail for SANAS compliance

## Quick Start
Run locally:
```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```
Or with Docker:
```bash
docker build -t boec-agent .
docker run -p 8000:8000 boec-agent
```
