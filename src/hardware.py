import cv2
import time
import subprocess
import glob
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from config_loader import CONFIG  # Import the dynamic configuration singleton

def capture_both_cameras(meter_port, nic_port):
    """Parallelized capture for dual camera setup using resolved device nodes."""
    # Fetch rotation settings from config
    meter_rotation = CONFIG.get("METER_ROTATION", 0)
    nic_rotation = CONFIG.get("NIC_ROTATION", 0)

    capture_config_meter = {"device": meter_port, "rotation": meter_rotation}
    capture_config_nic = {"device": nic_port, "rotation": nic_rotation}

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(capture_cam, capture_config_meter),
            executor.submit(capture_cam, capture_config_nic)
        ]

        results = []
        for future in futures:
            try:
                # 15s timeout to account for low FPS YUYV warm-up cycles
                frame = future.result(timeout=15) 
                results.append(frame)
            except Exception as e:
                print(f"Capture Thread Error: {e}")
                results.append(None)

    return results

def capture_cam(cam_args):
    """Routes to specific capture method based on config format setting."""
    device = cam_args['device']
    rotation = cam_args.get('rotation', 0)
    
    # Use config value for YUY_MODE (True/1 or False/0)
    if not CONFIG.get("YUY_MODE"):
        return capture_mjpeg_image(device, rotation)
    return capture_yuyv_image(device, rotation)

def capture_mjpeg_image(device, rotation):
    """High-speed MJPEG capture with sensor warm-up."""
    width = CONFIG.get("WIDTH", 3264)
    height = CONFIG.get("HEIGHT", 2448)

    subprocess.run([
        "v4l2-ctl", "-d", device,
        f"--set-fmt-video=width={width},height={height},pixelformat=MJPG"
    ], capture_output=True)

    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open device {device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*'MJPG'))

    for _ in range(10):
        cap.read()
        time.sleep(0.02)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("MJPEG capture failed")

    return _rotate_frame(frame, rotation)

def capture_yuyv_image(device, rotation):
    """Reliable YUYV capture for high-fidelity signal."""
    width = CONFIG.get("WIDTH", 3264)
    height = CONFIG.get("HEIGHT", 2448)

    subprocess.run([
        "v4l2-ctl", "-d", device,
        f"--set-fmt-video=width={width},height={height},pixelformat=YUYV"
    ], capture_output=True)
    
    time.sleep(0.1)
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open device {device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*'YUYV'))

    for _ in range(5):
        cap.read()
        time.sleep(0.75)

    frame = None
    for _ in range(3):
        ret, frame = cap.read()
        if ret and frame is not None:
            break
        time.sleep(0.75)

    cap.release()
    if frame is None:
        raise RuntimeError("YUYV capture failed after retries")

    return _rotate_frame(frame, rotation)

def _rotate_frame(frame, rotation):
    """Helper for image orientation correction."""
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame

def reset_usb_hub():
    """Power cycles cameras via uhubctl using config-defined hub/ports."""
    hub_loc = CONFIG.get("USB_HUB_LOCATION")
    ports = CONFIG.get("USB_HUB_PORTS", [])

    if not hub_loc or not ports:
        return

    ports_str = ",".join(str(p) for p in ports) if isinstance(ports, list) else str(ports)

    try:
        subprocess.run(["sudo", "uhubctl", "-l", hub_loc, "-p", ports_str, "-a", "2"], 
                       check=True, capture_output=True)
        time.sleep(1)
        subprocess.run(["sudo", "uhubctl", "-l", hub_loc, "-p", ports_str, "-a", "1"], 
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"USB Hub Reset Error: {e.stderr}")

def reset_v4l2_driver():
    """Kernel-level reload of the uvcvideo driver."""
    try:
        subprocess.run("sudo modprobe -r uvcvideo", shell=True, check=True)
        time.sleep(1)
        subprocess.run("sudo modprobe uvcvideo", shell=True, check=True)
        time.sleep(2)
        return True
    except subprocess.CalledProcessError:
        return False

def is_invalid_image(img):
    """Validates frame integrity against sensor-level noise or black frames."""
    if img is None:
        return True
    
    black_threshold = CONFIG.get("BLACK_THRESHOLD", 0.99)
    pixel_threshold = CONFIG.get("PIXEL_VAL_THRESHOLD", 10)

    try:
        gray = np.mean(img, axis=2) if len(img.shape) == 3 else img
        black_pixels = np.sum(gray <= pixel_threshold)
        return (black_pixels / gray.size) >= black_threshold
    except Exception:
        return True

def resolve_camera_ports():
    """Maps physical ID_PATHs to /dev/video nodes via udevadm."""
    meter_id = CONFIG.get("METER_PHYSICAL_ID")
    nic_id = CONFIG.get("NIC_PHYSICAL_ID")
    
    idpath_to_dev = {}
    for dev in glob.glob("/dev/video*"):
        try:
            output = subprocess.check_output(["udevadm", "info", "--name", dev], 
                                           universal_newlines=True)
            for line in output.splitlines():
                if line.startswith("E: ID_PATH="):
                    id_path = line.split("=", 1)[1]
                    idpath_to_dev[id_path] = dev
                    break
        except subprocess.CalledProcessError:
            continue

    meter_port = idpath_to_dev.get(meter_id, "/dev/video0")
    nic_port = idpath_to_dev.get(nic_id, "/dev/video2")
    
    return meter_port, nic_port

def configure_camera(device, exposure_val=500):
    """Utility to set manual exposure values via v4l2-ctl."""
    try:
        subprocess.run([
            "v4l2-ctl", "-d", device, 
            "--set-ctrl=exposure_auto=1", 
            f"--set-ctrl=exposure_absolute={exposure_val}"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Exposure Config Error: {e}")
