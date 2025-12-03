"""Automate virtual environment creation and dependency installation.

This helper creates a Python virtual environment in ``.venv`` (or a custom
location) and installs the project's required dependencies. It works on both
Windows and POSIX platforms using only the Python standard library.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from venv import EnvBuilder

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"


def venv_paths(venv_dir: Path) -> tuple[Path, Path]:
    """Return the python and pip executables for a venv on any platform."""

    if sys.platform.startswith("win"):
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
    else:
        python_exe = venv_dir / "bin" / "python"
        pip_exe = venv_dir / "bin" / "pip"
    return python_exe, pip_exe


def ensure_venv(venv_dir: Path) -> tuple[Path, Path]:
    """Create the virtual environment if it doesn't exist."""

    if not venv_dir.exists():
        print(f"Creating virtual environment at {venv_dir} ...")
        EnvBuilder(with_pip=True).create(venv_dir)
    python_exe, pip_exe = venv_paths(venv_dir)
    if not python_exe.exists():
        raise RuntimeError(f"Virtual environment is missing Python at {python_exe}")
    return python_exe, pip_exe


def install_requirements(python_exe: Path, pip_exe: Path) -> None:
    """Install dependencies from requirements.txt using the venv's pip."""

    if not REQUIREMENTS.exists():
        raise FileNotFoundError(f"requirements.txt not found at {REQUIREMENTS}")

    print("Upgrading pip ...")
    subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    print(f"Installing dependencies from {REQUIREMENTS} ...")
    subprocess.run([str(pip_exe), "install", "-r", str(REQUIREMENTS)], check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--venv-path",
        type=Path,
        default=ROOT / ".venv",
        help="Directory to create/use for the virtual environment (default: .venv).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    venv_dir: Path = args.venv_path

    try:
        python_exe, pip_exe = ensure_venv(venv_dir)
        install_requirements(python_exe, pip_exe)
    except subprocess.CalledProcessError as exc:
        print(f"Dependency installation failed with exit code {exc.returncode}:")
        print(exc)
        return exc.returncode
    except Exception as exc:  # noqa: BLE001 (broad to surface install errors clearly)
        print(f"Setup failed: {exc}")
        return 1

    print("Setup complete. Activate the environment with:")
    if sys.platform.startswith("win"):
        print(f"  {venv_dir}\\Scripts\\activate")
    else:
        print(f"  source {venv_dir}/bin/activate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
