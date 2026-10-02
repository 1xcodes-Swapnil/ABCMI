"""Repair pyannote.audio 4.0.7 loading unused PLDA for the 3.1 pipeline.

Run with the same interpreter as ABCI-MI. No models or outputs are substituted.
The original package file is preserved beside it with a .pre_abci_patch suffix.
"""
from importlib.metadata import distribution
from pathlib import Path


def main():
    package = distribution("pyannote.audio")
    if package.version != "4.0.7":
        raise RuntimeError("Patch applies only to inspected pyannote.audio 4.0.7")
    path = Path(package.locate_file("pyannote/audio/pipelines/speaker_diarization.py"))
    source = path.read_text(encoding="utf-8")
    before = "self._plda = get_plda(plda, token=token, cache_dir=cache_dir)"
    after = "self._plda = get_plda(plda, token=token, cache_dir=cache_dir) if clustering == \"VBxClustering\" else None"
    if after in source:
        print("Patch already applied")
        return
    if source.count(before) != 1:
        raise RuntimeError("Installed source differs from inspected implementation")
    updated = source.replace(before, after)
    compile(updated, str(path), "exec")
    backup = path.with_suffix(".py.pre_abci_patch")
    if backup.exists():
        raise RuntimeError("Backup exists; inspect before replacing package source")
    backup.write_text(source, encoding="utf-8")
    path.write_text(updated, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == updated
    print("Applied and syntax-checked one-line PLDA loading fix; original preserved")


if __name__ == "__main__":
    main()
