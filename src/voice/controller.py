#!/usr/bin/env python3
"""Voice Control Module - Speech recognition and synthesis"""
import asyncio
from typing import Optional, Callable, Dict, Any
from pathlib import Path
import json
import wave
import tempfile

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False


class VoiceController:
    """Voice control with speech recognition and synthesis"""
    
    def __init__(self, language: str = "en-US", rate: int = 200):
        self.language = language
        self.rate = rate
        self.recognizer = None
        self.tts_engine = None
        self.microphone = None
        self.is_listening = False
        self._on_command: Optional[Callable] = None
        self._init_components()
    
    def _init_components(self):
        """Initialize speech components"""
        if SPEECH_RECOGNITION_AVAILABLE:
            self.recognizer = sr.Recognizer()
        
        if TTS_AVAILABLE:
            try:
                self.tts_engine = pyttsx3.init()
                self.tts_engine.setProperty("rate", self.rate)
                # Get available voices
                voices = self.tts_engine.getProperty("voices")
                if voices:
                    # Set default voice
                    self.tts_engine.setProperty("voice", voices[0].id)
            except:
                self.tts_engine = None
        
        if PYAUDIO_AVAILABLE and self.recognizer:
            try:
                self.microphone = sr.Microphone()
                # Adjust for ambient noise
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=1)
            except:
                self.microphone = None
    
    def speak(self, text: str) -> Dict:
        """Speak text using TTS"""
        if not self.tts_engine:
            return {
                "success": False, 
                "error": "TTS not available. Install pyttsx3: pip install pyttsx3"
            }
        
        try:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()
            return {"success": True, "message": f"Spoke: {text[:50]}..."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def listen(self, timeout: int = 5, phrase_time_limit: int = 10) -> Dict:
        """Listen for speech and return recognized text"""
        if not self.recognizer or not self.microphone:
            return {
                "success": False,
                "error": "Speech recognition not available. Install: pip install SpeechRecognition pyaudio"
            }
        
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(
                    source, 
                    timeout=timeout, 
                    phrase_time_limit=phrase_time_limit
                )
            
            # Try different recognition services
            # First try Google (free, no API key)
            try:
                text = self.recognizer.recognize_google(audio, language=self.language)
                return {"success": True, "text": text, "service": "google"}
            except sr.UnknownValueError:
                return {"success": False, "error": "Could not understand audio"}
            except sr.RequestError:
                pass
            
            # Fall back to Sphinx (offline, less accurate)
            try:
                text = self.recognizer.recognize_sphinx(audio)
                return {"success": True, "text": text, "service": "sphinx"}
            except:
                return {"success": False, "error": "Recognition failed"}
                
        except sr.WaitTimeoutError:
            return {"success": False, "error": "No speech detected"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def listen_continuous(self, on_command: Callable[[str], None], 
                          wake_word: str = None, 
                          stop_phrase: str = "stop listening"):
        """Start continuous listening mode"""
        if not self.recognizer or not self.microphone:
            return {"success": False, "error": "Speech recognition not available"}
        
        self.is_listening = True
        self._on_command = on_command
        
        def callback(recognizer, audio):
            if not self.is_listening:
                return
            
            try:
                text = recognizer.recognize_google(audio, language=self.language)
                
                # Check for stop phrase
                if stop_phrase.lower() in text.lower():
                    self.stop_listening()
                    self.speak("Stopped listening")
                    return
                
                # Check wake word if set
                if wake_word and wake_word.lower() not in text.lower():
                    return
                
                # Process command
                if self._on_command:
                    self._on_command(text)
                    
            except sr.UnknownValueError:
                pass  # Ignore unrecognized audio
            except sr.RequestError:
                pass  # Ignore API errors
            except Exception as e:
                print(f"Voice error: {e}")
        
        try:
            self.recognizer.listen_in_background(self.microphone, callback)
            return {"success": True, "message": f"Listening for commands... Say '{stop_phrase}' to stop."}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def stop_listening(self):
        """Stop continuous listening"""
        self.is_listening = False
    
    def set_voice(self, voice_id: int = 0) -> Dict:
        """Set TTS voice by index"""
        if not self.tts_engine:
            return {"success": False, "error": "TTS not available"}
        
        try:
            voices = self.tts_engine.getProperty("voices")
            if 0 <= voice_id < len(voices):
                self.tts_engine.setProperty("voice", voices[voice_id].id)
                return {"success": True, "message": f"Voice set to {voices[voice_id].name}"}
            return {"success": False, "error": f"Invalid voice ID. Available: 0-{len(voices)-1}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_voices(self) -> Dict:
        """List available TTS voices"""
        if not self.tts_engine:
            return {"success": False, "error": "TTS not available"}
        
        try:
            voices = self.tts_engine.getProperty("voices")
            voice_list = [{"id": i, "name": v.name, "languages": v.languages} 
                         for i, v in enumerate(voices)]
            return {"success": True, "voices": voice_list}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def set_rate(self, rate: int) -> Dict:
        """Set speech rate (words per minute)"""
        if not self.tts_engine:
            return {"success": False, "error": "TTS not available"}
        
        try:
            self.rate = rate
            self.tts_engine.setProperty("rate", rate)
            return {"success": True, "message": f"Rate set to {rate}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def set_volume(self, volume: float) -> Dict:
        """Set volume (0.0 to 1.0)"""
        if not self.tts_engine:
            return {"success": False, "error": "TTS not available"}
        
        try:
            volume = max(0.0, min(1.0, volume))
            self.tts_engine.setProperty("volume", volume)
            return {"success": True, "message": f"Volume set to {volume}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def save_to_file(self, text: str, filepath: str) -> Dict:
        """Save speech to audio file"""
        if not self.tts_engine:
            return {"success": False, "error": "TTS not available"}
        
        try:
            self.tts_engine.save_to_file(text, filepath)
            self.tts_engine.runAndWait()
            return {"success": True, "message": f"Saved to {filepath}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Voice commands mapping
VOICE_COMMANDS = {
    "open": "open_file",
    "save": "save_file",
    "new": "new_file",
    "run": "run_command",
    "search": "search_files",
    "read": "read_file",
    "write": "write_file",
    "help": "show_help",
    "settings": "open_settings"
}

# Tool definitions for AI
VOICE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "voice_speak",
            "description": "Speak text aloud",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to speak"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "voice_listen",
            "description": "Listen for speech and return recognized text",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeout": {"type": "integer", "description": "Seconds to wait for speech"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "voice_set_rate",
            "description": "Set speech rate",
            "parameters": {
                "type": "object",
                "properties": {
                    "rate": {"type": "integer", "description": "Words per minute (100-300)"}
                },
                "required": ["rate"]
            }
        }
    }
]

# Singleton
_voice_controller: Optional[VoiceController] = None

def get_voice_controller() -> VoiceController:
    """Get or create voice controller"""
    global _voice_controller
    if _voice_controller is None:
        _voice_controller = VoiceController()
    return _voice_controller

def execute_voice_tool(name: str, args: Dict) -> Dict:
    """Execute voice tool by name"""
    vc = get_voice_controller()
    
    if name == "voice_speak":
        return vc.speak(args.get("text", ""))
    elif name == "voice_listen":
        return vc.listen(timeout=args.get("timeout", 5))
    elif name == "voice_set_rate":
        return vc.set_rate(args.get("rate", 200))
    else:
        return {"success": False, "error": f"Unknown voice tool: {name}"}
