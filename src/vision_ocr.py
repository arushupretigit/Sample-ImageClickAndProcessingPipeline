"""
This file contains sample functions.
Proprietary text validation logic and serial format matching are abstracted.
"""

import json

class OCR:
    def __init__(self, limits_path):
        self.limits = self._load_limits(limits_path)
        self.ocr = PaddleOCR(
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            text_detection_model_name="PP-OCRv5_mobile_det",
            use_textline_orientation=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            device="cpu"
        )

    def _load_limits(self, path):
        with open(path, 'r') as f:
            return json.load(f)

    def extract_ppocr_boxes(self, page):
        """
        Helper to flatten PaddleOCR results into a structured list.
        Converts 4-point polygons into min/max bounding boxes and center points.
        """
        out = []
        # In production: these come from ocr.predict()
        texts = page.get("rec_texts", [])
        polys = page.get("rec_polys", [])

        for text, poly in zip(texts, polys):
            xs = [p[0] for p in poly]
            ys = [p[1] for p in poly]

            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            y_center = (ymin + ymax) / 2

            out.append({
                "text": text,
                "xmin": float(xmin),
                "y_center": float(y_center),
                "poly": poly
            })
        return out

    def perform_inference(self, image):
        """
        Skeleton for PaddleOCR text extraction.
        Returns extracted strings and their spatial metadata.
        """
        # Simulated page result from PaddleOCR
        mock_page = {
            "rec_texts": ["METER-ID-2026", "BATCH-A1"],
            "rec_polys": [
                [[100, 50], [200, 50], [200, 80], [100, 80]],
                [[100, 100], [200, 100], [200, 130], [100, 130]]
            ]
        }
        return self.extract_ppocr_boxes(mock_page)

def perform_meter_ocr(meter_img):
    """
    In production, this might compare text from multiple images 
    or validate against an expected serial number format.
    """
    ocr_engine = OCR("config/ocr_limits.json")
    
    # Run inference on the provided frame
    extracted_data = ocr_engine.perform_inference(meter_img)

    #Ideal image can also be passed here if we need 1:1 comparison of text
    
    if not extracted_data:
        return {"status": "FAIL", "error": "No text detected"}

    # Placeholder for comparison or format validation logic
    # e.g., if extracted_data[0]['text'] matches regex pattern...
    
    return {"status": "PASS", "data": extracted_data}
