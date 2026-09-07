```python
claude_md_content = """# CLAUDE.md - OpenBiomech (Open-Source Visual3D & Mokka Alternative)

## 1. Project Overview & High-Level Architecture
OpenBiomech is an ultra-high-performance, cross-platform (Linux, macOS Apple Silicon / Intel) biomechanical analysis engine and 3D visualization suite designed as an open-source, reproducible alternative to C-Motion Visual3D and BTK Mokka.

The system is decoupled into four modular layers:
1. **Core Data Structures & Binary I/O Engine**: High-throughput zero-copy parser/writer for standard biomechanical formats (.c3d, .csv, .trc, .mot, .anc).
2. **Computational Biomechanics Engine**: Numerically stable linear algebra, dual-pass filtering, rigid-body 6DoF tracking, ISB Joint Coordinate Systems (JCS), recursive Newton-Euler inverse dynamics, and anthropometric segment modeling.
3. **Hardware-Accelerated 3D Viewport & UI**: Cross-platform rendering via `wgpu` (Metal on macOS, Vulkan on Linux) paired with an immediate-mode UI (`egui` or `Qt6/cxx-qt`) and high-fps synchronized 2D telemetry plotting.
4. **Automation, Scripting & IPC Pipeline**: Direct Python bindings via `PyO3` / `maturin` allowing batch CLI processing matching Visual3D pipeline scripts (`.v3s`) and interoperability with scientific Python (NumPy, SciPy, Polars).

### Modular Workspace Directory Structure
```text
openbiomech/
├── Cargo.toml                     # Cargo workspace definition
├── CLAUDE.md                      # AI coding instructions and conventions
├── LICENSE-APACHE / LICENSE-MIT
├── README.md
├── crates/
│   ├── c3d-io/                    # Binary C3D parser/writer (IEEE Little-Endian, DEC VAX, Big-Endian)
│   │   ├── src/
│   │   │   ├── header.rs          # 512-byte block 1 header decoding
│   │   │   ├── parameters.rs      # Parameter blocks (Groups, Items, Dimensions)
│   │   │   ├── data_blocks.rs     # 3D points (Real/Int16) & analog multichannel frames
│   │   │   ├── vax.rs             # DEC VAX floating-point converter
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── biomech-math/              # Core kinematics, filters, and linear algebra
│   │   ├── src/
│   │   │   ├── filtering.rs       # 4th order zero-lag Butterworth, GCVSPL splines
│   │   │   ├── rigid_body.rs      # SVD / Kabsch-Umeyama optimal registration algorithm
│   │   │   ├── quaternions.rs     # Unit quaternion continuous orientation & SLERP
│   │   │   ├── euler_angles.rs    # Cardan/Euler decomposition (ZXY, XYZ, YXZ, etc.)
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── biomech-model/             # Segmental model, landmarks, and anthropometry
│   │   ├── src/
│   │   │   ├── segment.rs         # Rigid segment definition (ACS, TCS, mass, CoM, inertia tensor)
│   │   │   ├── landmark.rs        # Static/dynamic calibration landmarks & virtual targets
│   │   │   ├── isb_joints.rs      # ISB standards (Pelvis, Hip, Knee, Ankle, Spine, Shoulder, Elbow, Wrist)
│   │   │   ├── bsp.rs             # Body Segment Parameters (Dempster, de Leva, Dumas)
│   │   │   ├── events.rs          # Gait event detection (Heel Strike, Toe Off via GRF / kinematics)
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── inverse-dynamics/          # Force plate calibration, COP, and kinetic calculations
│   │   ├── src/
│   │   │   ├── force_plate.rs     # Force platform types 1, 2 (6x6 matrix), 3, 4, 5
│   │   │   ├── cop.rs             # Center of pressure and Free Moment computation
│   │   │   ├── newton_euler.rs    # Recursive bottom-up/top-down 3D Newton-Euler equations
│   │   │   ├── joint_power.rs     # 3D joint power (P = M · omega) and energetic work
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── viewer-core/               # wgpu rendering pipelines and 3D scene graph
│   │   ├── src/
│   │   │   ├── camera.rs          # Arcball / Orbit 3D camera with view projections
│   │   │   ├── pipeline_points.rs # Instanced sphere rendering for 3D trajectory markers
│   │   │   ├── pipeline_vectors.rs# Dynamic arrows for GRF, segment axes, and COP
│   │   │   ├── pipeline_mesh.rs   # Bone geometries and segmental reference meshes
│   │   │   ├── pipeline_grid.rs   # Calibrated ground planes and force plate bounding boxes
│   │   │   └── lib.rs
│   ├── gui-app/                   # Desktop frontend (egui or cxx-qt)
│   │   ├── src/
│   │   │   ├── transport.rs       # Timeline playback, scrub, looping, sub-frame interpolation
│   │   │   ├── plots.rs           # Real-time multi-channel 2D graph plots synchronized to 3D
│   │   │   ├── model_tree.rs      # Interactive segment hierarchy and marker assignment
│   │   │   └── main.rs
│   └── pipeline-cli/              # Headless CLI for batch execution of automated scripts
│       └── src/main.rs
├── py-openbiomech/                 # High-level Python package via PyO3
│   ├── Cargo.toml
│   ├── pyproject.toml
│   └── src/lib.rs
└── tests/
    └── fixtures/                  # Real-world validation C3D files (Vicon, Qualisys, Charnwood)

