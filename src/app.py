import time
from flask import Flask, request, jsonify
from concurrent.futures import ThreadPoolExecutor
from config_loader import CONFIG
from hardware import (
    reset_usb_hub, 
    reset_v4l2_driver, 
    capture_both_cameras, 
    resolve_camera_ports, 
    is_invalid_image,
    configure_camera
)

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=4)

# Global state for async job management
processing_future = None
retry_future = None
retry_attempted = False

@app.route('/printcheck', methods=['POST'])
def printcheck():
    global processing_future, retry_future, retry_attempted

    data = request.json
    cmd_code = data["header"]["cmdCode"]

    # --- CMD 2: POLL STATUS & RETRY LOGIC ---
    if cmd_code == 2:
        if not processing_future:
            return jsonify({"header": {"cmdCode": cmd_code}, "data": {"status": "-1", "success": False}}), 200

        if not processing_future.done():
            return jsonify({"header": {"cmdCode": cmd_code}, "data": {"status": "0", "success": False}}), 200

        main_result = processing_future.result()
        result_data = main_result.get("data", {})
        
        if result_data.get("success", False):
            return jsonify({
                "header": {"cmdCode": cmd_code},
                "data": {
                    "success": True, 
                    "status": "1",
                    "template_passed": all([result_data.get("niclogos"), result_data.get("nic_positions"), result_data.get("meter_ocr")]),
                    "niclogos": result_data.get("niclogos"),
                    "nic_positions": result_data.get("nic_positions"), 
                    "nic_qr": result_data.get("nic_qr"),
                    "meter_qr": result_data.get("meter_qr"),
                    "meter_ocr": result_data.get("meter_ocr")
                }
            }), 200

        # Automatic Retry Flow
        if not retry_attempted:
            retry_attempted = True
            reset_usb_hub()
            time.sleep(2)

            # Re-resolve ports and capture
            meter_port, nic_port = resolve_camera_ports()
            meter_img, nic_img = capture_both_cameras(meter_port, nic_port)

            if is_invalid_image(meter_img) or is_invalid_image(nic_img):
                reset_v4l2_driver()
                meter_port, nic_port = resolve_camera_ports()
                
                if CONFIG.get("YUY_MODE"):
                    configure_camera(meter_port, 500)
                    configure_camera(nic_port, 500)

                meter_img, nic_img = capture_both_cameras(meter_port, nic_port)

                if is_invalid_image(meter_img) or is_invalid_image(nic_img):
                    return jsonify({"header": {"cmdCode": cmd_code}, "data": {"status": "1", "success": False, "reason": "Hardware Failure"}}), 200

            # Offload to worker thread (process_images function from processor module)
            from processor import process_images
            retry_future = executor.submit(process_images, meter_img, nic_img, data)
            return jsonify({"header": {"cmdCode": cmd_code}, "data": {"status": "0", "message": "Retrying", "success": False}}), 200

        if retry_future and not retry_future.done():
            return jsonify({"header": {"cmdCode": cmd_code}, "data": {"status": "0", "success": False}}), 200

        retry_result = retry_future.result()
        return jsonify({"header": {"cmdCode": cmd_code}, "data": retry_result.get("data", {})}), 200

    # --- CMD 3: INITIALIZE CAPTURE ---
    elif cmd_code == 3:
        retry_attempted = False
        reset_usb_hub()
        time.sleep(2)
        
        meter_port, nic_port = resolve_camera_ports()
        meter_img, nic_img = capture_both_cameras(meter_port, nic_port)

        if is_invalid_image(meter_img) or is_invalid_image(nic_img):
            reset_v4l2_driver()
            meter_port, nic_port = resolve_camera_ports()
            if CONFIG.get("YUY_MODE"):
                configure_camera(meter_port, 500)
                configure_camera(nic_port, 500)
            meter_img, nic_img = capture_both_cameras(meter_port, nic_port)

            if is_invalid_image(meter_img) or is_invalid_image(nic_img):
                return jsonify({"header": {"cmdCode": cmd_code}, "data": {"captured": False, "success": False}}), 200

        from processor import process_images
        processing_future = executor.submit(process_images, meter_img, nic_img, data)
        return jsonify({"header": {"cmdCode": cmd_code}, "data": {"captured": True, "success": True}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
