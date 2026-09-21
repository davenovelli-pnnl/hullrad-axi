from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from .engine import (
    AVAILABLE_FIELDS,
    DEFAULT_FIELDS,
    FIELD_MAP,
    HullRadFailure,
    discover_engine,
    inspect_structure,
    probe_python,
    run_hullrad,
    sha256,
)
from .toon import dumps
from .version import VERSION


class Formatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


class Parser(argparse.ArgumentParser):
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("formatter_class", Formatter)
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:
        usage = self.format_usage().removeprefix("usage: ").strip()
        print(dumps({"error": message, "help": f"Valid usage: {usage}"}))
        raise SystemExit(2)


def emit(value: dict[str, object]) -> None:
    print(dumps(value))


def reject_unknown_flags(parser: Parser, argv: list[str]) -> None:
    selected: argparse.ArgumentParser = parser
    remaining = argv
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction) and argv and argv[0] in action.choices:
            selected = action.choices[argv[0]]
            remaining = argv[1:]
            break
    valid = {flag for action in selected._actions for flag in action.option_strings}
    for token in remaining:
        if token == "--":
            break
        flag = token.split("=", 1)[0]
        if flag.startswith("-") and not re.fullmatch(r"-\d+(?:\.\d+)?", flag) and flag not in valid:
            selected.error(f"unrecognized argument: {flag}")


def fail(message: str, help_text: str | None = None, code: int = 1) -> None:
    payload: dict[str, object] = {"error": message}
    if help_text:
        payload["help"] = help_text
    emit(payload)
    raise SystemExit(code)


