import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor


@app.route('/printcheck', methods=['POST'])
def printcheck():
    """
    Endpoint to handle industrial image validation requests.
    cmdCode 2: Poll processing status and handle retry logic.
    cmdCode 3: Initialize image capture and start asynchronous validation.
    """
    global cached_template_ocr, cached_template_detections, previous_qr, previous_passed
    global config_meter, config_nic, processing_future, processing_LED
    global meterport, nicport, retry_future, retry_attempted, YUY
    global meterindex, nicindex, capture_config_meter, capture_config_nic

    data = request.json
    cmd_code = data["header"]["cmdCode"]

    # --- CMD 2: POLL STATUS & RETRY LOGIC ---
    if cmd_code == 2:
        if not processing_future:
            return jsonify({
                "header": {"cmdCode": cmd_code},
                "data": {"status": "-1", "message": "No job submitted", "success": False}
            }), 200

        if not processing_future.done():
            return jsonify({
                "header": {"cmdCode": cmd_code},
                "data": {"status": "0", "message": "Processing", "success": False}
            }), 200

        # Extract main job results
        main_result = processing_future.result()
        result_data = main_result.get("data", {})
        main_success = bool(result_data.get("success", False))

        if main_success:
            return jsonify({
                "header": {"cmdCode": cmd_code},
                "data": {
                    "success": True,
                    "status": "1",
                    "template_passed": bool(
                        result_data.get("niclogos") and 
                        result_data.get("nic_positions") and 
                        result_data.get("meter_ocr")
                    ),
                    "niclogos": result_data.get("niclogos"),
                    "nic_positions": result_data.get("nic_positions"), 
                    "nic_qr": result_data.get("nic_qr"),
                    "meter_qr": result_data.get("meter_qr"),
                    "meter_ocr": result_data.get("meter_ocr"),
                    "reason": result_data.get("reason"),
                }
            }), 200

        # Handle automatic retry on failure
        if not retry_attempted:
            retry_attempted = True
            reset_usb_hub()
            time.sleep(2)

            meter_img, nic_img = capture_both_cameras()

            # Hardware recovery logic if initial capture fails
            if is_invalid_image(meter_img) or is_invalid_image(nic_img):
                try:
                    reset_v4l2_driver()
                except Exception:
                    pass
                
                resolve_camera_ports()
                meterindex, nicindex = meterport[-1], nicport[-1]

                # Re-configure capture parameters
                capture_config_meter = {"device_index": int(meterindex), "resolution": (2304, 1728), "rotation": meter_angle}
                capture_config_nic = {"device_index": int(nicindex), "resolution": (2304, 1728), "rotation": nic_angle}

                if YUY == 'True':
                    configure_camera(meterport, 500)
                    configure_camera(nicport, 500)

                meter_img, nic_img = capture_both_cameras()

                if is_invalid_image(meter_img) or is_invalid_image(nic_img):
                    return jsonify({
                        "header": {"cmdCode": cmd_code},
                        "data": {"status": "1", "success": False, "reason": "Hardware capture failure after reset"}
                    }), 200

            # Offload retry processing to worker thread
            retry_future = executor.submit(process_images, meter_img, nic_img, result_data.get("original_data"))
            return jsonify({
                "header": {"cmdCode": cmd_code},
                "data": {"status": "0", "message": "Retrying with fresh capture", "success": False}
            }), 200

        if retry_future and not retry_future.done():
            return jsonify({
                "header": {"cmdCode": cmd_code},
                "data": {"status": "0", "message": "Processing retry", "success": False}
            }), 200

        # Final evaluation after retry
        retry_result = retry_future.result()
        d2 = retry_result.get("data", {})
        return jsonify({
            "header": {"cmdCode": cmd_code},
            "data": {
                "success": bool(d2.get("success", False)),
                "status": "1",
                "niclogos": d2.get("niclogos"),
                "nic_positions": d2.get("nic_positions"),
                "nic_qr": d2.get("nic_qr"),
                "meter_qr": d2.get("meter_qr"),
                "meter_ocr": d2.get("meter_ocr")
            }
        }), 200

    # --- CMD 3: INITIALIZE CAPTURE & PROCESS ---
    elif cmd_code == 3:
        retry_attempted = False
        retry_future = None

        reset_usb_hub()
        time.sleep(2)
        meter_img, nic_img = capture_both_cameras()

        if is_invalid_image(meter_img) or is_invalid_image(nic_img):
            try:
                reset_v4l2_driver()
            except Exception:
                pass
            resolve_camera_ports()
            time.sleep(1.5)

            meterindex, nicindex = meterport[-1], nicport[-1]
            if YUY == 'True':
                configure_camera(meterport, 500)
                configure_camera(nicport, 500)
            
            meter_img, nic_img = capture_both_cameras()

            if is_invalid_image(meter_img) or is_invalid_image(nic_img):
                return jsonify({
                    "header": {"cmdCode": cmd_code},
                    "data": {"captured": False, "success": False, "error": "Hardware failure"}
                }), 200

        # Start async validation pipeline
        processing_future = executor.submit(process_images, meter_img, nic_img, data)
        return jsonify({"header": {"cmdCode": cmd_code}, "data": {"captured": True, "success": True}})
