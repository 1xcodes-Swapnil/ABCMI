"""Fetch only the missing official small JIT artifact; never run during inference."""
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    root = Path(__file__).resolve().parents[2]
    destination = root / ".runtime/models/silero"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "silero_vad.jit"
    manifest_path = destination / "provenance.json"
    if target.exists():
        if not manifest_path.exists():
            raise RuntimeError("Existing VAD artifact has no provenance; preserved without overwrite")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if hashlib.sha256(target.read_bytes()).hexdigest() != manifest["sha256"]:
            raise RuntimeError("Existing VAD artifact checksum differs; preserved without overwrite")
        print(json.dumps({"status": "REUSED", "bytes": target.stat().st_size}))
        return
    api = "https://api.github.com/repos/snakers4/silero-vad/contents/src/silero_vad/data/silero_vad.jit"
    request = urllib.request.Request(api, headers={"User-Agent": "ABCI-MI-local-model-provisioning"})
    with urllib.request.urlopen(request, timeout=30) as response:
        metadata = json.load(response)
    size = metadata["size"]
    if not 0 < size <= 4 * 1024 * 1024:
        raise RuntimeError("Official artifact exceeds the bounded 4 MiB provisioning budget")
    url = metadata["download_url"]
    if not url.startswith("https://raw.githubusercontent.com/snakers4/silero-vad/"):
        raise RuntimeError("Unexpected official artifact host/path")
    print(json.dumps({"download_bytes": size, "destination": str(destination),
                      "existing_equivalent": False, "reason": "Missing required local neural VAD artifact"}))
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(size + 1)
    git_blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if len(data) != size or git_blob != metadata["sha"]:
        raise RuntimeError("Downloaded model does not match the official Git blob")
    manifest = {"repository": "snakers4/silero-vad", "source_url": url,
                "git_blob_sha1": git_blob, "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": size, "artifact": str(target)}
    with target.open("xb") as output:
        output.write(data)
    with manifest_path.open("x", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2)
    print(json.dumps({"status": "PROVISIONED", "bytes": size, "sha256": manifest["sha256"]}))


if __name__ == "__main__":
    main()
