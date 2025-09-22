import logging
import os
import struct
import hashlib
from PIL import Image
from typing import Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class SteganographyDetector:
    def __init__(self):
        self.image_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff']
        self.audio_extensions = ['.mp3', '.wav', '.flac', '.ogg', '.m4a']
        self.document_extensions = ['.pdf', '.docx', '.xlsx', '.pptx']
        
    def detect_lsb_steganography(self, image_path: str) -> Dict:
        try:
            img = Image.open(image_path)
            pixels = np.array(img)
            
            lsb_bits = []
            for row in pixels:
                for pixel in row:
                    if isinstance(pixel, np.ndarray):
                        for value in pixel:
                            lsb_bits.append(value & 1)
                    else:
                        lsb_bits.append(pixel & 1)
            
            lsb_bytes = []
            for i in range(0, len(lsb_bits) - 8, 8):
                byte = 0
                for j in range(8):
                    byte = (byte << 1) | lsb_bits[i + j]
                lsb_bytes.append(byte)
            
            hidden_data = bytes(lsb_bytes)
            
            signatures = {
                b'PK': 'ZIP archive',
                b'%PDF': 'PDF document',
                b'\x89PNG': 'PNG image',
                b'\xFF\xD8\xFF': 'JPEG image',
                b'-----BEGIN': 'PEM certificate/key',
                b'{"': 'JSON data',
                b'<?xml': 'XML data'
            }
            
            for sig, desc in signatures.items():
                if sig in hidden_data[:1000]:
                    logger.warning(f"Found potential {desc} hidden in {image_path}")
                    return {
                        "detected": True,
                        "type": "LSB",
                        "hidden_content": desc,
                        "confidence": "high"
                    }
            
            entropy = self.calculate_entropy(hidden_data[:1000])
            if entropy > 7.5:
                return {
                    "detected": True,
                    "type": "LSB",
                    "hidden_content": "Encrypted/compressed data",
                    "confidence": "medium",
                    "entropy": entropy
                }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"Error analyzing {image_path}: {e}")
            return {"detected": False, "error": str(e)}
    
    def detect_eof_steganography(self, file_path: str) -> Dict:
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            
            file_ext = os.path.splitext(file_path)[1].lower()
            
            eof_markers = {
                '.jpg': b'\xFF\xD9',
                '.jpeg': b'\xFF\xD9',
                '.png': b'IEND\xAE\x42\x60\x82',
                '.gif': b'\x00\x3B',
                '.pdf': b'%%EOF',
                '.zip': None
            }
            
            if file_ext in eof_markers and eof_markers[file_ext]:
                marker = eof_markers[file_ext]
                marker_pos = content.find(marker)
                
                if marker_pos != -1:
                    eof_pos = marker_pos + len(marker)
                    extra_data = content[eof_pos:]
                    
                    if len(extra_data) > 100:
                        logger.warning(f"Found {len(extra_data)} bytes after EOF in {file_path}")
                        return {
                            "detected": True,
                            "type": "EOF",
                            "extra_bytes": len(extra_data),
                            "confidence": "high"
                        }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"Error checking EOF in {file_path}: {e}")
            return {"detected": False, "error": str(e)}
    
    def detect_metadata_steganography(self, file_path: str) -> Dict:
        try:
            from PIL.ExifTags import TAGS
            
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.tiff')):
                img = Image.open(file_path)
                exifdata = img.getexif()
                
                suspicious_tags = []
                for tag_id in exifdata:
                    tag = TAGS.get(tag_id, tag_id)
                    data = exifdata.get(tag_id)
                    
                    if isinstance(data, bytes) and len(data) > 1000:
                        suspicious_tags.append({
                            "tag": tag,
                            "size": len(data),
                            "preview": data[:50].hex()
                        })
                    
                    elif isinstance(data, str) and len(data) > 500:
                        suspicious_tags.append({
                            "tag": tag,
                            "size": len(data),
                            "preview": data[:50]
                        })
                
                if suspicious_tags:
                    logger.warning(f"Found suspicious metadata in {file_path}")
                    return {
                        "detected": True,
                        "type": "Metadata",
                        "suspicious_tags": suspicious_tags,
                        "confidence": "medium"
                    }
            
            return {"detected": False}
            
        except Exception as e:
            logger.error(f"Error checking metadata in {file_path}: {e}")
            return {"detected": False, "error": str(e)}
    
    def calculate_entropy(self, data: bytes) -> float:
        if not data:
            return 0.0
        
        entropy = 0
        for i in range(256):
            p_i = data.count(i) / len(data)
            if p_i > 0:
                entropy -= p_i * np.log2(p_i)
        
        return entropy
    
    def detect_all(self, file_path: str) -> Dict:
        results = {
            "file": file_path,
            "checks": []
        }
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        if file_ext in self.image_extensions:
            lsb_result = self.detect_lsb_steganography(file_path)
            if lsb_result["detected"]:
                results["checks"].append({"method": "LSB", "result": lsb_result})
            
            metadata_result = self.detect_metadata_steganography(file_path)
            if metadata_result["detected"]:
                results["checks"].append({"method": "Metadata", "result": metadata_result})
        
        eof_result = self.detect_eof_steganography(file_path)
        if eof_result["detected"]:
            results["checks"].append({"method": "EOF", "result": eof_result})
        
        results["steganography_detected"] = len(results["checks"]) > 0
        
        return results