def _path(raw: str, label: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        fail(f"{label} does not exist or is not a file: {path}")
    return path


def _engine(args: argparse.Namespace) -> Path:
    try:
        engine = discover_engine(args.engine)
    except HullRadFailure as exc:
        fail(str(exc), exc.help_text)
    if engine is None:
        fail("bundled HullRad engine was not found", "Reinstall hullrad-axi or pass --engine PATH")
    return engine


def _selected(values: dict[str, object], fields: str) -> dict[str, object]:
    names = list(values) if fields == "all" else [item.strip() for item in fields.split(",") if item.strip()]
    unknown = [name for name in names if name not in values]
    if unknown:
        fail(f"unknown or unavailable result fields: {', '.join(unknown)}")
    return {name: values[name] for name in names}


def validate_fields(raw: str) -> None:
    if raw == "all":
        return
    names = [item.strip() for item in raw.split(",") if item.strip()]
    if not names:
        fail("--fields must name at least one result field or use all", code=2)
    unknown = [name for name in names if name not in AVAILABLE_FIELDS]
    if unknown:
        fail(
            f"unknown result fields: {', '.join(unknown)}",
            f"Valid fields: {', '.join(AVAILABLE_FIELDS)}, all",
            code=2,
        )


def display_bin() -> str:
    path = Path(os.path.abspath(Path(os.environ.get("AXI_COMMAND_PATH", sys.argv[0])).expanduser()))
    try:
        return str(Path("~") / path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def _run_one(args: argparse.Namespace, structure: Path, out_dir: Path | None) -> dict[str, object]:
    engine = _engine(args)
    try:
        result = run_hullrad(engine, structure, timeout=args.timeout)
    except HullRadFailure as exc:
        fail(f"HullRad calculation failed: {exc}", exc.help_text)
    if args.show_native:
        sys.stderr.write(str(result["stdout"]))
        sys.stderr.write(str(result["stderr"]))
    values = result["values"]
    assert isinstance(values, dict)
    record: dict[str, object] = {
        "status": "ok",
        "structure": str(structure),
        "duration_seconds": round(float(result["duration_seconds"]), 6),
        **_selected(values, args.fields),
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=False)
        snapshot = out_dir / f"input{structure.suffix.lower()}"
        shutil.copyfile(structure, snapshot)
        (out_dir / "hullrad.stdout.txt").write_text(str(result["stdout"]))
        (out_dir / "hullrad.stderr.txt").write_text(str(result["stderr"]))
        manifest = {
            "schema_version": 1,
            "tool_version": VERSION,
            "state": "completed",
            "engine": str(engine),
            "engine_sha256": sha256(engine),
            "structure": str(structure),
            "structure_sha256": sha256(structure),
            "structure_snapshot": str(snapshot),
            "python": result["python"],
            "duration_seconds": result["duration_seconds"],
            "started_unix": result["started_unix"],
            "finished_unix": result["finished_unix"],
            "returncode": result["returncode"],
            "results": values,
        }
        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        record["run_dir"] = str(out_dir.resolve())
    return record


def build_parser() -> Parser:
    parser = Parser(prog="hullrad-axi", description="Run bundled HullRad with compact, reproducible outputs")
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser(
        "doctor",
        help="Check engine availability",
        epilog="Environment: AXI_PYTHON overrides the installed interpreter.\nExamples:\n  hullrad-axi doctor\n  hullrad-axi doctor --structure protein.pdb",
    )
    doctor.add_argument("--engine", help="Override the bundled HullRad Python script")
    doctor.add_argument("--structure", help="Optional PDB or mmCIF for a complete calculation test")
    doctor.add_argument("--timeout", type=float, default=300.0, help="Calculation test timeout in seconds")

    inspect = sub.add_parser(
        "inspect",
        help="Inspect a structure without calculation",
        epilog="Examples:\n  hullrad-axi inspect --structure protein.pdb\n  hullrad-axi inspect --structure assembly.cif",
    )
    inspect.add_argument("--structure", required=True, help="PDB or mmCIF structure path")

    sub.add_parser(
        "fields",
        help="List result keys accepted by --fields",
        epilog="Use these names with `hullrad-axi run --fields name1,name2` or `--fields all`.",
    )

    run = sub.add_parser(
        "run",
        help="Run one HullRad calculation",
        epilog="Environment: AXI_PYTHON overrides the installed interpreter.\nRun `hullrad-axi fields` to list result keys.\nExamples:\n  hullrad-axi run --structure protein.pdb\n  hullrad-axi run --structure protein.cif --out-dir records/protein --show-native",
    )
    run.add_argument("--structure", required=True, help="PDB or mmCIF structure path")
    run.add_argument("--engine", help="Override the bundled HullRad Python script")
    run.add_argument("--out-dir", help="New directory for native logs and manifest")
    run.add_argument("--timeout", type=float, default=300.0, help="Calculation timeout in seconds")
    run.add_argument("--fields", default=",".join(DEFAULT_FIELDS), help="Comma-separated result fields or all")
    run.add_argument("--show-native", action="store_true", help="Mirror native output to stderr")

    batch = sub.add_parser(
        "batch",
        help="Run multiple structures sequentially",
        epilog="Environment: AXI_PYTHON overrides the installed interpreter.\nRun `hullrad-axi fields` to list result keys.\nExamples:\n  hullrad-axi batch --out-dir records proteins/*.pdb\n  hullrad-axi batch --out-dir records --fields all a.pdb b.cif",
    )
    batch.add_argument("structures", nargs="+", help="PDB or mmCIF structure paths")
    batch.add_argument("--engine", help="Override the bundled HullRad Python script")
    batch.add_argument("--out-dir", required=True, help="Parent directory for per-structure records")
    batch.add_argument("--timeout", type=float, default=300.0, help="Per-calculation timeout in seconds")
    batch.add_argument("--fields", default=",".join(DEFAULT_FIELDS), help="Comma-separated result fields or all")
    batch.add_argument("--show-native", action="store_true", help="Mirror native output to stderr")
    return parser


def home() -> None:
    try:
        engine = discover_engine(None)
    except HullRadFailure as exc:
        fail(str(exc), exc.help_text)
    emit({
        "bin": display_bin(),
        "description": "Calculate protein hydrodynamic estimates with bundled HullRad",
        "engine_status": "ready" if engine else "not_configured",
        "engine": str(engine) if engine else None,
        "help": "Run `hullrad-axi fields` to list result keys or `hullrad-axi doctor --structure <PDB_OR_MMCIF>` to check a calculation",
    })


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        home()
        return
    parser = build_parser()
    reject_unknown_flags(parser, argv)
    args = parser.parse_args(argv)
    if args.command == "doctor":
        if args.timeout <= 0:
            fail("--timeout must be positive", code=2)
        engine = _engine(args)
        try:
            python_report = probe_python(min(args.timeout, 30.0))
        except HullRadFailure as exc:
            fail(str(exc), exc.help_text)
        payload: dict[str, object] = {
            "status": "ready" if engine else "not_configured",
            "engine": str(engine) if engine else None,
            **python_report,
        }
        if engine is not None and python_report["python_convex_hull"] == "unavailable" and not args.structure:
            payload["status"] = "unverified"
            payload["help"] = (
                "Unset AXI_PYTHON to use the installed Python, or install NumPy and SciPy in the selected interpreter"
                if os.environ.get("AXI_PYTHON")
                else "Reinstall hullrad-axi to restore NumPy and SciPy, or add --structure to test the engine"
            )
        if args.structure:
            if engine is None:
                fail("cannot test a structure because HullRad engine was not found", "Pass --engine PATH")
            structure = _path(args.structure, "structure")
            try:
                calculation = run_hullrad(engine, structure, timeout=args.timeout)
            except HullRadFailure as exc:
                fail(f"HullRad calculation test failed: {exc}", exc.help_text)
            payload["structure_test"] = "passed"
            payload["status"] = "ready"
            payload["duration_seconds"] = round(float(calculation["duration_seconds"]), 6)
        emit(payload)
    elif args.command == "fields":
        emit({
            "fields": [
                {"name": name, "default": name in DEFAULT_FIELDS, "native_label": native}
                for native, name in FIELD_MAP.items()
            ],
            "help": "Use --fields name1,name2 or --fields all with `hullrad-axi run` or `hullrad-axi batch`",
        })
    elif args.command == "inspect":
        structure = _path(args.structure, "structure")
        try:
            emit({"structure": inspect_structure(structure)})
        except ValueError as exc:
            fail(str(exc))
    elif args.command == "run":
        if args.timeout <= 0:
            fail("--timeout must be positive", code=2)
        validate_fields(args.fields)
        structure = _path(args.structure, "structure")
        out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
        if out_dir is not None and out_dir.exists():
            fail(f"output directory already exists: {out_dir}")
        emit(_run_one(args, structure, out_dir))
    elif args.command == "batch":
        if args.timeout <= 0:
            fail("--timeout must be positive", code=2)
        validate_fields(args.fields)
        base = Path(args.out_dir).expanduser().resolve()
        if base.exists():
            fail(f"output directory already exists: {base}")
        structures = [_path(raw, "structure") for raw in args.structures]
        rows: list[dict[str, object]] = []
        for index, structure in enumerate(structures, start=1):
            rows.append(_run_one(args, structure, base / f"{index:04d}-{structure.stem}"))
        emit({"count": len(rows), "results": rows})
    else:
        parser.error("a command is required")
