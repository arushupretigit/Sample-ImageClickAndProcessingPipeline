import cv2
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor

# Configuration Constants (In production, these are derived from the CONFIG file, set as per best compatibility with hardware of that line)
YUY = True  
WIDTH = 3264
HEIGHT = 2448

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
