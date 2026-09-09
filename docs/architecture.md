# mkvis3d / OpenBiomech — Target Architecture (Rust)

> **Status:** this document is the **long-term target architecture** — a full
> Rust workspace that has **not been started**. The project is currently in
> the **Python prototype** phase; see [`CLAUDE.md`](../CLAUDE.md) for what
> actually exists today and [`docs/index.md`](index.md) for the documentation
> hub. Nothing here should be read as "already implemented."

OpenBiomech (mkvis3d) targets an ultra-high-performance, cross-platform
(Linux, macOS Apple Silicon/Intel, Windows) biomechanical analysis engine and
3D visualization suite: an open-source, reproducible alternative to C-Motion
Visual3D and BTK Mokka.

The system decouples into four modular layers:

1. **Core data structures & binary I/O engine** — a high-throughput,
   near-zero-copy parser/writer for standard biomechanical formats (`.c3d`,
   `.csv`, `.trc`, `.mot`, `.anc`).
2. **Computational biomechanics engine** — numerically stable linear algebra,
   dual-pass filtering, rigid-body 6DoF tracking, ISB Joint Coordinate
   Systems (JCS), recursive Newton-Euler inverse dynamics, and anthropometric
   segment modeling.
3. **Hardware-accelerated 3D viewport & UI** — cross-platform rendering via
   `wgpu` (Metal on macOS, Vulkan on Linux, DX12/Vulkan on Windows) paired
   with an immediate-mode UI (`egui`, or `Qt6`/`cxx-qt`) and a synchronized
   high-fps 2D telemetry plot view.
4. **Automation, scripting & IPC pipeline** — Python bindings via `PyO3` /
   `maturin`, enabling batch CLI processing comparable to Visual3D pipeline
   scripts (`.v3s`) and interoperability with the scientific Python stack
   (NumPy, SciPy, Polars).

## 1. Workspace layout (target)

```text
mkvis3d/
├── Cargo.toml                      # Cargo workspace definition
├── CLAUDE.md                       # AI assistant instructions and current phase
├── README.md
├── crates/
│   ├── c3d-io/                     # Binary C3D parser/writer (Intel, DEC VAX, MIPS/Sun)
│   │   ├── src/
│   │   │   ├── header.rs           # 512-byte block 1 header decoding
│   │   │   ├── parameters.rs       # Parameter blocks (groups, items, dimensions)
│   │   │   ├── data_blocks.rs      # 3D points (real/int16) & analog multichannel frames
│   │   │   ├── vax.rs              # DEC VAX floating-point converter
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── biomech-math/                # Core kinematics, filters, and linear algebra
│   │   ├── src/
│   │   │   ├── filtering.rs         # 4th-order zero-lag Butterworth, GCVSPL splines
│   │   │   ├── rigid_body.rs        # SVD / Kabsch-Umeyama optimal registration
│   │   │   ├── quaternions.rs       # Scalar-first unit quaternions & SLERP
│   │   │   ├── euler_angles.rs      # Cardan/Euler decomposition (ZXY, XYZ, YXZ, ...)
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── biomech-model/                # Segmental model, landmarks, and anthropometry
│   │   ├── src/
│   │   │   ├── segment.rs            # Rigid segment (ACS, TCS, mass, CoM, inertia tensor)
│   │   │   ├── landmark.rs           # Static/dynamic calibration landmarks & virtual targets
│   │   │   ├── isb_joints.rs         # ISB conventions (pelvis/hip/knee/ankle/spine/shoulder/elbow/wrist)
│   │   │   ├── bsp.rs                # Body segment parameters (Dempster, de Leva, Dumas)
│   │   │   ├── events.rs             # Gait event detection (heel strike/toe off)
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── inverse-dynamics/             # Force plate calibration, COP, kinetics
│   │   ├── src/
│   │   │   ├── force_plate.rs        # Types 1-5 platform calibration
│   │   │   ├── cop.rs                # Center of pressure and free moment
│   │   │   ├── newton_euler.rs       # Recursive 3D Newton-Euler equations
│   │   │   ├── joint_power.rs        # 3D joint power (P = M · ω) and work
│   │   │   └── lib.rs
│   │   └── tests/
│   ├── viewer-core/                  # wgpu rendering pipelines and 3D scene graph
│   │   └── src/
│   │       ├── camera.rs             # Arcball/orbit 3D camera and view projections
│   │       ├── pipeline_points.rs    # Instanced sphere rendering for markers
│   │       ├── pipeline_vectors.rs   # Dynamic arrows for GRF, segment axes, COP
│   │       ├── pipeline_mesh.rs      # Bone geometries and segment reference meshes
│   │       ├── pipeline_grid.rs      # Ground planes and force-plate bounding boxes
│   │       └── lib.rs
│   ├── gui-app/                      # Desktop frontend (egui or cxx-qt)
│   │   └── src/
│   │       ├── transport.rs          # Timeline playback, scrub, loop, sub-frame interpolation
│   │       ├── plots.rs              # Real-time multi-channel 2D plots, synced to 3D
│   │       ├── model_tree.rs         # Interactive segment hierarchy and marker assignment
│   │       └── main.rs
│   └── pipeline-cli/                 # Headless CLI for batch execution of automated scripts
│       └── src/main.rs
├── py-openbiomech/                    # High-level Python package via PyO3
│   ├── Cargo.toml
│   ├── pyproject.toml
│   └── src/lib.rs
└── tests/
    └── fixtures/                      # Real-world validation C3D files (Vicon, Qualisys, Charnwood)
```

