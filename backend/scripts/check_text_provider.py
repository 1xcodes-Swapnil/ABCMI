"""Priority credential/model check. Sends no meeting text, prints no credentials."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(DEBUG="false", LOG_LEVEL="CRITICAL", EXECUTION_MODE="REAL")


async def main():
    import httpx
    from app.core.config import get_settings
    settings = get_settings()
    result = {"run_id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
              "check": "Gemini model access", "meeting_text_sent": False,
              "inference_executed": False, "status": "BLOCKED", "configured_model": settings.GEMINI_MODEL}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": settings.GEMINI_API_KEY or ""})
        result["http_status"] = response.status_code
        if response.status_code == 200:
            models = [m["name"].removeprefix("models/") for m in response.json().get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", [])]
            result["available_text_models"] = [m for m in models if "flash" in m and not any(v in m for v in ("image", "tts", "live", "audio"))]
            result["configured_model_available"] = settings.GEMINI_MODEL in models
            result["status"] = "VERIFIED" if result["configured_model_available"] else "BLOCKED"
        else:
            result["reason"] = "Provider rejected model discovery; check credential permissions and API availability"
            # Keep structured error codes only. Messages may echo secrets.
            try:
                error = response.json().get("error", {})
                result["provider_status"] = error.get("status")
                result["provider_reasons"] = [d.get("reason") for d in error.get("details", []) if d.get("reason")]
            except ValueError:
                pass
    except httpx.RequestError as exc:
        result["error_type"] = type(exc).__name__
        result["reason"] = "Network request failed; credential value and endpoint parameters omitted"
    folder = ROOT / "e2e_validation" / "diagnostics"
    path = folder / f"text_provider_{result['run_id']}.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
    print(json.dumps(result, indent=2))
    print(f"Evidence: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
