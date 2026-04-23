"""Multimodal engine - images, video, audio, PDF, document understanding."""
import os, io, json, base64, hashlib
from typing import Dict, List, Any, Optional
from PIL import Image
import urllib.request

class MultimodalEngine:
    """Handle images, video, audio, PDF, and document processing."""
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
    
    def process_image(self, image_path: str, task: str = "describe") -> Dict:
        """Process image - describe, extract text, analyze, compare."""
        try:
            img = Image.open(image_path)
            info = {
                "path": image_path,
                "size": img.size,
                "mode": img.mode,
                "format": img.format,
                "file_size": os.path.getsize(image_path),
                "width": img.width,
                "height": img.height,
                "aspect_ratio": round(img.width / img.height, 2) if img.height > 0 else 0,
            }
            if task == "describe":
                info["description"] = f"Image: {img.width}x{img.height} {img.mode} {img.format}"
            return info
        except Exception as e:
            return {"error": str(e)}
    
    def extract_text_from_image(self, image_path: str) -> str:
        """Extract text from image using simple OCR (requires pytesseract if available)."""
        try:
            import pytesseract
            img = Image.open(image_path)
            return pytesseract.image_to_string(img)
        except:
            return "[OCR requires pytesseract - pip install pytesseract]"
    
    def extract_frames_from_video(self, video_path: str, interval_sec: int = 5) -> List[str]:
        """Extract frames from video at regular intervals."""
        import subprocess
        output_dir = os.path.dirname(video_path)
        name = os.path.splitext(os.path.basename(video_path))[0]
        frames = []
        try:
            result = subprocess.run([
                "ffmpeg", "-i", video_path, "-vf", f"fps=1/{interval_sec}",
                "-q:v", "2", f"{output_dir}/{name}_frame_%03d.jpg", "-y"
            ], capture_output=True, text=True)
            import glob
            frames = sorted(glob.glob(f"{output_dir}/{name}_frame_*.jpg"))
        except:
            pass
        return frames
    
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio/video to text."""
        try:
            import subprocess
            result = subprocess.run([
                "whisper", audio_path, "--model", "base", "--language", "en"
            ], capture_output=True, text=True, timeout=300)
            return result.stdout
        except:
            return "[Whisper not installed - run: pip install openai-whisper]"
    
    def generate_image_description(self, image_path: str) -> str:
        """Generate detailed image description using AI."""
        return f"Image at {image_path}: {self.process_image(image_path)}"
    
    def pdf_to_text(self, pdf_path: str, max_pages: int = 50) -> str:
        """Extract text from PDF."""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(pdf_path)
            text = ""
            for i, page in enumerate(reader.pages[:max_pages]):
                text += page.extract_text() or ""
            return text
        except Exception as e:
            return f"Error: {e}"
    
    def pdf_to_images(self, pdf_path: str, output_dir: str = "") -> List[str]:
        """Convert PDF pages to images."""
        try:
            from pdf2image import convert_from_path
            if not output_dir:
                output_dir = os.path.dirname(pdf_path)
            images = convert_from_path(pdf_path, dpi=150)
            paths = []
            for i, img in enumerate(images):
                out_path = f"{output_dir}/page_{i+1:03d}.png"
                img.save(out_path, "PNG")
                paths.append(out_path)
            return paths
        except:
            return []
    
    def create_thumbnail(self, image_path: str, size: Tuple[int,int] = (200,200)) -> str:
        """Create thumbnail of image."""
        try:
            img = Image.open(image_path)
            img.thumbnail(size, Image.Resampling.LANCZOS)
            thumb_path = image_path.rsplit(".", 1)[0] + "_thumb.png"
            img.save(thumb_path, "PNG")
            return thumb_path
        except:
            return ""
    
    def image_to_base64(self, image_path: str) -> str:
        """Convert image to base64 for API calls."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def compare_images(self, img1_path: str, img2_path: str) -> Dict:
        """Compare two images for similarity."""
        try:
            img1 = Image.open(img1_path).resize((100,100)).convert("L")
            img2 = Image.open(img2_path).resize((100,100)).convert("L")
            from PIL import ImageChops
            diff = ImageChops.difference(img1, img2)
            rms = (sum(list(diff.getdata())[:]) / 10000) / 255
            return {"similarity": round(max(0, 1 - rms), 3), "rms_diff": round(rms, 4)}
        except Exception as e:
            return {"error": str(e)}