See the [README.md crate table](../README.md#current-status) for which of
these crates already have a working Python module in the current prototype.

## 2. Mathematical & biomechanical standards

Implementations must adhere to International Society of Biomechanics (ISB)
conventions and the formal analytical formulations below. This section is
the canonical reference for *what is correct*, independent of the
implementation language (Python today, Rust at the target architecture).

### 2.1 Coordinate system & triad conventions

1. **Right-handed orthogonal system.** All global systems and local segment
   coordinate systems (SCS) must satisfy:

   $$\mathbf{e}_x \times \mathbf{e}_y = \mathbf{e}_z, \quad
     \lVert\mathbf{e}_x\rVert = \lVert\mathbf{e}_y\rVert = \lVert\mathbf{e}_z\rVert = 1$$

2. **ISB standard axis assignment:**
   - $\mathbf{Z}$: longitudinal/superior axis, directed proximally.
   - $\mathbf{X}$: anteroposterior axis, directed anteriorly (or laterally,
     depending on the specific joint standard — e.g. ISB knee vs. hip).
   - $\mathbf{Y}$: mediolateral axis, directed laterally/medially per the
     specific ISB segment specification.

3. **Unit quaternions for singularity-free rotations.** Orientation is
   maintained as a **scalar-first** unit quaternion
   $\mathbf{q} = [w, x, y, z]^T \in \mathbb{H}$, $\lVert\mathbf{q}\rVert = 1$.
   Conversion to Cardan/Euler angles happens strictly as an extraction step,
   to avoid gimbal lock during intermediate tracking.

### 2.2 6DoF rigid-body optimal registration (Kabsch-Umeyama SVD)

For each frame, determine the optimal rotation $\mathbf{R} \in \mathrm{SO}(3)$
and translation $\mathbf{p} \in \mathbb{R}^3$ aligning technical cluster
markers $\mathbf{x}_i^{\text{local}}$ to measured trajectories
$\mathbf{y}_i^{\text{global}}$ ($i = 1, \dots, N$):

1. Compute centroids:

   $$\mathbf{c}_x = \frac{1}{N}\sum_{i=1}^N \mathbf{x}_i^{\text{local}}, \qquad
     \mathbf{c}_y = \frac{1}{N}\sum_{i=1}^N \mathbf{y}_i^{\text{global}}$$

2. Construct the centered cross-covariance matrix:

   $$\mathbf{H} = \sum_{i=1}^N (\mathbf{x}_i^{\text{local}} - \mathbf{c}_x)
                              (\mathbf{y}_i^{\text{global}} - \mathbf{c}_y)^T$$

3. Singular value decomposition: $\mathbf{H} = \mathbf{U}\mathbf{\Sigma}\mathbf{V}^T$.

4. Compute the rotation, rejecting reflections ($\det(\mathbf{R}) = +1$):

   $$\mathbf{d} = \begin{bmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & \det(\mathbf{V}\mathbf{U}^T) \end{bmatrix},
     \qquad \mathbf{R} = \mathbf{V}\,\mathbf{d}\,\mathbf{U}^T$$

5. Compute the translation: $\mathbf{p} = \mathbf{c}_y - \mathbf{R}\,\mathbf{c}_x$.

### 2.3 Joint Coordinate System (JCS) kinematics

Joint kinematics follow the Grood & Suntay / ISB floating-axis
parameterization:

- Proximal frame $\mathbf{P} = [\mathbf{e}_1, \mathbf{e}_2, \mathbf{e}_3]$,
  distal frame $\mathbf{D} = [\mathbf{f}_1, \mathbf{f}_2, \mathbf{f}_3]$.
- Proximal (flexion) axis: $\mathbf{e}_{\text{flex}} = \mathbf{e}_1$.
- Distal (rotation) axis: $\mathbf{e}_{\text{rot}} = \mathbf{f}_3$.
- Floating axis (perpendicular to both):

  $$\mathbf{e}_{\text{float}} = \frac{\mathbf{e}_{\text{flex}} \times \mathbf{e}_{\text{rot}}}
                                      {\lVert\mathbf{e}_{\text{flex}} \times \mathbf{e}_{\text{rot}}\rVert}$$

- Joint angular velocity vector:

  $$\boldsymbol{\omega}_{\text{joint}} = \dot{\alpha}\,\mathbf{e}_{\text{flex}}
                                       + \dot{\beta}\,\mathbf{e}_{\text{float}}
                                       + \dot{\gamma}\,\mathbf{e}_{\text{rot}}$$

### 2.4 Signal processing & numerical differentiation

1. **Butterworth dual-pass filter** — 4th-order low-pass digital filter,
   forward-backward zero-phase-lag filtering, with the standard cutoff
   correction $f_{\text{effective}} = f_c / (2^{1/n} - 1)^{1/4}$ for `n`
   passes.
2. **GCVSPL (generalized cross-validatory splines)** — cubic or quintic
   smoothing splines producing continuous, smooth first ($\mathbf{v}$,
   $\boldsymbol{\omega}$) and second ($\mathbf{a}$, $\dot{\boldsymbol{\omega}}$)
   derivatives without amplifying high-frequency digitizing noise. The
   Python prototype uses `scipy.interpolate.make_smoothing_spline` (cubic
   GCV only — quintic and the reported GCV score are not exposed through
   scipy; see [`CLAUDE.md`](../CLAUDE.md#conventions)).

### 2.5 Force plate mechanics & Center of Pressure (COP)

Support platform types 1-5. For a standard strain-gauge/piezoelectric
platform (type 2, $6\times 6$ calibration matrix $\mathbf{C}$):

1. Compute channel forces and moments from raw signals:
   $\mathbf{F}_{\text{raw}} = \mathbf{C}\cdot\mathbf{V}_{\text{analog}}$.
2. Correct moments for the geometric sensor origin offset $(x_0, y_0, z_0)$:

   $$M_x' = M_x + F_y z_0 - F_z y_0, \qquad M_y' = M_y - F_x z_0 + F_z x_0$$

3. Compute the instantaneous COP in platform coordinates:

   $$x_{\text{cop}} = \frac{-M_y'}{F_z}, \qquad y_{\text{cop}} = \frac{M_x'}{F_z}, \qquad z_{\text{cop}} = 0$$

4. **Vertical GRF threshold** — if $F_z < F_{\text{threshold}}$ (default
   $15.0\ \text{N}$), set $\mathrm{COP} = \mathbf{0}$, $\mathbf{F} = \mathbf{0}$,
   $\mathbf{M} = \mathbf{0}$ to remove non-contact singularities.
5. Transform COP and reaction forces from local plate coordinates to the
   global lab coordinate system using the 4 corner calibration parameters
   (`CORNERS`).

### 2.6 3D inverse dynamics (recursive Newton-Euler)

Executed recursively, distal to proximal:

1. **Linear momentum balance:**

   $$\mathbf{F}_{\text{proximal}} = m_i(\mathbf{a}_{\text{com},i} - \mathbf{g}) - \mathbf{F}_{\text{distal}}$$

   with $\mathbf{g} = [0, 0, -9.80665]^T\ \text{m/s}^2$.

2. **Angular momentum balance:**

   $$\mathbf{M}_{\text{proximal}} = \mathbf{I}_i\dot{\boldsymbol{\omega}}_i
       + \boldsymbol{\omega}_i \times (\mathbf{I}_i \boldsymbol{\omega}_i)
       - \mathbf{M}_{\text{distal}}
       - (\mathbf{r}_{\text{distal}} \times \mathbf{F}_{\text{distal}})
       - (\mathbf{r}_{\text{proximal}} \times \mathbf{F}_{\text{proximal}})$$

   where $\mathbf{I}_i = \mathbf{R}_i \mathbf{I}_{i,\text{local}} \mathbf{R}_i^T$
   is the instantaneous global inertia tensor,
   $\mathbf{r}_{\text{proximal}} = \mathbf{p}_{\text{joint,prox}} - \mathbf{p}_{\text{com},i}$,
   $\mathbf{r}_{\text{distal}} = \mathbf{p}_{\text{joint,dist}} - \mathbf{p}_{\text{com},i}$.

3. **Joint power:**

   $$P_{\text{joint}} = \mathbf{M}_{\text{joint}} \cdot (\boldsymbol{\omega}_{\text{distal}} - \boldsymbol{\omega}_{\text{proximal}})$$

## 3. C3D file format specification & parsing rules

Raw 512-byte blocks. The parser must guarantee near-zero-copy performance
where feasible and handle historical format anomalies.

### 3.1 Header block (block 1)

- **Byte 1:** pointer to first parameter block (typically 2).
- **Byte 2:** magic key `0x50` (decimal 80).
- **Word 2 (bytes 3-4):** number of 3D points per frame ($N_{\text{points}}$).
- **Word 3 (bytes 5-6):** total analog measurements per 3D frame
  ($N_{\text{analog\_samples}} = N_{\text{channels}} \times N_{\text{subsamples}}$).
- **Word 4 (bytes 7-8):** 1-based index of first frame.
- **Word 5 (bytes 9-10):** 1-based index of last frame.
- **Word 6 (bytes 11-12):** maximum interpolation gap.
- **Words 7-8 (bytes 13-16):** 3D scale factor (float):
  - `scale < 0.0` → 3D points stored as 32-bit floats.
  - `scale > 0.0` → 3D points stored as 16-bit signed integers; scale
    coordinates by $\lvert\text{scale}\rvert$.
- **Word 9 (bytes 17-18):** pointer to the first 512-byte data block.
- **Word 10 (bytes 19-20):** number of analog samples per video frame ($N$).
- **Words 11-12 (bytes 21-24):** frame rate (video sample frequency, Hz, float).

### 3.2 Processor architecture flags

Found at byte 4 of the first parameter block:

- **Processor 84 (`0x54`):** Intel little-endian (standard IEEE-754 float).
- **Processor 85 (`0x55`):** DEC VAX (F-Float/D-Float: sign bit, 8-bit
  exponent biased 128, 23-bit mantissa, swapped 16-bit words).
- **Processor 86 (`0x56`):** MIPS/Sun big-endian (IEEE-754, byte-swapped).

The parser decodes DEC VAX bit patterns without relying on hardware VAX
emulation:

```rust
pub fn vax_to_ieee_f32(vax_bits: u32) -> f32 {
    let word0 = (vax_bits & 0xFFFF) as u16;
    let word1 = ((vax_bits >> 16) & 0xFFFF) as u16;
    if word0 == 0 {
        return 0.0;
    }
    let sign = (word0 >> 15) & 0x01;
    let exponent = (word0 >> 7) & 0xFF;
    let fraction = (((word0 & 0x7F) as u32) << 16) | (word1 as u32);
    if exponent == 0 && sign == 0 {
        return 0.0;
    }
    let ieee_exp = (exponent as i32) - 128 + 127 - 1;
    let ieee_bits = ((sign as u32) << 31) | ((ieee_exp as u32) << 23) | fraction;
    f32::from_bits(ieee_bits)
}
```

(The current Python prototype implements the equivalent decode in
`openbiomech/c3d_io/legacy_binary.py` using NumPy; see
[`CLAUDE.md`](../CLAUDE.md#current-phase-python-prototype).)

### 3.3 Data storage layout (target Rust)

Struct-of-Arrays (SoA) layout for contiguous SIMD vectorization:

- **Markers:** `x: Vec<f32>`, `y: Vec<f32>`, `z: Vec<f32>`,
  `residual: Vec<f32>`, `camera_mask: Vec<u16>`.
- **Analog:** a contiguous buffer flattened as `[Frame][Subsample][Channel]`.

(The Python prototype uses the equivalent NumPy SoA layout — see the
`c3d-io` row of the crate table in [`CLAUDE.md`](../CLAUDE.md).)

## 4. Rust code style & engineering guidelines (target)

These rules apply once the Rust workspace starts. They do not apply to the
current Python prototype — see [`CLAUDE.md` § Conventions](../CLAUDE.md#conventions)
for the Python rules in force today.

### 4.1 Rust idioms & safety

1. **Zero unchecked panics** — no `unwrap()`, `expect()`, or bare-bracket
   slicing in library crates. Propagate errors via a typed enum:

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

2. **Precision discipline** — intermediate kinematics, SVD decompositions,
   and numerical integration use `f64`; downcast to `f32` only when packing
   vertex/instance buffers for `wgpu` rendering.
3. **Allocation rules** — zero heap allocations inside per-frame processing
   loops; pre-allocate frame buffers (`Vec::with_capacity`) or use
   arena/scratch memory.

### 4.2 Testing & parity verification

1. Every mathematical function (Kabsch, Butterworth, COP) has a
   ground-truth unit test.
2. Synthetic rigid-body motion with known sinusoidal angular trajectories
   verifies angular velocity, acceleration, and inverse-dynamics torques.
3. Cross-engine tolerance against Visual3D baseline exports:
   - Kinematic angles: $\le 10^{-4}$ degrees.
   - Joint moments: $\le 10^{-3}\ \text{N}\cdot\text{m}$.
   - COP coordinates: $\le 10^{-2}\ \text{mm}$.

## 5. Automation pipeline & Python interoperability (target)

To fully replace Visual3D pipeline scripts (`.v3s`), the target engine
exposes high-level declarative commands via Python and JSON/YAML task
specifications:

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
    template="isb_lower_limb.yaml",
)

# 4. Compute 6DoF kinematics & inverse dynamics
results = model.process_dynamic_trial(
    trial,
    kinematic_standard="ISB",
    bsp_model="Dumas2007",
)

# 5. Extract temporal gait events
events = results.detect_gait_events(method="ForcePlateThreshold", threshold_n=15.0)

# 6. Export tabular time series
results.export_csv("kinematics_kinetics_output.csv")
```

The equivalent already works today with the real `openbiomech` Python
package (`c3d_io`, `biomech_math`, `model`, `inverse_dynamics`) — see
[`docs/cli.md`](cli.md) for the CLI surface and
[`README.md`](../README.md) for the current status table.
