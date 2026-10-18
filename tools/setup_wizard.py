"""Set up a machine for Local AI Assistant.

The graphical installer calls this; so does a human with a terminal. It is kept
in one place on purpose: the PyTorch index choice and the model folder names
have to match what the application looks for, and a second copy of those rules
in a .bat file is how they drift apart.

Every step is idempotent - running it again on a prepared machine does nothing
and says so, instead of downloading gigabytes for nothing.

    python tools/setup_wizard.py doctor
    python tools/setup_wizard.py deps
    python tools/setup_wizard.py models stt tts emb
    python tools/setup_wizard.py ffmpeg --archive path\\to\\ffmpeg.zip
    python tools/setup_wizard.py all --models stt,emb

Exit code is 0 when everything asked for ended up in place, 1 otherwise.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / "venv"
VENV_PYTHON = VENV / "Scripts" / "python.exe"
MODELS = ROOT / "models"
LOGS = ROOT / "logs"

CUDA_INDEX = "https://download.pytorch.org/whl/cu128"
CUDA_INDEX_FALLBACK = "https://download.pytorch.org/whl/cu121"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"

# name -> (folder under models/, repo id, extra snapshot_download arguments,
#          what the user gets, rough download size)
#
# The third element must be a dict, not an empty tuple: it is splatted into the
# call, and "**()" raises TypeError. That bug was caught by installing for real -
# it failed on Whisper and OmniVoice while the embeddings model, which has a
# real dict, went through.
MODEL_SPECS = {
    "stt": (
        "whisper-large-v3-turbo",
        "openai/whisper-large-v3-turbo",
        {},
        "Speech recognition (Whisper Large V3 Turbo)",
        "1.5 GB",
    ),
    "tts": (
        "omnivoice",
        "k2-fsa/OmniVoice",
        {},
        "Voice synthesis (OmniVoice)",
        "3.0 GB",
    ),
    "emb": (
        "all-MiniLM-L6-v2",
        "sentence-transformers/all-MiniLM-L6-v2",
        {"allow_patterns": ["*.json", "*.txt", "1_Pooling/*", "model.safetensors"]},
        "Memory embeddings (all-MiniLM-L6-v2)",
        "87 MB",
    ),
}

# Fail here, at import, rather than two hours into an install: the third element
# is splatted into snapshot_download, which accepts a mapping and nothing else.
for _name, _spec in MODEL_SPECS.items():
    if not isinstance(_spec[2], dict):
        raise TypeError(
            f"MODEL_SPECS[{_name!r}]: extra arguments must be a dict, got {type(_spec[2]).__name__}")


def say(message: str) -> None:
    """Print and log at the same time - the installer shows only the log."""
    print(message, flush=True)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        stamp = __import__("time").strftime("%Y-%m-%d %H:%M:%S")
        with (LOGS / "setup.log").open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {message}\n")
    except OSError:
        pass  # a read-only install dir must not break the install


def fail(message: str) -> int:
    say(f"  [!] {message}")
    return 1


def have_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None


def torch_mode(requested: str) -> str:
    """auto / cuda / cpu, with TORCH_BUILD in .env as the default for auto."""
    if requested != "auto":
        return requested
    env_value = ""
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().upper().startswith("TORCH_BUILD="):
                env_value = line.split("=", 1)[1].strip().strip('"').lower()
                break
    if env_value in ("cuda", "cpu"):
        return env_value
    return "cuda" if have_nvidia() else "cpu"


def run(cmd: list[str], what: str) -> bool:
    """Run a command, streaming nothing but recording success. Returns ok."""
    say(f"  ... {what}")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stdout or "") + (proc.stderr or "")
        tail = [ln for ln in tail.splitlines() if ln.strip()][-6:]
        for line in tail:
            say(f"      {line}")
        return False
    return True


def install_deps(requested_torch: str = "auto") -> int:
    """Create the venv and install everything the application imports."""
    mode = torch_mode(requested_torch)
    say(f"Python: {sys.version.split()[0]} ({sys.executable})")
    say(f"PyTorch build requested: {mode}")

    if not VENV_PYTHON.is_file():
        say("Creating the virtual environment...")
        if not run([sys.executable, "-m", "venv", str(VENV)], "python -m venv"):
            return fail("could not create the virtual environment")
    else:
        say("Virtual environment already exists.")

    py = str(VENV_PYTHON)
    if not run([py, "-m", "pip", "install", "--upgrade", "pip"], "upgrading pip"):
        return fail("could not upgrade pip")

    # pip is satisfied by ANY installed torch, the CPU build included, so it
    # would download nothing over an existing environment. Remove it first.
    index = {"cuda": CUDA_INDEX, "cpu": CPU_INDEX}[mode]
    if mode == "cuda":
        say(f"Installing the CUDA build of PyTorch ({CUDA_INDEX}) - large download")
        ok = (run([py, "-m", "pip", "uninstall", "-y", "torch", "torchaudio"], "removing any previous PyTorch")
              and run([py, "-m", "pip", "install", "torch", "torchaudio", "--index-url", index],
                      "downloading PyTorch"))
        if not ok:
            say(f"  [i] {index} did not work, trying the older build")
            index = CUDA_INDEX_FALLBACK
            ok = (run([py, "-m", "pip", "uninstall", "-y", "torch", "torchaudio"], "removing any previous PyTorch")
                  and run([py, "-m", "pip", "install", "torch", "torchaudio", "--index-url", index],
                          "downloading PyTorch"))
        if not ok:
            say("  [i] no CUDA build could be installed - falling back to the CPU build")
            mode, index = "cpu", CPU_INDEX
            run([py, "-m", "pip", "uninstall", "-y", "torch", "torchaudio"], "removing any previous PyTorch")
            run([py, "-m", "pip", "install", "torch", "torchaudio", "--index-url", index],
                "downloading PyTorch")
    else:
        say(f"Installing the CPU build of PyTorch ({index})")
        run([py, "-m", "pip", "uninstall", "-y", "torch", "torchaudio"], "removing any previous PyTorch")
        if not run([py, "-m", "pip", "install", "torch", "torchaudio", "--index-url", index],
                   "downloading PyTorch"):
            return fail("could not install PyTorch")

    if not run([py, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
               "installing the remaining dependencies"):
        return fail("could not install the dependencies from requirements.txt")

    report_torch(str(VENV_PYTHON))
    return 0


def report_torch(python: str) -> None:
    """Print what PyTorch actually ended up being - not what was asked for."""
    probe = (
        "import torch;"
        "print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
    )
    proc = subprocess.run([python, "-c", probe], capture_output=True, text=True)
    if proc.returncode != 0:
        say(f"  [!] torch does not import: {proc.stderr.strip()[:120]}")
        return
    parts = proc.stdout.split()
    version = parts[0] if parts else "?"
    build = parts[1] if len(parts) > 1 else "None"
    available = len(parts) > 2 and parts[2] == "True"
    if available:
        name = ""
        proc2 = subprocess.run(
            [python, "-c", "import torch;print(torch.cuda.get_device_name(0))"],
            capture_output=True, text=True)
        name = proc2.stdout.strip()
        say(f"  [+] torch {version}, CUDA {build}, GPU: {name}")
    else:
        say(f"  [!] torch {version} has no CUDA - speech will run on the processor "
            f"and the video memory features have nothing to work with")


def folder_size_mb(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total // (1024 * 1024)


def install_models(names: list[str]) -> int:
    """Download the selected models into models/, skipping ones already there."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return fail("huggingface_hub is not installed - run the dependency step first")

    problems = 0
    for name in names:
        if name not in MODEL_SPECS:
            say(f"  [!] unknown model '{name}' - known: {', '.join(MODEL_SPECS)}")
            problems += 1
            continue
        folder, repo, kwargs, title, size = MODEL_SPECS[name]
        target = MODELS / folder
        if target.is_dir() and any(target.iterdir()):
            say(f"  [+] {title}: already in models/{folder} ({folder_size_mb(target)} MB)")
            continue
        say(f"Downloading {title} ({size}) into models/{folder} ...")
        try:
            snapshot_download(repo, local_dir=str(target), **kwargs)
        except Exception as exc:                      # noqa: BLE001 - report, do not crash
            say(f"  [!] {title} failed: {type(exc).__name__}: {exc}")
            problems += 1
            continue
        say(f"  [+] {title}: {folder_size_mb(target)} MB")
    return 1 if problems else 0


