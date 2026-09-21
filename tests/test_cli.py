from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def invoke(*args: str, axi_python: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    env.pop("AXI_PYTHON", None)
    if axi_python is not None:
        env["AXI_PYTHON"] = axi_python
    return subprocess.run(
        [sys.executable, "-m", "hullrad_axi.entry", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_version_fast_path(self) -> None:
        for flag in ("-v", "-V", "--version"):
            result = invoke(flag)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "0.1.0\n")

    def test_bundled_engine_is_default(self) -> None:
        result = invoke()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("engine_status: ready", result.stdout)
        self.assertIn("HullRadV10.2.py", result.stdout)

    def test_fields_are_discoverable(self) -> None:
        result = invoke("fields")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("fields[25]{name,default,native_label}:", result.stdout)
        self.assertIn("translational_diffusion_cm2_s,true,Dt", result.stdout)
        self.assertIn("rotational_diffusion_s_1,true,Dr", result.stdout)
        help_result = invoke("run", "--help")
        self.assertIn("hullrad-axi fields", help_result.stdout)

    def test_missing_engine_override_does_not_fall_back(self) -> None:
        result = invoke("doctor", "--engine", "/definitely/not/HullRad.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--engine script does not exist", result.stdout)

    def test_doctor_structure_runs_calculation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "engine.py"
            engine.write_text("print('  Dt              :       8.00e-07   cm^2/s')\n")
            structure = root / "x.pdb"
            structure.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n")
            result = invoke("doctor", "--engine", str(engine), "--structure", str(structure))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("structure_test: passed", result.stdout)
            self.assertNotIn("help: Add --structure", result.stdout)

    def test_unknown_flag_is_structured_usage_error(self) -> None:
        result = invoke("run", "--wat")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stdout)
        self.assertIn("--wat", result.stdout)

        removed = invoke("doctor", "--python", sys.executable)
        self.assertEqual(removed.returncode, 2)
        self.assertIn("unrecognized argument: --python", removed.stdout)

    def test_fake_engine_run_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "engine.py"
            engine.write_text(
                "print('  #Amino Acids    :          123')\n"
                "print('  M               :        14000     g/mol')\n"
                "print('  Dt              :       8.00e-07   cm^2/s')\n"
                "print('  R(Translation)  :        26.00     Angstroms')\n"
                "print('  Dr              :       6.00e+06   s^-1')\n"
                "print('  R(Rotation)     :        29.00     Angstroms')\n"
            )
            structure = root / "x.pdb"
            structure.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n")
            out = root / "run"
            result = invoke("run", "--engine", str(engine), "--structure", str(structure), "--out-dir", str(out))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("status: ok", result.stdout)
            self.assertIn("translational_diffusion_cm2_s: 8e-7", result.stdout)
            self.assertTrue((out / "manifest.json").is_file())
            self.assertEqual((out / "input.pdb").read_bytes(), structure.read_bytes())
            manifest = json.loads((out / "manifest.json").read_text())
            self.assertEqual(manifest["tool_version"], "0.1.0")
            self.assertEqual(manifest["state"], "completed")
            self.assertEqual(manifest["returncode"], 0)

    def test_missing_python_is_structured(self) -> None:
        result = invoke("doctor", axi_python="/definitely/not/a/python")
        self.assertEqual(result.returncode, 1)
        self.assertIn("AXI_PYTHON interpreter", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_engine_traceback_is_translated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "engine.py"
            engine.write_text("raise RuntimeError('dependency exploded')\n")
            structure = root / "x.pdb"
            structure.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n")
            result = invoke("run", "--engine", str(engine), "--structure", str(structure))
            self.assertEqual(result.returncode, 1)
            self.assertIn("HullRad exited with code 1", result.stdout)
            self.assertNotIn("Traceback", result.stdout)
            self.assertNotIn("dependency exploded", result.stdout)

    def test_existing_output_directory_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            structure = root / "x.pdb"
            structure.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n")
            result = invoke("run", "--structure", str(structure), "--out-dir", str(root))
            self.assertEqual(result.returncode, 1)
            self.assertIn("output directory already exists", result.stdout)

    def test_unknown_field_is_usage_error_before_engine_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            structure = Path(tmp) / "x.pdb"
            structure.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n")
            result = invoke("run", "--structure", str(structure), "--fields", "not_a_field")
            self.assertEqual(result.returncode, 2)
            self.assertIn("unknown result fields", result.stdout)
            self.assertNotIn("engine was not found", result.stdout)

    def test_missing_expected_native_fields_is_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = root / "engine.py"
            engine.write_text("print('not HullRad output')\n")
            structure = root / "x.pdb"
            structure.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n")
            result = invoke("run", "--engine", str(engine), "--structure", str(structure))
            self.assertEqual(result.returncode, 1)
            self.assertIn("expected hydrodynamic result fields", result.stdout)
            self.assertNotIn("unexpected internal error", result.stdout)

    def test_batch_validates_all_structure_paths_before_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "launched"
            engine = root / "engine.py"
            engine.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('yes')\n")
            structure = root / "x.pdb"
            structure.write_text("ATOM      1  CA  ALA A   1       0.000   0.000   0.000\n")
            result = invoke(
                "batch",
                "--engine",
                str(engine),
                "--out-dir",
                str(root / "records"),
                str(structure),
                str(root / "missing.pdb"),
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
