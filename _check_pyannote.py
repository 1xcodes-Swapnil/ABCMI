"""Load PyAnnote speaker-diarization-3.1 and check weights."""
import os, warnings
warnings.filterwarnings("ignore")
os.environ["HF_HUB_CACHE"] = "F:/hf-cache/hub"
os.environ["HUGGINGFACE_HUB_CACHE"] = "F:/hf-cache/hub"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

from dotenv import load_dotenv
load_dotenv("backend/.env")
import huggingface_hub as hfh

token = os.environ.get("HF_TOKEN", "")
print(f"HF_TOKEN set: {'YES' if token else 'NO'}")

# Set token globally so from_pretrained picks it up
hfh.login(token=token, add_to_git_credential=False)

import torch
print(f"CUDA: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

print("\nLoading pyannote/speaker-diarization-3.1 (no PLDA) ...")
try:
    # pyannote 4.x from_pretrained for speaker-diarization-3.1 tries to pull PLDA from
    # a separately gated repo (pyannote/speaker-diarization-community-1).
    # Workaround: construct SpeakerDiarization directly from the config components.
    from pyannote.audio.pipelines import SpeakerDiarization
    pipe = SpeakerDiarization(
        segmentation="pyannote/segmentation-3.0",
        embedding="pyannote/wespeaker-voxceleb-resnet34-LM",
        embedding_batch_size=32,
        embedding_exclude_overlap=True,
        clustering="AgglomerativeClustering",
        segmentation_batch_size=32,
        plda=None,                 # skip gated PLDA repo
        token=token,
    )
    # Apply the official hyperparameters from config.yaml
    pipe.instantiate({
        "clustering": {"method": "centroid", "min_cluster_size": 12, "threshold": 0.7045654963945799},
        "segmentation": {"min_duration_off": 0.0},
    })
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipe = pipe.to(device)
    print(f"LOADED OK (no PLDA): {type(pipe).__name__} on {device}")
    print("PYANNOTE LOADED")
except Exception as e:
    print(f"LOAD FAILED: {e}")
    import traceback
    traceback.print_exc()
