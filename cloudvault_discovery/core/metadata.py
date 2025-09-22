import logging
import os
import json
import zipfile
import PyPDF2
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MetadataExtractor:
    def __init__(self):
        self.extractors = {
            '.jpg': self.extract_image_metadata,
            '.jpeg': self.extract_image_metadata,
            '.png': self.extract_image_metadata,
            '.tiff': self.extract_image_metadata,
            '.pdf': self.extract_pdf_metadata,
            '.docx': self.extract_office_metadata,
            '.xlsx': self.extract_office_metadata,
            '.pptx': self.extract_office_metadata,
            '.mp3': self.extract_audio_metadata,
            '.mp4': self.extract_video_metadata
        }
    
    def extract_image_metadata(self, file_path: str) -> Dict:
        metadata = {"file_type": "image"}
        
        try:
            img = Image.open(file_path)
            
            metadata["format"] = img.format
            metadata["mode"] = img.mode
            metadata["size"] = f"{img.width}x{img.height}"
            
            exifdata = img.getexif()
            
            if exifdata:
                for tag_id in exifdata:
                    tag = TAGS.get(tag_id, tag_id)
                    data = exifdata.get(tag_id)
                    
                    if tag == "DateTime":
                        metadata["creation_date"] = data
                    elif tag == "Make":
                        metadata["camera_make"] = data
                    elif tag == "Model":
                        metadata["camera_model"] = data
                    elif tag == "Software":
                        metadata["software"] = data
                    elif tag == "Artist":
                        metadata["author"] = data
                    elif tag == "Copyright":
                        metadata["copyright"] = data
                    elif tag == "GPSInfo":
                        gps_data = {}
                        for key in data:
                            decode = GPSTAGS.get(key, key)
                            gps_data[decode] = data[key]
                        
                        metadata["gps_coordinates"] = self._convert_gps_coordinates(gps_data)
                
                metadata["all_exif"] = {
                    TAGS.get(k, k): str(v) for k, v in exifdata.items()
                }
            
        except Exception as e:
            logger.error(f"Error extracting image metadata from {file_path}: {e}")
            metadata["error"] = str(e)
        
        return metadata
    
    def extract_pdf_metadata(self, file_path: str) -> Dict:
        metadata = {"file_type": "pdf"}
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                info = pdf_reader.metadata
                if info:
                    metadata["title"] = info.get('/Title', '')
                    metadata["author"] = info.get('/Author', '')
                    metadata["subject"] = info.get('/Subject', '')
                    metadata["creator"] = info.get('/Creator', '')
                    metadata["producer"] = info.get('/Producer', '')
                    
                    if '/CreationDate' in info:
                        metadata["creation_date"] = str(info['/CreationDate'])
                    if '/ModDate' in info:
                        metadata["modification_date"] = str(info['/ModDate'])
                
                metadata["pages"] = len(pdf_reader.pages)
                metadata["encrypted"] = pdf_reader.is_encrypted
                
        except Exception as e:
            logger.error(f"Error extracting PDF metadata from {file_path}: {e}")
            metadata["error"] = str(e)
        
        return metadata
    
    def extract_office_metadata(self, file_path: str) -> Dict:
        metadata = {"file_type": "office"}
        
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                if 'docProps/core.xml' in zip_file.namelist():
                    core_xml = zip_file.read('docProps/core.xml').decode('utf-8')
                    
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(core_xml)
                    
                    namespaces = {
                        'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
                        'dc': 'http://purl.org/dc/elements/1.1/',
                        'dcterms': 'http://purl.org/dc/terms/'
                    }
                    
                    creator = root.find('.//dc:creator', namespaces)
                    if creator is not None:
                        metadata["author"] = creator.text
                    
                    title = root.find('.//dc:title', namespaces)
                    if title is not None:
                        metadata["title"] = title.text
                    
                    created = root.find('.//dcterms:created', namespaces)
                    if created is not None:
                        metadata["creation_date"] = created.text
                    
                    modified = root.find('.//dcterms:modified', namespaces)
                    if modified is not None:
                        metadata["modification_date"] = modified.text
                    
                    last_modified_by = root.find('.//cp:lastModifiedBy', namespaces)
                    if last_modified_by is not None:
                        metadata["last_modified_by"] = last_modified_by.text
                
        except Exception as e:
            logger.error(f"Error extracting Office metadata from {file_path}: {e}")
            metadata["error"] = str(e)
        
        return metadata
    
    def extract_audio_metadata(self, file_path: str) -> Dict:
        metadata = {"file_type": "audio"}
        
        try:
            import mutagen
            
            audio = mutagen.File(file_path)
            if audio:
                metadata["duration"] = str(audio.info.length)
                metadata["bitrate"] = str(getattr(audio.info, 'bitrate', 'Unknown'))
                
                for key, value in audio.items():
                    if key.lower() in ['title', 'artist', 'album', 'date', 'genre']:
                        metadata[key.lower()] = str(value[0]) if isinstance(value, list) else str(value)
                
        except Exception as e:
            logger.error(f"Error extracting audio metadata from {file_path}: {e}")
            metadata["error"] = str(e)
        
        return metadata
    
    def extract_video_metadata(self, file_path: str) -> Dict:
        metadata = {"file_type": "video"}
        
        try:
            import cv2
            
            video = cv2.VideoCapture(file_path)
            
            if video.isOpened():
                metadata["width"] = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
                metadata["height"] = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
                metadata["fps"] = video.get(cv2.CAP_PROP_FPS)
                metadata["frame_count"] = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
                metadata["duration"] = metadata["frame_count"] / metadata["fps"] if metadata["fps"] > 0 else 0
                
                video.release()
                
        except Exception as e:
            logger.error(f"Error extracting video metadata from {file_path}: {e}")
            metadata["error"] = str(e)
        
        return metadata
    
    def _convert_gps_coordinates(self, gps_info: Dict) -> Optional[Dict]:
        try:
            lat = gps_info.get('GPSLatitude')
            lat_ref = gps_info.get('GPSLatitudeRef')
            lon = gps_info.get('GPSLongitude')
            lon_ref = gps_info.get('GPSLongitudeRef')
            
            if lat and lon:
                lat_decimal = self._convert_to_decimal(lat)
                lon_decimal = self._convert_to_decimal(lon)
                
                if lat_ref == 'S':
                    lat_decimal = -lat_decimal
                if lon_ref == 'W':
                    lon_decimal = -lon_decimal
                
                return {
                    "latitude": lat_decimal,
                    "longitude": lon_decimal,
                    "google_maps": f"https://maps.google.com/?q={lat_decimal},{lon_decimal}"
                }
                
        except Exception as e:
            logger.error(f"Error converting GPS coordinates: {e}")
        
        return None
    
    def _convert_to_decimal(self, dms):
        degrees = dms[0]
        minutes = dms[1] / 60.0
        seconds = dms[2] / 3600.0
        return degrees + minutes + seconds
    
    def extract_all(self, file_path: str) -> Dict:
        file_ext = os.path.splitext(file_path)[1].lower()
        
        metadata = {
            "filename": os.path.basename(file_path),
            "file_size": os.path.getsize(file_path),
            "file_extension": file_ext,
            "extraction_time": datetime.now().isoformat()
        }
        
        if file_ext in self.extractors:
            specific_metadata = self.extractors[file_ext](file_path)
            metadata.update(specific_metadata)
        
        metadata["osint_value"] = self._evaluate_osint_value(metadata)
        
        return metadata
    
    def _evaluate_osint_value(self, metadata: Dict) -> Dict:
        osint_score = 0
        valuable_info = []
        
        if metadata.get("author") or metadata.get("last_modified_by"):
            osint_score += 3
            valuable_info.append("Contains author information")
        
        if metadata.get("gps_coordinates"):
            osint_score += 5
            valuable_info.append("Contains GPS location")
        
        if metadata.get("software") or metadata.get("producer"):
            osint_score += 2
            valuable_info.append("Contains software information")
        
        if metadata.get("creation_date") or metadata.get("modification_date"):
            osint_score += 1
            valuable_info.append("Contains timestamp information")
        
        return {
            "score": osint_score,
            "valuable_info": valuable_info,
            "rating": "High" if osint_score >= 5 else "Medium" if osint_score >= 3 else "Low"
        }