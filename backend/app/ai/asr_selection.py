"""Explicit batch ASR selection. Live MOSS configuration remains independent."""
def batch_asr_identity(settings):
    provider = getattr(settings, "BATCH_ASR_PROVIDER", "moss")
    if provider == "whisper":
        return {"provider": provider, "model_id": settings.WHISPER_MODEL_ID,
                "precision": settings.WHISPER_PRECISION,
                "chunk_duration": settings.WHISPER_CHUNK_DURATION_SECONDS,
                "chunk_overlap": settings.WHISPER_CHUNK_OVERLAP_SECONDS}
    if provider != "moss":
        raise ValueError("Unknown batch ASR provider; no automatic fallback")
    return {"provider": provider, "model_id": settings.OPENMOSS_MODEL_ID,
            "prompt_policy": settings.OPENMOSS_PROMPT_POLICY,
            "precision": settings.OPENMOSS_PRECISION,
            "chunk_duration": settings.AUDIO_CHUNK_DURATION_SECONDS,
            "chunk_overlap": settings.AUDIO_CHUNK_OVERLAP_SECONDS}
