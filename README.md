# hullrad-axi

`hullrad-axi` is an [Agent eXperience Interface](https://axi.md/) for estimating
hydrodynamic properties from a PDB or mmCIF structure. It runs
[HullRad 10.2](https://github.com/fleming12/hullrad.github.io) and returns
compact [TOON](https://toonformat.dev/) output. The package
includes the unmodified HullRad script and its NumPy and SciPy dependencies.

## Install

```sh
npm install -g --install-links --allow-scripts=github:davenovelli-pnnl/hullrad-axi github:davenovelli-pnnl/hullrad-axi
hullrad-axi --version
```

`--install-links` makes npm copy the GitHub package instead of linking a
temporary checkout. `--allow-scripts` explicitly permits this GitHub package's
Python setup script, so npm does not issue an unreviewed-script warning.

Requires Node 20+ and network access during installation. The installer checks
a pinned uv download from Astral, then uv provisions Python 3.11 and installs
the package in an isolated environment. A system Python installation is not
required, even if the machine has an older Python. The supported targets are
64-bit macOS, Windows, and Linux on x64 or ARM64. No separate HullRad download
is needed.

## Commands

```sh
hullrad-axi doctor [--structure <pdb-or-cif>] [--engine <script>] [--timeout <seconds>]
hullrad-axi inspect --structure <pdb-or-cif>
hullrad-axi fields
hullrad-axi run --structure <pdb-or-cif> [--out-dir <new-dir>] [--fields <names|all>] [--show-native]
hullrad-axi batch --out-dir <new-dir> <structure...> [--fields <names|all>] [--show-native]
```

Run `hullrad-axi <command> --help` for the complete flag reference.
`doctor`, `run`, and `batch` use the AXI's installed Python unless
`AXI_PYTHON` names another interpreter. The override must have NumPy and SciPy.

### doctor

Checks the bundled engine and installed Python environment. With `--structure`, it also
runs a complete calculation on that PDB or mmCIF file. The structure is supplied
by the caller; sample structures are not shipped with the package.

Flags: `--structure <file>`, `--engine <script>` to override bundled HullRad,
and `--timeout <seconds>` (default `300`) for the calculation test. `doctor`
reports which interpreter it checked.

```sh
hullrad-axi doctor
hullrad-axi doctor --structure protein.pdb
```

### inspect

Reports a structure's path, format, size, SHA-256 hash, and PDB coordinate-record
count. It does not run HullRad. Flag: required `--structure <file>`.

```sh
hullrad-axi inspect --structure protein.cif
```

### fields

Lists every result key accepted by `--fields`, marks the default keys, and
shows the corresponding native HullRad label. It takes no flags.

```sh
hullrad-axi fields
```

### run

Calculates one structure. Flag: required `--structure <file>`; optional
`--out-dir <new-dir>` to preserve an input snapshot, native logs, normalized
results, and a JSON manifest; `--fields <names|all>` to select TOON result fields;
`--show-native` to mirror native output to standard error; `--engine <script>`;
and `--timeout <seconds>` (default `300`). The default
fields are amino-acid count, molecular mass, and translational and rotational
diffusion coefficients and radii.

For `--fields`, `names` means comma-separated result keys, such as
`--fields molecular_mass_g_mol,translational_diffusion_cm2_s`. This selects
which keys appear in TOON output; it does not change the output format.
`--fields all` includes every parsed result available for that structure. The
six default keys are `amino_acids`, `molecular_mass_g_mol`, `translational_diffusion_cm2_s`,
`translational_radius_angstrom`, `rotational_diffusion_s_1`, and
`rotational_radius_angstrom`. Run `hullrad-axi fields` to see the full list.

```sh
hullrad-axi run --structure protein.pdb
hullrad-axi run --structure protein.cif --out-dir records/protein --fields all
```

### batch

Runs each supplied structure in sequence and creates a separate record under
the required new `--out-dir <dir>`. Positional arguments are one or more PDB or
mmCIF paths. Optional flags: `--fields <names|all>` as described above,
`--show-native`, `--engine <script>`, and `--timeout <seconds>` (default `300`
per structure).

```sh
hullrad-axi batch --out-dir records/screen structures/a.pdb structures/b.cif
```

## Output

Standard output, including errors, is TOON. Exit codes are `0` for success,
`1` for errors, and `2` for usage errors. Record directories must be new;
existing records are never overwritten. The manifest records the structure and
engine hashes, results, runtime, and selected Python interpreter.

## Uninstall

```sh
npm uninstall -g hullrad-axi
```

This removes the command, the package, and its package-local uv and Python
environments. No uninstall script is needed.

## Development

```sh
python -m unittest discover -s tests
```

## License and citation

The AXI wrapper is MIT licensed; see `LICENSE`. The bundled HullRad 10.2 script
is dedicated to the public domain under the Unlicense text in its header. See
`THIRD_PARTY_NOTICES.md` for its exact source and hash.

Fleming, P.J., and Fleming, K.G. "HullRad: Fast Calculations of Folded and
Disordered Protein and Nucleic Acid Hydrodynamic Properties." *Biophysical
Journal* **114** (2018), 856–869. DOI: 10.1016/j.bpj.2018.01.002.