```

---

## 2. Essential Development Commands

### Toolchain & Dependencies

* **Rust**: Rust 1.80+ (stable).
* **Package Management**: `uv` for Python environments and `cargo` for Rust.
* **macOS Prerequisites**: Xcode Command Line Tools (`xcode-select --install`).
* **Linux Prerequisites**: `libxcb`, `libxkbcommon`, `vulkan-loader`, `libasound2-dev`, `pkg-config`.

### Compilation & Build

```bash
# Debug compilation for all crates
cargo build --workspace

# Optimized release build with native CPU vectorization (AVX2 / NEON)
RUSTFLAGS="-C target-cpu=native" cargo build --workspace --release

# Rapid type check and syntax verification across the workspace
cargo check --workspace --all-targets --all-features

```

### Testing, Benchmarking & Validation

```bash
# Run all unit and integration tests across all workspace crates
cargo test --workspace

# Run math-specific tests with detailed stdout
cargo test -p biomech-math -- --nocapture

# Run Criterion benchmarks for high-throughput routines (SVD, C3D streaming, Newton-Euler)
cargo bench --workspace

# Validate numerical parity against baseline C3D datasets
cargo test --test integration_visual3d_validation

```

### Linting & Formatting Enforcement

```bash
# Strict clippy linting (zero warnings permitted in CI)
cargo clippy --workspace --all-targets --all-features -- -D warnings

# Code formatting compliance
cargo fmt --all -- --check

```

### Python Bindings (Maturin + uv)

```bash
# Initialize isolated Python environment
uv venv
source .venv/bin/activate

# Build and install PyO3 extension in editable development mode
uv run maturin develop -m py-openbiomech/Cargo.toml --release

# Run Python integration test suite
uv run pytest tests/python/

