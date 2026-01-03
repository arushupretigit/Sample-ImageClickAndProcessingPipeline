# Production-Grade Image Processing Pipeline (Sample Repository)

This repository demonstrates a **production-ready image processing pipeline** designed for real-world manufacturing & inspection environments.

The focus is on **system stability, fault tolerance, and cycle-time optimization** — critical for production.

---

## What This Pipeline Does

At a high level, the pipeline:

1. Captures images from **multiple USB cameras**
2. Applies **hardware-aware recovery** if capture fails
3. Runs multiple **computer vision checks in parallel**
4. Returns a **deterministic, machine-friendly result** suitable for PLCs or MES systems

---

## Key Engineering Features

### 1. Hardware-Aware Camera Handling

- Dual-camera capture with **explicit device resolution via udev ID_PATH**
- Automatic recovery using:
  - USB hub power cycling (`uhubctl`)
  - Kernel-level `uvcvideo` driver reload
- Supports **MJPEG and YUYV** modes for different reliability / fidelity needs
- Sensor warm-up logic to avoid black or unstable frames

**Benefit:**  
Stable image acquisition even under USB glitches, camera resets, or long runtimes.

---

### 2. Robust Image Validation

- Detects invalid frames (black frames, sensor noise, dead captures)
- Configurable thresholds via external config file
- Prevents bad images from entering the inference pipeline

**Benefit:**  
Avoids false negatives caused by hardware issues instead of actual defects.

---

### 3. Parallel Vision Pipeline (Time-Critical)

Vision tasks are executed **concurrently** using multiprocessing:

- Logo detection (YOLO)
- Logo position validation
- QR code decoding (NIC + meter)
- OCR on meter text

All checks run in parallel and are evaluated deterministically.

**Benefit:**  
Significant cycle-time reduction compared to sequential processing, suitable for production throughput.

---

### 4. Clear Pass / Fail Decision Flow

Validation follows a strict, ordered logic:

1. Logo presence
2. Logo position
3. NIC QR readability
4. Meter QR readability and bounds
5. Meter OCR validation

Each failure returns:
- The exact reason
- Which stage failed
- A consistent response schema

**Benefit:**  
Easy integration with upstream systems and fast root-cause analysis on the shop floor.

---

### 5. Retry Logic Built Into the API

- Automatic retry on failure
- Hardware reset + re-capture before reprocessing
- Retry state tracked explicitly to avoid infinite loops

**Benefit:**  
Reduces manual intervention and avoids unnecessary line stops.

---

### 6. Config-Driven Behavior (No Code Changes)

All environment-specific behavior is externalized:

- Camera port IDs
- Image resolution
- Rotation
- Capture mode (MJPEG / YUYV)
- Validation thresholds
- Hardware control settings

**Benefit:**  
The same codebase can be deployed across machines with different hardware setups.

---

### 7. API Designed for Production Use

- Flask-based control API
- Asynchronous processing using futures
- Poll-based status reporting
- Stateless request/response design from the client’s perspective

**Benefit:**  
Easy to integrate with existing automation systems or HMI software.

---

## Repository Structure
config/
- hawk_settings.conf # Deployment-specific configuration

src/
- app.py # API + orchestration
- hardware.py # Camera control and recovery
- processor.py # Parallel vision pipeline
- vision_logo.py # Logo detection and position checks
- vision_qr.py # QR code validation
- vision_ocr.py # OCR pipeline
- config_loader.py # Config parser and singleton

---

## Notes

- Vision models and limits are **intentionally stubbed or simplified**.
- The goal of this repository is to showcase **system design and deployment practices**, not proprietary models.
- All heavy vision workloads are isolated from the API layer to ensure responsiveness and stability.
---

## Disclaimer

This is a **demonstration repository**.  
Model weights, limits files, and proprietary logic are excluded by design.

