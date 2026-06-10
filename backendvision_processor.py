# backend/vision_processor.py
import cv2
import numpy as np
from ultralytics import YOLO
import torch
from typing import List, Dict

class SAGEVision:
    def __init__(self):
        # Load YOLOv8 model trained on:
        # - Military vehicles
        # - Armed groups
        # - Suspicious convoys
        # - Refugee camps
        self.model = YOLO("sage_vision_v1.pt")  # Custom trained model
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
    def analyze_drone_frame(self, frame: np.ndarray) -> Dict:
        """Analyze single drone/satellite frame"""
        results = self.model(frame)
        
        detections = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                detections.append({
                    "class": self.model.names[int(box.cls)],
                    "confidence": float(box.conf),
                    "bbox": box.xyxy.tolist()
                })
        
        # Threat assessment
        threat_detected = any(d['class'] in ['armed_person', 'military_vehicle', 'checkpoint'] 
                              for d in detections)
        
        return {
            "detections": detections,
            "threat_detected": threat_detected,
            "threat_level": "high" if threat_detected else "low",
            "timestamp": datetime.now().isoformat()
        }
    
    def analyze_satellite_image(self, image_path: str, coordinates: tuple) -> Dict:
        """Analyze satellite imagery for camp detection"""
        image = cv2.imread(image_path)
        
        # Detect patterns (tents, vehicles, personnel)
        # Custom model for camp detection
        results = self.model(image)
        
        # Calculate camp size estimate
        tent_count = sum(1 for d in results if d['class'] == 'tent')
        
        return {
            "camp_detected": tent_count > 5,
            "estimated_personnel": tent_count * 8,  # rough estimate
            "coordinates": coordinates,
            "risk_level": "critical" if tent_count > 20 else "high" if tent_count > 10 else "medium"
        }