```

---

## 3. Mathematical & Biomechanical Standards

Implementations MUST adhere to international standards (International Society of Biomechanics - ISB) and formal analytical formulations.

### 3.1. Coordinate System & Triad Conventions

1. **Right-Handed Orthogonal System**: All global systems and local segment coordinate systems (SCS) must satisfy:

$$\mathbf{e}_x \times \mathbf{e}_y = \mathbf{e}_z, \quad \Vert{}\mathbf{e}_x\Vert{} = \Vert{}\mathbf{e}_y\Vert{} = \Vert{}\mathbf{e}_z\Vert{} = 1$$


2. **ISB Standard Axes Assignment**:
* $\mathbf{Z}$: Longitudinal / Superior axis directed proximally.
* $\mathbf{X}$: Anteroposterior axis directed anteriorly (or laterally depending on specific joint standard, e.g., ISB Knee vs Hip).
* $\mathbf{Y}$: Mediolateral axis directed laterally/medially according to the specific ISB segment specification.


3. **Unit Quaternions for Singularity-Free Rotations**:
Orientation must be maintained as unit quaternions $\mathbf{q} = [w, x, y, z]^T \in \mathbb{H}, \Vert{}\mathbf{q}\Vert{} = 1$.
Conversion to Cardan/Euler angles must occur strictly as an extraction step to avoid gimbal lock during intermediate tracking.

### 3.2. 6DoF Rigid Body Optimal Registration (Kabsch-Umeyama SVD)

For each frame, determine optimal rotation matrix $\mathbf{R} \in \mathrm{SO}(3)$ and translation vector $\mathbf{p} \in \mathbb{R}^3$ aligning technical cluster markers $\mathbf{x}_i^{\text{local}}$ to measured 3D trajectories $\mathbf{y}_i^{\text{global}}$ ($i = 1, \dots, N$):

1. Compute centroids:

$$\mathbf{c}_x = \frac{1}{N} \sum_{i=1}^N \mathbf{x}_i^{\text{local}}, \quad \mathbf{c}_y = \frac{1}{N} \sum_{i=1}^N \mathbf{y}_i^{\text{global}}$$


2. Construct centered cross-covariance dispersion matrix:

$$\mathbf{H} = \sum_{i=1}^N (\mathbf{x}_i^{\text{local}} - \mathbf{c}_x) (\mathbf{y}_i^{\text{global}} - \mathbf{c}_y)^T$$


3. Perform Singular Value Decomposition (SVD):

$$\mathbf{H} = \mathbf{U} \mathbf{\Sigma} \mathbf{V}^T$$


4. Compute rotation matrix ensuring proper rotation ($\det(\mathbf{R}) = +1$):

$$\mathbf{d} = \begin{bmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & \det(\mathbf{V}\mathbf{U}^T) \end{bmatrix}, \quad \mathbf{R} = \mathbf{V} \mathbf{d} \mathbf{U}^T$$


5. Compute translation vector:

$$\mathbf{p} = \mathbf{c}_y - \mathbf{R} \mathbf{c}_x$$



### 3.3. Joint Coordinate System (JCS) Kinematics

Joint kinematics must follow Grood & Suntay / ISB parameterization:

* Proximal coordinate system $\mathbf{P} = [\mathbf{e}_1, \mathbf{e}_2, \mathbf{e}_3]$, Distal coordinate system $\mathbf{D} = [\mathbf{f}_1, \mathbf{f}_2, \mathbf{f}_3]$.
* Proximal axis: $\mathbf{e}_{\text{flex}} = \mathbf{e}_1$.
* Distal axis: $\mathbf{e}_{\text{rot}} = \mathbf{f}_3$.
* Floating axis (perpendicular to both):

$$\mathbf{e}_{\text{float}} = \frac{\mathbf{e}_{\text{flex}} \times \mathbf{e}_{\text{rot}}}{\Vert{}\mathbf{e}_{\text{flex}} \times \mathbf{e}_{\text{rot}}\Vert{}}$$


* Joint angular velocity vector:

$$\boldsymbol{\omega}_{\text{joint}} = \dot{\alpha} \mathbf{e}_{\text{flex}} + \dot{\beta} \mathbf{e}_{\text{float}} + \dot{\gamma} \mathbf{e}_{\text{rot}}$$



### 3.4. Signal Processing & Numerical Differentiation

1. **Butterworth Dual-Pass Filter**:
* 4th-order low-pass digital filter.
* Forward-backward zero-phase lag filtering ($f_{\text{effective}} = \frac{f_c}{(2^{1/n} - 1)^{1/4}}$ cut-off adjustment).


2. **GCVSPL (Generalized Cross-Validatory Splines)**:
* Cubic or quintic smoothing splines to produce continuous, smooth first ($\mathbf{v}, \boldsymbol{\omega}$) and second ($\mathbf{a}, \dot{\boldsymbol{\omega}}$) derivatives directly without amplification of high-frequency digitizing noise.



### 3.5. Force Plate Mechanics & Center of Pressure (COP)

Support Type 1, 2, 3, 4, 5 platforms.
For standard Hall-effect or strain-gauge type platforms (Type 2 with $6 \times 6$ calibration matrix $\mathbf{C}$):

1. Compute channel forces and moments from raw voltage signals:

$$\mathbf{F}_{\text{raw}} = \mathbf{C} \cdot \mathbf{V}_{\text{analog}}$$


2. Correct moments for geometric sensor origin offset $(x_0, y_0, z_0)$:

$$M_x' = M_x + F_y \cdot z_0 - F_z \cdot y_0$$


$$M_y' = M_y - F_x \cdot z_0 + F_z \cdot x_0$$


3. Calculate instantaneous Center of Pressure (COP) in platform coordinates:

$$x_{\text{cop}} = \frac{-M_y'}{F_z}, \quad y_{\text{cop}} = \frac{M_x'}{F_z}, \quad z_{\text{cop}} = 0$$


4. Vertical Ground Reaction Force Threshold:
If $F_z < F_{\text{threshold}}$ (default: $15.0\,\text{N}$), set $\mathrm{COP} = \mathbf{0}$, $\mathbf{F} = \mathbf{0}$, and $\mathbf{M} = \mathbf{0}$ to eliminate non-contact singularities.
5. Transform COP and reaction forces from local plate coordinates to the global 3D laboratory coordinate system using the 4 corner calibration parameters (`CORNERS`).

### 3.6. 3D Inverse Dynamics (Recursive Newton-Euler)

Executed recursively from distal to proximal segment:

1. **Linear Momentum Balance**:

$$\mathbf{F}_{\text{proximal}} = m_i (\mathbf{a}_{\text{com}, i} - \mathbf{g}) - \mathbf{F}_{\text{distal}}$$



where $\mathbf{g} = [0, 0, -9.80665]^T\,\text{m/s}^2$.
2. **Angular Momentum Balance**:

$$\mathbf{M}_{\text{proximal}} = \mathbf{I}_i \dot{\boldsymbol{\omega}}_i + \boldsymbol{\omega}_i \times (\mathbf{I}_i \boldsymbol{\omega}_i) - \mathbf{M}_{\text{distal}} - (\mathbf{r}_{\text{distal}} \times \mathbf{F}_{\text{distal}}) - (\mathbf{r}_{\text{proximal}} \times \mathbf{F}_{\text{proximal}})$$



where:
* $\mathbf{I}_i = \mathbf{R}_i \mathbf{I}_{i, \text{local}} \mathbf{R}_i^T$ is the instantaneous inertia tensor in the global frame.
* $\mathbf{r}_{\text{proximal}} = \mathbf{p}_{\text{joint, prox}} - \mathbf{p}_{\text{com}, i}$.
* $\mathbf{r}_{\text{distal}} = \mathbf{p}_{\text{joint, dist}} - \mathbf{p}_{\text{com}, i}$.


3. **Joint Power**:

$$P_{\text{joint}} = \mathbf{M}_{\text{joint}} \cdot (\boldsymbol{\omega}_{\text{distal}} - \boldsymbol{\omega}_{\text{proximal}})$$



---

## 4. C3D File Format Specification & Parsing Rules

The C3D format consists of raw 512-byte blocks. The parser must guarantee zero-copy performance where feasible and handle historical format anomalies.

### 4.1. Header Block (Block 1)

* **Byte 1**: Pointer to first parameter block (typically 2).
* **Byte 2**: Magic key `0x50` (decimal 80).
* **Word 2 (Bytes 3-4)**: Number of 3D points per frame ($N_{\text{points}}$).
* **Word 3 (Bytes 5-6)**: Total analog measurements per 3D frame ($N_{\text{analog\_samples}} = N_{\text{channels}} \times N_{\text{subsamples}}$).
* **Word 4 (Bytes 7-8)**: 1-based index of first frame.
* **Word 5 (Bytes 9-10)**: 1-based index of last frame.
* **Word 6 (Bytes 11-12)**: Maximum interpolation gap.
* **Words 7-8 (Bytes 13-16)**: 3D scale factor (floating point):
* `scale < 0.0`: 3D points are stored as 32-bit floating-point numbers.
* `scale > 0.0`: 3D points are stored as 16-bit signed integers; coordinates must be scaled by $\vert\text{scale}\vert$.


* **Word 9 (Bytes 17-18)**: Pointer to starting 512-byte block of 3D/analog data.
* **Word 10 (Bytes 19-20)**: Number of analog samples per video frame ($N$).
* **Words 11-12 (Bytes 21-24)**: Frame rate (video sample frequency in Hz, float).

### 4.2. Processor Architecture Flags

Found at Byte 4 of the first parameter block (Header of Parameter Section):

* **Processor 84 (`0x54`)**: Intel Little-Endian (Standard IEEE-754 Float).
* **Processor 85 (`0x55`)**: DEC VAX (VAX F-Float / D-Float format: Sign bit, 8-bit exponent with bias 128, 23-bit mantissa with swapped 16-bit words).
* **Processor 86 (`0x56`)**: MIPS / Sun Big-Endian (IEEE-754 Float, byte-swapped).

The parser must detect and decode DEC VAX bit-patterns without relying on hardware VAX emulation:

```rust
pub fn vax_to_ieee_f32(vax_bits: u32) -> f32 {
    let word0 = (vax_bits & 0xFFFF) as u16;
    let word1 = ((vax_bits >> 16) & 0xFFFF) as u16;
    if word0 == 0 { return 0.0; }
    let sign = (word0 >> 15) & 0x01;
    let exponent = (word0 >> 7) & 0xFF;
    let fraction = (((word0 & 0x7F) as u32) << 16) | (word1 as u32);
    if exponent == 0 && sign == 0 { return 0.0; }
    let ieee_exp = (exponent as i32) - 128 + 127 - 1;
    let ieee_bits = ((sign as u32) << 31) | ((ieee_exp as u32) << 23) | fraction;
    f32::from_bits(ieee_bits)
}

