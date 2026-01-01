from vision_yolo import check_nic_logos, check_nic_position
from vision_qr import validate_qr_code
from vision_ocr import perform_meter_ocr

def _build_response(cmd_code, success=False, logos=True, pos=True, n_qr=True, m_qr=True, ocr=True, reason="", data=None, imgs=None):
    """Helper to maintain a consistent response schema."""
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
    Sequential validation pipeline for industrial product inspection.
    Execution Order: Logos -> Positioning -> QR Decoding -> OCR.
    """
    cmd_code = data["header"]["cmdCode"]
    ideal_artwork = data["data"].get("idealArtworkPath")
    imgs = (meter_img, nic_img)

    # 1. NIC Logo Validation (YOLO)
    logo_res = check_nic_logos(nic_img, ideal_artwork)
    if logo_res.get("status") != "PASS":
        return _build_response(cmd_code, logos=False, pos=False, n_qr=False, m_qr=False, ocr=False, 
                               reason=f"Logo Failure: {logo_res.get('error')}", data=data, imgs=imgs)

    # 2. NIC Position Validation (YOLO + Geometry)
    pos_res = check_nic_position(nic_img, ideal_artwork)
    if pos_res.get("status") != "PASS":
        return _build_response(cmd_code, pos=False, n_qr=False, m_qr=False, ocr=False, 
                               reason=f"Position Failure: {pos_res.get('error')}", data=data, imgs=imgs)

    # 3. NIC QR Validation (QReader)
    nqr_res = validate_qr_code(nic_img)
    if nqr_res.get("error") or not nqr_res.get("codes"):
        return _build_response(cmd_code, n_qr=False, m_qr=False, ocr=False, 
                               reason="NIC QR missing or unreadable", data=data, imgs=imgs)

    # 4. Meter QR Validation (QReader + Bound Checks)
    mqr_res = validate_qr_code(meter_img, check_limits=True)
    if mqr_res.get("error") or not mqr_res.get("codes"):
        return _build_response(cmd_code, m_qr=False, ocr=False, 
                               reason="Meter QR missing or unreadable", data=data, imgs=imgs)
    
    if not mqr_res.get("position_ok") or not mqr_res.get("size_ok"):
        return _build_response(cmd_code, m_qr=False, ocr=False, 
                               reason="Meter QR position/size out of tolerance", data=data, imgs=imgs)

    # 5. Meter OCR Validation (PaddleOCR)
    ocr_res = perform_meter_ocr(meter_img)
    if ocr_res.get("status") != "PASS":
        return _build_response(cmd_code, ocr=False, 
                               reason=f"OCR Failure: {ocr_res.get('error', 'Boundary check failed')}", data=data, imgs=imgs)

    # Final Success
    return _build_response(cmd_code, success=True, data=data, imgs=imgs)