def install_ffmpeg(archive: Path) -> int:
    """Unpack ffmpeg.exe/ffprobe.exe next to the project.

    src/stt_engine.py looks in <project>/ffmpeg/ before giving up on PATH, so
    nothing has to be added to the system PATH.
    """
    if not archive.is_file():
        return fail(f"ffmpeg archive not found: {archive}")
    out = ROOT / "ffmpeg"
    out.mkdir(parents=True, exist_ok=True)
    wanted = {"ffmpeg.exe", "ffprobe.exe"}
    found = set()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = Path(info.filename).name
            if name in wanted:
                with zf.open(info) as src, (out / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                found.add(name)
    if not found:
        return fail(f"no ffmpeg.exe or ffprobe.exe inside {archive.name}")
    if "ffprobe.exe" not in found:
        say("  [i] ffprobe.exe is missing from the archive - whisper timing may be off")
    say(f"  [+] ffmpeg installed into ffmpeg/ ({', '.join(sorted(found))})")
    return 0


def write_env() -> int:
    """Create .env from the template if it is not there yet."""
    env = ROOT / ".env"
    if env.is_file():
        say("  [+] .env already exists - left untouched")
        return 0
    template = ROOT / ".env.example"
    if not template.is_file():
        return fail(".env.example is missing, cannot create .env")
    shutil.copyfile(template, env)
    say(f"  [+] .env created from .env.example - open Settings to point it at your LLM")
    return 0


def doctor() -> int:
    """Report what is in place. Nothing is changed."""
    say(f"Project: {ROOT}")
    ok = True

    if VENV_PYTHON.is_file():
        proc = subprocess.run([str(VENV_PYTHON), "--version"], capture_output=True, text=True)
        say(f"  [+] venv: {proc.stdout.strip() or proc.stderr.strip()}")
        report_torch(str(VENV_PYTHON))
    else:
        say("  [-] venv: missing - speech and the assistant will not start")
        ok = False

    for name, (folder, _repo, _kw, title, size) in MODEL_SPECS.items():
        path = MODELS / folder
        if path.is_dir() and any(path.iterdir()):
            say(f"  [+] {title}: {folder_size_mb(path)} MB")
        else:
            say(f"  [-] {title}: not installed (models/{folder}, about {size})")

    ff = ROOT / "ffmpeg" / "ffmpeg.exe"
    say(f"  [{'+' if ff.is_file() else '-'}] ffmpeg: {ff if ff.is_file() else 'missing'}")
    env = ROOT / ".env"
    say(f"  [{'+' if env.is_file() else '-'}] .env: {'present' if env.is_file() else 'missing'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("deps", help="create the venv and install dependencies")
    sub.add_parser("env", help="create .env from the template")
    sub.add_parser("doctor", help="report what is installed, change nothing")

    p_models = sub.add_parser("models", help="download models")
    p_models.add_argument("names", nargs="+", choices=sorted(MODEL_SPECS))
    p_models.add_argument("--force", action="store_true",
                          help="download again even if the folder is not empty")

    p_ff = sub.add_parser("ffmpeg", help="unpack ffmpeg next to the project")
    p_ff.add_argument("--archive", required=True, type=Path)

    p_all = sub.add_parser("all", help="deps, env and the listed models")
    p_all.add_argument("--models", default="", help="comma separated: stt,tts,emb")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        return doctor()

    if args.command == "deps":
        return install_deps()

    if args.command == "env":
        return write_env()

    if args.command == "models":
        return install_models(args.names)

    if args.command == "ffmpeg":
        return install_ffmpeg(args.archive)

    if args.command == "all":
        result = install_deps()
        if result == 0:
            result = write_env()
        names = [n.strip() for n in args.models.split(",") if n.strip()]
        if names and result == 0:
            result = install_models(names)
        return result

    return 1


if __name__ == "__main__":
    sys.exit(main())