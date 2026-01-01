import cv2
import time
import subprocess
import glob
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# Configuration Constants (In production, these are derived from the CONFIG file, set as per best compatibility with hardware of that line)
CONFIG = {
    "YUY": True,
    "WIDTH": 3264,
    "HEIGHT": 2448,
    "usb_hub_location": "1-1", 
    "usb_hub_ports": [1, 2],
    "meter_physical_id": "platform-3f980000.usb-usb-0:1.2:1.0",
    "nic_physical_id": "platform-3f980000.usb-usb-0:1.3:1.0"
}
YUY = CONFIG.get("YUY", False)
WIDTH = CONFIG.get("WIDTH", 3264)
HEIGHT = CONFIG.get("HEIGHT", 2448)

def capture_both_cameras(capture_config_meter, capture_config_nic):
    """Parallelized capture for dual camera setup."""
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(capture_cam, capture_config_meter),
            executor.submit(capture_cam, capture_config_nic)
        ]

        results = []
        for future in futures:
            try:
                frame = future.result(timeout=15) # Extended timeout for slow YUYV fps
                results.append(frame)
            except Exception as e:
                print(f"Capture Thread Error: {e}")
                results.append(None)

    return results

def capture_cam(cam_args):
    """Routes to specific capture method based on global format setting."""
    device = f"/dev/video{cam_args['device_index']}"
    rotation = cam_args.get('rotation', 0)
    
    if not YUY:
        return capture_mjpeg_image(device, rotation)
    return capture_yuyv_image(device, rotation)

def capture_mjpeg_image(device, rotation):
    """High-speed MJPEG capture with sensor warm-up."""
    subprocess.run([
        "v4l2-ctl", "-d", device,
        f"--set-fmt-video=width={WIDTH},height={HEIGHT},pixelformat=MJPG"
    ], capture_output=True)

    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open device {device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*'MJPG'))

    # Sensor warm-up
    for _ in range(10):
        cap.read()
        time.sleep(0.02)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("MJPEG capture failed")

    return _rotate_frame(frame, rotation)

def capture_yuyv_image(device, rotation):
    """Reliable YUYV capture for high-fidelity signal (2 FPS throughput)."""
    subprocess.run([
        "v4l2-ctl", "-d", device,
        f"--set-fmt-video=width={WIDTH},height={HEIGHT},pixelformat=YUYV"
    ], capture_output=True)
    
    time.sleep(0.1)
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open device {device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*'YUYV'))

    # Warm up
    for _ in range(5):
        cap.read()
        time.sleep(0.75)

    # Retry logic for frame acquisition
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
    """Helper for image orientation."""
    if rotation == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def reset_usb_hub():
    """Power cycles the cameras using USB hub ports using uhubctl."""
    hub_loc = CONFIG.get("usb_hub_location")
    ports = CONFIG.get("usb_hub_ports", [])

    if not hub_loc or not ports:
        return

    ports_str = ",".join(str(p) for p in ports) if isinstance(ports, list) else ports

    try:
        # Action 2 = Power Off
        subprocess.run(["sudo", "uhubctl", "-l", hub_loc, "-p", ports_str, "-a", "2"], 
                       check=True, capture_output=True)
        time.sleep(1)
        # Action 1 = Power On
        subprocess.run(["sudo", "uhubctl", "-l", hub_loc, "-p", ports_str, "-a", "1"], 
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"USB Hub Reset Error: {e.stderr}")

def reset_v4l2_driver():
    """Performs a kernel-level reload of the uvcvideo driver."""
    try:
        subprocess.run("sudo modprobe -r uvcvideo", shell=True, check=True)
        time.sleep(1)
        subprocess.run("sudo modprobe uvcvideo", shell=True, check=True)
        time.sleep(2)
        return True
    except subprocess.CalledProcessError:
        return False

def is_invalid_image(img, black_threshold=0.99, pixel_threshold=10):
    """
    Checks if the frame is empty or effectively blank (sensor error).
    Filters out frames where >99% of pixels are below the darkness threshold.
    """
    if img is None:
        return True
    try:
        gray = np.mean(img, axis=2) if len(img.shape) == 3 else img
        black_pixels = np.sum(gray <= pixel_threshold)
        return (black_pixels / gray.size) >= black_threshold
    except Exception:
        return True

def resolve_camera_ports():
    """
    Maps physical hardware ID_PATHs to /dev/video nodes.
    Ensures persistent camera assignment regardless of OS enumeration order.
    """
    meter_id = CONFIG.get("meter_physical_id")
    nic_id = CONFIG.get("nic_physical_id")
    
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
