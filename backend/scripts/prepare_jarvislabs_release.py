"""Package current application source for JarvisLabs without credentials, caches or evidence."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = ROOT / "e2e_validation/artifacts" / ("jarvislabs_release_" + stamp)
    target.mkdir(parents=True)
    paths = set()
    for folder in ("backend/app", "backend/scripts", "backend/alembic", "src", "public"):
        for file in (ROOT / folder).rglob("*"):
            relative = file.relative_to(ROOT)
            if not file.is_file() or file.is_symlink():
                continue
            if any(part in {"__pycache__", "tests", ".pytest_cache", "node_modules"} for part in relative.parts):
                continue
            if file.suffix not in {".py", ".sh", ".ps1", ".ts", ".tsx", ".js", ".css", ".svg", ".html",
                                   ".mako", ".jpg", ".jpeg", ".png", ".webp", ".woff", ".woff2", ".ttf"}:
                continue
            paths.add(relative)
    for name in ("package.json", "package-lock.json", "tsconfig.json", "vite.config.ts", "index.html",
                 "backend/requirements.txt", "backend/requirements-real.txt", "backend/alembic.ini",
                 "backend/cli.py", "backend/moss_adapter.py", "docs/JARVISLABS_EXECUTION.md"):
        paths.add(Path(name))
    manifest = {"timestamp": datetime.now(timezone.utc).isoformat(),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source": "current working tree including local changes", "files": {},
                "credentials_included": False, "models_included": False, "audio_included": False,
                "jarvislabs_execution": "NOT VERIFIED"}
    archive = target / "abci-mi.tar.gz"
    with tarfile.open(archive, "w:gz", dereference=True) as tar:
        for relative in sorted(paths):
            file = ROOT / relative
            content = file.read_bytes()
            # Windows Git CRLF cannot be executed as a Linux shell script.
            if file.suffix == ".sh":
                content = content.replace(b"\r\n", b"\n")
            manifest["files"][relative.as_posix()] = hashlib.sha256(content).hexdigest()
            info = tarfile.TarInfo("abci-mi/" + relative.as_posix())
            info.size, info.mode = len(content), 0o755 if file.suffix == ".sh" else 0o644
            tar.addfile(info, io.BytesIO(content))
        raw = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo("abci-mi/source_manifest.json")
        info.size, info.mode = len(raw), 0o644
        tar.addfile(info, io.BytesIO(raw))
    manifest.update(archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), archive_bytes=archive.stat().st_size)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"archive": str(archive), "archive_bytes": manifest["archive_bytes"],
                      "archive_sha256": manifest["archive_sha256"], "source_files": len(paths)}))


if __name__ == "__main__":
    main()
