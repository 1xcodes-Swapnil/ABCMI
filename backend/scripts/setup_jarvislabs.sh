#!/usr/bin/env bash
# Install ABCMI using the JarvisLabs template's CUDA torch pair; no model downloads.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
case "$repo" in /home/*) ;; *) echo 'Extract source below persistent /home first.' >&2; exit 1;; esac
export TMPDIR=/home/abci-runtime/tmp
export PIP_CACHE_DIR=/home/abci-runtime/cache/pip
export npm_config_cache=/home/abci-runtime/cache/npm
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR" "$npm_config_cache"
cd "$repo"
python3 - <<'PY'
import torch
from importlib.metadata import version
from pathlib import Path
if not torch.cuda.is_available():
    raise RuntimeError('CUDA unavailable; REAL CPU fallback forbidden')
torch_v, audio_v = version('torch'), version('torchaudio')
if torch_v.split('+')[0] != audio_v.split('+')[0]:
    raise RuntimeError('Template torch/torchaudio mismatch; do not replace blindly')
Path('/home/abci-runtime/torch-constraints.txt').write_text(f'torch=={torch_v}\ntorchaudio=={audio_v}\n')
print('Template CUDA:', torch.version.cuda, 'GPU:', torch.cuda.get_device_name())
PY
python3 -m venv --system-site-packages --without-pip /home/abci-runtime/venv
python3 -m pip --python /home/abci-runtime/venv/bin/python install pip wrapt
python=/home/abci-runtime/venv/bin/python
"$python" -m pip install -c /home/abci-runtime/torch-constraints.txt \
  -r backend/requirements.txt transformers==5.16.1 accelerate==1.14.0 \
  safetensors==0.8.0 bitsandbytes==0.50.2 pyannote.audio==4.0.7 av==17.1.0 \
  'librosa>=0.11,<0.12' 'soundfile>=0.13,<0.15' 'soxr>=1,<2'
"$python" -m pip install --no-deps \
  'moss-transcribe-diarize @ git+https://github.com/OpenMOSS/MOSS-Transcribe-Diarize.git@61bc29cd4120be7b5d3b761b64cd5dff57263642'
# --system-site-packages can expose a preinstalled PyAnnote. Refuse to patch outside venv.
"$python" - <<'PY'
from importlib.metadata import distribution
from pathlib import Path
import shutil, sysconfig
dist = distribution('pyannote.audio')
site = Path(sysconfig.get_paths()['purelib'])
for name in dist.files:
    p = Path(str(name))
    if (p.parts[0] == 'pyannote' and len(p.parts) > 1 and p.parts[1] == 'audio') or p.parts[0].endswith('.dist-info'):
        src, dst = Path(dist.locate_file(name)), site / p
        if src.is_file() and src.resolve() != dst.resolve():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
PY
"$python" backend/scripts/patch_pyannote_407.py
if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo 'Node/npm are required for the UI; install a compatible Node runtime under /home.' >&2
  exit 1
fi
npm ci
# A lockfile produced on Windows can omit Rollup's optional Linux native wheel.
# Keep the resolved Rollup version and package-lock unchanged.
if ! node -e "require('rollup')" >/dev/null 2>&1; then
  rollup_version="$(node -p "require('./node_modules/rollup/package.json').version")"
  npm install --no-save --package-lock=false "@rollup/rollup-linux-x64-gnu@$rollup_version"
fi
npm run build
echo 'Dependencies installed. No services started, migrations applied, or inference executed.'
echo 'Configure private backend/.env and transfer existing required model caches before preflight.'
