from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

FIELD_MAP = {
    "#Amino Acids": "amino_acids",
    "#Nucleotides": "nucleotides",
    "#Saccharides": "saccharides",
    "#Detergents": "detergents",
    "#PEG monomers": "peg_monomers",
    "M": "molecular_mass_g_mol",
    "v_bar": "partial_specific_volume_ml_g",
    "Ro(Anhydrous)": "anhydrous_radius_angstrom",
    "Rg(Anhydrous)": "gyration_radius_angstrom",
    "Dmax": "maximum_dimension_angstrom",
    "Axial Ratio": "axial_ratio",
    "f/fo": "frictional_ratio",
    "Dt": "translational_diffusion_cm2_s",
    "R(Translation)": "translational_radius_angstrom",
    "s20,w": "sedimentation_s",
    "Int. Viscosity": "intrinsic_viscosity_ml_g",
    "Total Hydration": "total_hydration_g_g",
    "Spc Vol Hyd Prot": "hydrated_specific_volume_ml_g",
    "ks(Non-ideal)": "ks_ml_g",
    "kd(Non-ideal)": "kd_ml_g",
    "Bex(2nd virial)": "excluded_volume_ml_g",
    "Asphericity": "asphericity",
    "Dr": "rotational_diffusion_s_1",
    "R(Rotation)": "rotational_radius_angstrom",
    "tauC": "correlation_time_ns",
}

AVAILABLE_FIELDS = tuple(dict.fromkeys(FIELD_MAP.values()))

DEFAULT_FIELDS = [
    "amino_acids",
    "molecular_mass_g_mol",
    "translational_diffusion_cm2_s",
    "translational_radius_angstrom",
    "rotational_diffusion_s_1",
    "rotational_radius_angstrom",
]


class HullRadFailure(RuntimeError):
    """A translated engine failure safe to expose through the AXI."""

    def __init__(self, message: str, help_text: str | None = None) -> None:
        super().__init__(message)
        self.help_text = help_text


def resolve_python() -> Path:
    """Use AXI_PYTHON when set, otherwise the active AXI interpreter."""
    override = os.environ.get("AXI_PYTHON")
    raw = override or sys.executable
    source = "AXI_PYTHON" if override else "installed Python"
    if os.sep in raw or (os.altsep and os.altsep in raw):
        candidate = Path(os.path.abspath(Path(raw).expanduser()))
    else:
        located = shutil.which(raw)
        if located is None:
            raise HullRadFailure(
                f"{source} interpreter was not found: {raw}",
                "Unset AXI_PYTHON to use the installed Python, or set it to an interpreter with NumPy and SciPy",
            )
        # Preserve a virtual environment's symlink path. Resolving it to the
        # base interpreter can change Python's prefix and hide installed packages.
        candidate = Path(os.path.abspath(located))
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise HullRadFailure(
            f"{source} interpreter is not executable: {candidate}",
            "Unset AXI_PYTHON to use the installed Python, or set it to an interpreter with NumPy and SciPy",
        )
    return candidate


def probe_python(timeout: float = 30.0) -> dict[str, object]:
    """Check the selected interpreter and HullRad's preferred convex-hull path."""
    python = resolve_python()
    try:
        completed = subprocess.run(
            [str(python), "-c", "import numpy; from scipy.spatial import ConvexHull"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HullRadFailure(
            f"selected Python interpreter could not complete its capability check: {type(exc).__name__}",
            "Unset or correct AXI_PYTHON, then rerun `hullrad-axi doctor`",
        ) from None
    return {
        "python": str(python),
        "python_convex_hull": "available" if completed.returncode == 0 else "unavailable",
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_engine(explicit: str | None) -> Path | None:
    for candidate, source in ((explicit, "--engine"), (os.environ.get("HULLRAD_SCRIPT"), "HULLRAD_SCRIPT")):
        if candidate:
            path = Path(candidate).expanduser().resolve()
            if not path.is_file():
                raise HullRadFailure(f"{source} script does not exist or is not a file: {path}")
            return path
    bundled = Path(__file__).resolve().parent / "data" / "HullRadV10.2.py"
    return bundled if bundled.is_file() else None


def parse_output(stdout: str) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    pattern = re.compile(r"^\s*(.*?)\s*:\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)")
    for line in stdout.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        label, token = match.groups()
        name = FIELD_MAP.get(label.strip())
        if not name:
            continue
        number = float(token)
        result[name] = int(number) if name in {"amino_acids", "nucleotides", "saccharides", "detergents", "peg_monomers"} else number
    return result


def run_hullrad(
    engine: Path,
    structure: Path,
    timeout: float = 300.0,
) -> dict[str, object]:
    resolved_python = resolve_python()
    started_unix = time.time()
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [str(resolved_python), str(engine), str(structure)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HullRadFailure(
            f"HullRad exceeded the {timeout:g} second timeout",
            "Increase --timeout or inspect the structure before retrying",
        ) from None
    except OSError as exc:
        raise HullRadFailure(
            f"HullRad could not be launched with the selected Python interpreter: {exc.strerror or type(exc).__name__}",
            "Check AXI_PYTHON and run `hullrad-axi doctor` with the same --engine value",
        ) from None
    duration = time.monotonic() - started
    if completed.returncode != 0:
        native = f"{completed.stderr}\n{completed.stdout}"
        if "qconvex" in native and ("No such file" in native or "FileNotFoundError" in native):
            raise HullRadFailure(
                "the selected Python interpreter lacks HullRad's Python convex-hull support, and this HullRad script's configured fallback executable is unavailable",
                "Unset or correct AXI_PYTHON, then rerun `hullrad-axi doctor --structure <PDB_OR_MMCIF>`",
            ) from None
        raise HullRadFailure(
            f"HullRad exited with code {completed.returncode} before producing results",
            "Run `hullrad-axi doctor --structure <PDB_OR_MMCIF>` with the same --engine value and AXI_PYTHON setting",
        )
    values = parse_output(completed.stdout)
    if "translational_diffusion_cm2_s" not in values:
        raise HullRadFailure(
            "HullRad completed but its expected hydrodynamic result fields were not found",
            "Verify that --engine points to a supported HullRad script and rerun `hullrad-axi doctor --structure <PDB_OR_MMCIF>`",
        )
    return {
        "values": values,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_seconds": duration,
        "started_unix": started_unix,
        "finished_unix": time.time(),
        "returncode": completed.returncode,
        "python": str(resolved_python),
    }


def inspect_structure(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix not in {".pdb", ".ent", ".cif", ".mmcif"}:
        raise ValueError("structure must be PDB or mmCIF")
    atoms = 0
    if suffix in {".pdb", ".ent"}:
        with path.open(errors="replace") as handle:
            atoms = sum(1 for line in handle if line.startswith(("ATOM  ", "HETATM")))
    return {
        "path": str(path),
        "format": "pdb" if suffix in {".pdb", ".ent"} else "mmcif",
        "bytes": path.stat().st_size,
        "coordinate_records": atoms if atoms else None,
        "sha256": sha256(path),
    }
