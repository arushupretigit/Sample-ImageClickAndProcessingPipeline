import concurrent.futures
from vision_logo import check_nic_logos, check_nic_position
from vision_qr import validate_qr_code
from vision_ocr import perform_meter_ocr

def _build_response(cmd_code, success=False, logos=True, pos=True, n_qr=True, m_qr=True, ocr=True, reason="", data=None, imgs=None):
    """Consistent response schema for handshake."""
    return {
        "header": {"cmdCode": cmd_code},
        "data": {
            "success": success,
            "niclogos": logos,
            "nic_positions": pos,
            "nic_qr": n_qr,
            "meter_qr": m_qr,
            "meter_ocr": ocr,
            "template_passed": success,
            "reason": reason,
            "original_data": data,
            "meter_img": imgs[0] if imgs else None,
            "nic_img": imgs[1] if imgs else None
        }
    }

def process_images(meter_img, nic_img, data):
    """
    Parallel validation pipeline. Executes YOLO, QR, and OCR checks 
    concurrently to minimize cycle time on the production line.
    """
    cmd_code = data["header"]["cmdCode"]
    #Ideal Artwork file is saved by another software into a specific location, to ensure correct artwork file is loaded for comparison
    artwork = data["data"].get("idealArtworkPath")
    imgs = (meter_img, nic_img)

    # ProcessPoolExecutor since these are heavy tasks
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        # Submit all tasks simultaneously
        future_logos = pool.submit(check_nic_logos, nic_img, artwork)
        future_pos = pool.submit(check_nic_position, nic_img, artwork)
        future_nqr = pool.submit(validate_qr_code, nic_img)
        future_mqr = pool.submit(validate_qr_code, meter_img, check_limits=True)
        future_ocr = pool.submit(perform_meter_ocr, meter_img)

        try:
            logo_res = future_logos.result()
            pos_res = future_pos.result()
            nqr_res = future_nqr.result()
            mqr_res = future_mqr.result()
            ocr_res = future_ocr.result()
        except Exception as e:
            return _build_response(cmd_code, success=False, reason=f"Inference Engine Error: {str(e)}", data=data, imgs=imgs)
    
    # 1. Logo Check
    if logo_res.get("status") != "PASS":
        return _build_response(cmd_code, logos=False, reason=f"Logo: {logo_res.get('error')}", data=data, imgs=imgs)

    # 2. Position Check
    if pos_res.get("status") != "PASS":
        return _build_response(cmd_code, pos=False, reason=f"Position: {pos_res.get('error')}", data=data, imgs=imgs)

    # 3. NIC QR Check
    if nqr_res.get("error") or not nqr_res.get("codes"):
        return _build_response(cmd_code, n_qr=False, reason="NIC QR unreadable", data=data, imgs=imgs)

    # 4. Meter QR Check
    if mqr_res.get("error") or not mqr_res.get("codes") or not mqr_res.get("position_ok"):
        return _build_response(cmd_code, m_qr=False, reason="Meter QR invalid/out of bounds", data=data, imgs=imgs)

    # 5. OCR Check
    if ocr_res.get("status") != "PASS":
        return _build_response(cmd_code, ocr=False, reason=f"OCR: {ocr_res.get('error')}", data=data, imgs=imgs)

    # All checks passed
    return _build_response(cmd_code, success=True, data=data, imgs=imgs)
