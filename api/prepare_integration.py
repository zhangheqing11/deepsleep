"""Export immutable upstream sources into ignored var/, without merging branches."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = "snapshot.json"

def specification():
    return json.loads((ROOT / "api/integration_sources.json").read_text(encoding="utf-8"))

def _git():
    git = shutil.which("git")
    if git:
        return git
    candidate = Path("C:/Program Files/Git/cmd/git.exe")
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("Git is required to export already fetched upstream sources.")

def verify_snapshot(root: Path) -> dict:
    root = Path(root).resolve()
    marker = root / MARKER
    if not marker.is_file():
        raise RuntimeError("Run python -m api.prepare_integration before starting offline integration.")
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    if metadata.get("sources") != specification() or not metadata.get("files"):
        raise RuntimeError("Snapshot sources differ from the pinned integration versions.")
    for relative, digest in metadata["files"].items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Invalid or missing dependency file: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Dependency source was modified: {relative}")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and p.name != MARKER and "__pycache__" not in p.parts}
    if actual != set(metadata["files"]):
        raise RuntimeError("Unexpected files in the dependency snapshot.")
    return metadata

def prepare(root: Path = ROOT, destination: Path | None = None) -> Path:
    root = Path(root).resolve()
    destination = Path(destination or root / "var/integration-deps").resolve()
    if not destination.is_relative_to(root / "var"):
        raise ValueError("Dependency exports must stay under the project var/ directory.")
    if destination.exists():
        verify_snapshot(destination)
        return destination
    sources = specification()
    blobs = {}
    for name in ("engine", "simulation"):
        source = sources[name]
        result = subprocess.run([_git(), "archive", "--format=tar", source["ref"], "--", *source["paths"]],
                                cwd=root, capture_output=True)
        if result.returncode:
            raise RuntimeError(f"Pinned {name} commit is unavailable; fetch its branch first.")
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in source["paths"]:
                    raise ValueError("Unsafe archive member")
                if member.isdir():
                    continue
                if not member.isfile() or member.name in blobs:
                    raise ValueError("Archive links or duplicate paths are not supported")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("Unreadable archive member")
                blobs[member.name] = stream.read()
    destination.mkdir(parents=True)
    for relative, content in blobs.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    metadata = {"sources": sources, "files": {p: hashlib.sha256(b).hexdigest() for p, b in blobs.items()}}
    (destination / MARKER).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    verify_snapshot(destination)
    return destination

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    print(prepare(destination=args.destination))
