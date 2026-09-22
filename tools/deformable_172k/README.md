# Deformable volumes for 172,032 actors

This branch targets 42 deformable pads per environment across 4,096 environments:
`42 * 4096 = 172032` volumes in one PhysX scene. It is based on upstream
`110.1-omni-and-physx-5.9.0`, commit
`517a0073715120e114ee055b63b26c95e00d9039` (Omniverse Physics 110.1 / PhysX 5.9.0).

## Limits and compatibility

The packed volume/element index remains 32 bits. Six bits move from the
tetrahedron field to the volume field:

| Encoding | Upstream | This branch |
| --- | ---: | ---: |
| Volume ID bits | 12 | 18 |
| Maximum volumes per scene | 4,095 | 262,143 |
| Tetrahedron index bits | 20 | 14 |
| Maximum tetrahedra per volume mesh | 1,048,575 | 16,383 |
| Deformable surface encoding | 12 / 20 | 12 / 20 (unchanged) |

The maximum counts reserve all-ones indices. Valid volume IDs are `0..262142`.
Valid tetrahedron indices are `0..16382`; `0x3fff` means any tetrahedron in
element filters. The tetrahedron limit applies separately to the collision and
simulation mesh. Body IDs are scene-global, while tetrahedron IDs are local to
each body; the mesh size is not multiplied by the number of environments.
The original workspace report records a largest target mesh of 14,238 simulation
tetrahedra, within this limit. Check both meshes of any new asset.

CPU and GPU code must be rebuilt together. This layout is incompatible with
unmodified libraries that encode volume IDs using 12 / 20 bits. The script below
builds the standalone SDK; Isaac Sim also needs the matching rebuilt Omni PhysX
extension stack. Replacing just `libPhysXGpu_64.so` in an installed Isaac Sim is
not sufficient.

This is a count/encoding change. It does not establish that a 172,032-body scene
fits GPU memory or runs at a useful frame rate.

## Source changes

- Raise the scene count guard and change the shared volume encode/decode layout.
- Use the volume-specific wildcard in CUDA contact preparation and select
  element-filter wildcards by actor type, including swapped volume/surface pairs.
- Move volume or pair indexing from CUDA grid Y to grid X in the affected solver
  and narrowphase paths. Move work within each actor to grid Y and update the
  corresponding host launches; this avoids the 65,535 grid-Y limit on body count.
- Keep the cloth/particle-only launch on its original axes, matching its
  unchanged kernel. A mismatched launch in the initial local patch was corrected.
- Add optional CUDA architecture and nvcc-thread CMake settings. Without an
  override, the upstream architecture selection and thread default are retained.

[grid-audit.json](grid-audit.json) lists the 21 CUDA functions whose axes changed;
it is an inspection inventory, not evidence of a full physics regression test.

## Reproduce the Linux SDK build

Tested toolchain: GCC/G++ 11.4.0, CMake 3.22.1, Ninja 1.10.1, CUDA 12.8.1
redistributables (nvcc 12.8.93). The local build targets RTX 5090 `sm_120` and
`compute_120`. Supply a CUDA toolkit containing nvcc, runtime libraries/headers,
CCCL headers, and cuobjdump; the local toolkit is in `../PhysX-172k-build/cuda-12.8.1`.

Run from the repository root:

```bash
python3 tools/deformable_172k/build_sdk.py \
  --cuda-root ../PhysX-172k-build/cuda-12.8.1 \
  --build-root ../PhysX-172k-build \
  --cc /usr/bin/gcc-11 --cxx /usr/bin/g++-11
python3 tools/deformable_172k/check_encoding.py ../PhysX-172k-build/checked-gcc
```

Both `checked` and `release` are built by default. Use `--configuration release`
to build only release, and `--arch` for a different single CUDA architecture.
Only architecture 120 was validated here. GPU output is
`physx/bin/linux.x86_64/{checked,release}/libPhysXGpu_64.so`, alongside the CPU
and GPU static libraries. Build directories, downloaded toolkits, caches, and
binaries are local artifacts and are not committed.

## Validation on 2026-09-22

- The original checked/release builds each completed 627 targets. After correcting
  the cloth-only launch, both configurations rebuilt the affected object, static
  library, and GPU shared library successfully.
- `build_sdk.py` reconfigured both existing builds and completed successfully.
- `check_encoding.py` compiled against the actual shared internal PhysX header
  and passed. It checks every valid volume ID at tetrahedron boundaries and the
  wildcard, including IDs above 4,095 and 65,535, and checks unchanged surface
  encoding. It does not simulate physics or test GPU kernels.
- Python syntax checks and `git diff --check` passed.
- The supplied folders contain a runtime probe, but no runtime result for more
  than 4,095 volumes. A 172,032-volume simulation is **not yet validated**.

The local build logs are under `../PhysX-172k-build/logs/`:
`rebuild-checked.log`, `rebuild-release.log`, and `reproduce-sdk.log`.

## Isaac Sim runtime probe

[runtime_probe.py](runtime_probe.py) carries forward the probe from the supplied
build folder with configurable paths/device and a square placement grid so a
large test scene remains over the ground plane. Use a matching Isaac Sim / Isaac
Lab installation and a rebuilt Omni PhysX extension tree. Run with Isaac Sim's
Python environment, for example after setting the following to real local paths:

```bash
export PHYSX_PROBE_EXTS=/path/to/PhysX/omni/ovexts/_build/linux-x86_64/release/extsPhysics
export PHYSX_PROBE_EXPERIENCE=/path/to/IsaacLab/apps/isaaclab.python.headless.kit
export PHYSX_PROBE_FOUNDATION=/path/to/matching/omni.physx.foundation-extension
export PHYSX_PROBE_OUTPUT=/tmp/physx-probe-4096
export PHYSX_PROBE_GPU=0
export PHYSX_PROBE_VOLUMES=4096
/path/to/isaac-sim/python.sh tools/deformable_172k/runtime_probe.py
```

If `PHYSX_PROBE_FOUNDATION` is omitted, the probe searches
`$ISAAC_PATH/extscache` (default `/isaac-sim/extscache`) and requires exactly one
foundation extension. All paths must refer to mutually compatible versions.

With `PHYSX_PROBE_VOLUMES=0`, it checks extension selection and records loaded
native libraries only. With a positive count, it also verifies the tensor-view
body count, CUDA backend, finite nodal positions, gravity-driven motion for all
bodies, and ground contact over 180 steps. It writes `result.json` and, on physics
success, `positions.npz`. Start with a small scene, then test 4,096, 65,536, and
172,032 bodies in separate processes/output directories. The probe uses tiny
meshes without self-collision; passing it would still not validate the full pad
assets, attachment/filter combinations, or training workload.