```

### 4.3. Data Storage Layout

* Struct-of-Arrays (SoA) layout in memory:
* Markers: `x: Vec<f32>`, `y: Vec<f32>`, `z: Vec<f32>`, `residual: Vec<f32>`, `camera_mask: Vec<u16>` to enable contiguous AVX-512/NEON vectorization.
* Analog: contiguous buffer flattened as `[Frame][Subsample][Channel]`.



---

## 5. Code Style & Engineering Guidelines

### 5.1. Rust Idioms & Safety

1. **Zero Unchecked Panics**: No calls to `unwrap()`, `expect()`, or array slicing with bare brackets in library crates. Always propagate errors using a custom typed enum:
```rust
#[derive(thiserror::Error, Debug)]
pub enum BiomechError {
    #[error("Invalid C3D header: {0}")]
    InvalidHeader(String),
    #[error("Singular matrix encountered in SVD registration")]
    SingularMatrix,
    #[error("Analog channel mismatch: expected {expected}, found {found}")]
    ChannelMismatch { expected: usize, found: usize },
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}

```


2. **Precision Discipline**:
* Intermediate kinematics, SVD decompositions, and numerical integration must use `f64`.
* Downcast to `f32` exclusively when packing vertex/instance buffers for `wgpu` rendering.


3. **Allocation Rules**:
* Zero heap allocations inside per-frame processing loops.
* Pre-allocate frame buffers using arena or scratchpad memory (`Vec::with_capacity`).



### 5.2. Testing & Parity Verification

1. **Unit Tests**:
* Every mathematical function (Kabsch, Butterworth filter, COP calculation) must have verified ground-truth tests.


2. **Synthetic Validation**:
* Synthetic rigid-body motion with known sinusoidal angular trajectories to verify angular velocity, acceleration, and inverse dynamics torques.


3. **Cross-Engine Tolerance**:
* Output angles and moments must match Visual3D baseline exports within tolerance:
* Kinematic angles: $\le 10^{-4}\,\text{degrees}$.
* Joint moments: $\le 10^{-3}\,\text{N}\cdot\text{m}$.
* COP coordinates: $\le 10^{-2}\,\text{mm}$.





---

## 6. Automation Pipeline & Python Interoperability

To fully replace Visual3D pipeline scripts (`.v3s`), the engine exposes high-level declarative commands via Python and JSON/YAML task specifications:

### Python Pipeline Example

```python
import openbiomech as ob

