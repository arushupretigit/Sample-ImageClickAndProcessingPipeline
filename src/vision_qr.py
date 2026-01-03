"""
This file contains only sample functions.
Utilizes QReader.
"""

import json
import cv2
from qreader import QReader 
import numpy as np

class QRValidator:
    def __init__(self, limits_path):
        self.limits = self._load_limits(limits_path)
        self.detector = QReader()

    def _load_limits(self, path):
        with open(path, 'r') as f:
            return json.load(f)

    def decode_qr(self, image):
        """
        Uses QReader.detect_and_decode to extract text and bounding boxes.
        """

        decoded_qr, detected_qrs = self.detector.detect_and_decode(image=image, return_detections=True)
        if not detected_qrs:
          raise RuntimeError("No QR code detected")
        #
        #(text and bbox extraction from the results)
        #
        """Sample Response"""
        return {
            "text": "AIK123456",
            "bbox": [1200, 800, 1450, 1050],
        }

def validate_qr_code(image, check_limits=False):
    """
    For checking readbility of the QR code. If check_limits == True,
    then also checks if bounding box is within permissible limits
    """
    validator = QRValidator("config/qr_limits.json")
    result = validator.decode_qr(image)
    
    # Check if text was successfully extracted
    if not result.get("text"):
        return {"codes": [], "error": "Failed to detect QR", "success": False}

    response = {
        "codes": [result["text"]],
        "error": None,
        "position_ok": True
    }

    if check_limits:
        limits = validator.limits.get("qr_limits", {})
        
        # (Position validation logic)
        position_ok = False
        if position_ok == False:
          response["position_ok"] = False
            

    return response
