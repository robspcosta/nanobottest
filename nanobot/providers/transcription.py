"""Voice transcription provider using Groq."""

import os
from pathlib import Path

import httpx
from loguru import logger


class GroqTranscriptionProvider:
    """Voice transcription provider using Groq's Whisper API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, file_path: str | Path) -> str:
        if not self.api_key:
            return ""
        path = Path(file_path)
        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    files = {"file": (path.name, f), "model": (None, "whisper-large-v3")}
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    response = await client.post(self.api_url, headers=headers, files=files, timeout=60.0)
                    response.raise_for_status()
                    return response.json().get("text", "")
        except Exception as e:
            logger.error("Groq transcription error: {}", e)
            return ""


class GeminiTranscriptionProvider:
    """Voice transcription provider using Google's Gemini 1.5 Flash."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    async def transcribe(self, file_path: str | Path) -> str:
        if not self.api_key:
            return ""
        path = Path(file_path)
        try:
            import base64
            with open(path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "contents": [{
                    "parts": [
                        {"text": "Transcreva o áudio abaixo exatamente como falado, sem comentários adicionais."},
                        {"inline_data": {"mime_type": "audio/ogg", "data": audio_b64}}
                    ]
                }]
            }
            params = {"key": self.api_key}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, params=params, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                
                # Extract text from candidate
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
                return ""
        except Exception as e:
            logger.error("Gemini transcription error: {}", e)
            return ""


class WhisperLocalTranscriptionProvider:
    """Voice transcription provider using a local Whisper API (OpenAI-compatible)."""

    def __init__(self, api_url: str | None = None, api_key: str | None = None):
        # Use internal URL from user if provided, otherwise check env
        base_url = api_url or os.environ.get("WHISPER_API_URL") or "http://172.16.51.5:8000"
        
        # Ensure it points to the transcription endpoint
        if "/v1/audio/transcriptions" not in base_url:
            base_url = base_url.rstrip("/") + "/v1/audio/transcriptions"
            
        self.api_url = base_url
        self.api_key = api_key or os.environ.get("WHISPER_API_KEY", "sk-local")

    async def transcribe(self, file_path: str | Path) -> str:
        path = Path(file_path)
        try:
            async with httpx.AsyncClient() as client:
                with open(path, "rb") as f:
                    # Some local whisper implementations expect 'model' as well
                    files = {"file": (path.name, f), "model": (None, "whisper-1")}
                    headers = {"Authorization": f"Bearer {self.api_key}"}
                    response = await client.post(self.api_url, headers=headers, files=files, timeout=120.0)
                    response.raise_for_status()
                    return response.json().get("text", "")
        except Exception as e:
            logger.error("Local Whisper transcription error: {}", e)
            return ""


def get_transcription_provider():
    """Factory to get the preferred transcription provider.
    Now exclusively uses local Whisper to ensure data privacy as requested.
    """
    url = os.environ.get("WHISPER_API_URL")
    if not url:
        # Default to public Rasys URL for VPS compatibility
        url = "https://whisper.rasys.net.br/v1/audio/transcriptions"
    
    return WhisperLocalTranscriptionProvider(api_url=url)