# 1. Load motion capture file
trial = ob.load_c3d("subject01_walk.c3d")

# 2. Filter 3D trajectories and analog signals
trial.filter_markers(cutoff_hz=6.0, order=4)
trial.filter_analog(cutoff_hz=20.0, order=4)

# 3. Apply static calibration & build biomechanical model
model = ob.BiomechanicalModel.from_static(
    static_c3d="subject01_static.c3d",
    template="isb_lower_limb.yaml"
)

# 4. Compute 6DoF Kinematics & Inverse Dynamics
results = model.process_dynamic_trial(
    trial,
    kinematic_standard="ISB",
    bsp_model="Dumas2007"
)

# 5. Extract temporal gait events
events = results.detect_gait_events(method="ForcePlateThreshold", threshold_n=15.0)

# 6. Export tabular time-series
results.export_csv("kinematics_kinetics_output.csv")

```

"""

with open("CLAUDE.md", "w", encoding="utf-8") as f:
f.write(claude_md_content)

print(f"Successfully generated CLAUDE.md ({len(claude_md_content)} bytes)")

```

```text?code_stdout&code_event_index=1
Successfully generated CLAUDE.md (17866 bytes)


```

Your Markdown file is ready


### Summary of `CLAUDE.md` Specification

The generated `CLAUDE.md` (17,866 bytes) provides an exhaustive configuration and engineering guideline written entirely in technical English to optimize token usage when working with Claude Code. It covers:

1. **Architecture & Modular Workspace**:
* Decoupled 7-crate Rust workspace (`c3d-io`, `biomech-math`, `biomech-model`, `inverse-dynamics`, `viewer-core`, `gui-app`, `pipeline-cli`) plus PyO3/maturin bindings (`py-openbiomech`).
* Struct-of-Arrays (SoA) layout for AVX-512 / ARM NEON SIMD vectorization.


2. **Core Mathematical & Biomechanical Standards**:
* **Rigid Body 6DoF Registration**: Closed-form SVD / Kabsch-Umeyama algorithm with reflection rejection ($\det(\mathbf{R}) = +1$).
* **Kinematics**: ISB Joint Coordinate System (JCS) / Grood & Suntay conventions, unit quaternion continuous integration ($\Vert{}\mathbf{q}\Vert{} = 1$), and gimbal-lock-free Cardan angle extractions.
* **Signal Processing**: 4th-order dual-pass zero-phase Butterworth digital filtering and GCVSPL quintic splines for continuous derivatives ($\mathbf{v}, \mathbf{a}, \boldsymbol{\omega}, \dot{\boldsymbol{\omega}}$).
* **Kinetics & Force Plates**: Types 1–5 force platform calibrations, sensor origin offset corrections, vertical ground reaction force thresholding ($F_z \ge 15.0\,\text{N}$), and Center of Pressure (COP) calculation.
* **Inverse Dynamics**: Full recursive bottom-up Newton-Euler 3D equations of motion, time-varying inertia tensor transformation ($\mathbf{I} = \mathbf{R} \mathbf{I}_0 \mathbf{R}^T$), and joint power computations ($P = \mathbf{M} \cdot \boldsymbol{\omega}_{\text{rel}}$).


3. **C3D Specification & Parsing**:
* Detailed 512-byte header decoding, parameter group layouts, and signed integer / real coordinate scaling.
* Native DEC VAX F-Float / D-Float IEEE-754 converter routine for historical motion capture datasets.


4. **Engineering Guidelines, Error Handling & Numerical Tolerances**:
* `f64` numerical pipeline with strict zero-panic error enums (`thiserror`).
* Exact numerical validation parity criteria against Visual3D (kinematics $\le 10^{-4}{^\circ}$, moments $\le 10^{-3}\,\text{N}\cdot\text{m}$, COP $\le 10^{-2}\,\text{mm}$).
