"""Verify a rebuilt Omni PhysX stack, then optionally simulate falling volumes.

Run with Isaac Sim's Python. See README.md for required environment variables.
"""
import json
import math
import os
from pathlib import Path
import traceback

DEV = Path(os.environ['PHYSX_PROBE_EXTS']).resolve()
EXPERIENCE = Path(os.environ['PHYSX_PROBE_EXPERIENCE']).resolve()
OUT = Path(os.environ['PHYSX_PROBE_OUTPUT']).resolve()
GPU = int(os.environ.get('PHYSX_PROBE_GPU', '0'))
assert DEV.is_dir(), DEV
assert EXPERIENCE.is_file(), EXPERIENCE
OUT.mkdir(parents=True, exist_ok=True)
report = {'status': 'starting', 'pid': os.getpid(), 'dev_folder': str(DEV)}
def save():
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
save()
from isaacsim import SimulationApp
foundation_override = os.environ.get('PHYSX_PROBE_FOUNDATION')
if foundation_override:
    foundation_dir = Path(foundation_override).resolve()
else:
    foundation = sorted(Path(os.environ.get('ISAAC_PATH', '/isaac-sim')).glob(
        'extscache/omni.physx.foundation-*/config/extension.toml'))
    assert len(foundation) == 1, 'Set PHYSX_PROBE_FOUNDATION to the matching foundation extension'
    foundation_dir = foundation[0].parent.parent.resolve()
assert (foundation_dir / 'config/extension.toml').is_file(), foundation_dir
app = SimulationApp({
    'headless': True, 'active_gpu': GPU, 'physics_gpu': GPU,
    'multi_gpu': False, 'disable_viewport_updates': True, 'limit_cpu_threads': 8,
    'extra_args': [f'--/app/exts/devFolders=["{DEV}"]',
                   f'--/app/exts/devPaths=["{foundation_dir}"]',
                   '--/app/fastShutdown=true', '--/plugins/carb.tasking.plugin/threadCount=8',
                   '--/app/renderer/enabled=false', '--/app/window/enabled=false',
                   '--/app/extensions/registryEnabled=false'],
}, experience=str(EXPERIENCE))
try:
    import omni.kit.app
    manager = omni.kit.app.get_app().get_extension_manager()
    extensions = {}
    for name in ['omni.physx', 'omni.physx.gpu', 'omni.physx.tensors',
                 'omni.physx.cooking', 'omni.physx.foundation', 'omni.usdphysics',
                 'omni.usd.schema.physx']:
        manager.set_extension_enabled_immediate(name, True)
        ext_id = manager.get_enabled_extension_id(name)
        path = manager.get_extension_path(ext_id) if ext_id else None
        extensions[name] = {'id': ext_id, 'path': path}
    report['extensions'] = extensions
    report['loaded_libraries'] = sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
        if ('physx' in line.lower() or 'usdphysics' in line.lower()) and '.so' in line})
    save()
    for name in ['omni.physx', 'omni.physx.gpu', 'omni.physx.tensors', 'omni.physx.cooking']:
        assert extensions[name]['path'] and Path(extensions[name]['path']).resolve().is_relative_to(DEV), extensions[name]
    report['status'] = 'pass_extension_load'
    print('PHYSX172K_EXTENSION_LOAD_PASS', flush=True)
    count = int(os.environ.get('PHYSX_PROBE_VOLUMES', '0'))
    assert 0 <= count <= 262143, count
    if count:
        import carb
        import numpy as np
        import omni.usd
        import omni.physx
        from omni.physx.bindings import _physx as physx_bindings
        import omni.physics.tensors as tensors
        from omni.physx.scripts import deformableUtils, deformableMeshUtils, physicsUtils
        from pxr import Gf, UsdGeom, UsdPhysics, PhysxSchema
        settings = carb.settings.get_settings()
        settings.set('/physics/overrideGPU', 1)
        settings.set('/physics/cudaDevice', GPU)
        settings.set('/physics/updateToUsd', True)
        settings.set(physx_bindings.SETTING_SUPPRESS_READBACK, True)
        settings.set(physx_bindings.SETTING_USE_ACTIVE_CUDA_CONTEXT, False)
        omni.usd.get_context().new_stage()
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        world = UsdGeom.Xform.Define(stage, '/World')
        stage.SetDefaultPrim(world.GetPrim())
        scene = UsdPhysics.Scene.Define(stage, '/World/physicsScene')
        scene.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
        scene.CreateGravityMagnitudeAttr(9.81)
        scene_api = PhysxSchema.PhysxSceneAPI.Apply(scene.GetPrim())
        scene_api.CreateEnableGPUDynamicsAttr(True)
        scene_api.CreateBroadphaseTypeAttr('GPU')
        scene_api.CreateSolverTypeAttr('TGS')
        physicsUtils.add_ground_plane(stage, '/World/Ground', 'Z', 1000.0, Gf.Vec3f(0), Gf.Vec3f(0.5))
        material = '/World/PadMaterial'
        assert deformableUtils.add_deformable_material(stage, material, youngs_modulus=100000.0, poissons_ratio=0.3, dynamic_friction=0.5)
        points, indices = deformableMeshUtils.createTetraVoxelBox(1)
        points = [p * 0.1 for p in points]
        tets = [Gf.Vec4i(*indices[i:i+4]) for i in range(0, len(indices), 4)]
        columns = math.ceil(math.sqrt(count))
        for i in range(count):
            path = f'/World/Pad_{i:06d}'
            mesh = UsdGeom.TetMesh.Define(stage, path)
            mesh.CreatePointsAttr(points)
            mesh.CreateTetVertexIndicesAttr(tets)
            mesh.AddTranslateOp().Set(Gf.Vec3d((i % columns) * 0.3, (i // columns) * 0.3, 1.0))
            assert deformableUtils.set_physics_volume_deformable_body(stage, mesh.GetPath())
            mesh.GetPrim().ApplyAPI('PhysxBaseDeformableBodyAPI')
            mesh.GetPrim().GetAttribute('physxDeformableBody:selfCollision').Set(False)
            physicsUtils.add_physics_material_to_prim(stage, mesh.GetPrim(), material)
        report['status'] = 'scene_authored'
        report['volumes_requested'] = count
        report['tets_per_volume'] = len(tets)
        save()
        print(f'PHYSX172K_SCENE_AUTHORED count={count} tets_each={len(tets)}', flush=True)
        physics = omni.physx.get_physx_simulation_interface()
        stage_id = omni.usd.get_context().get_stage_id()
        physics.attach_stage(stage_id)
        dt = 1.0 / 120.0
        physics.simulate(dt, 0.0)
        physics.fetch_results()
        sim = tensors.create_simulation_view('warp', stage_id)
        sim.set_subspace_roots('/')
        bodies = sim.create_volume_deformable_body_view('/World/Pad_*')
        report['volumes_created'] = bodies.count
        report['tensor_device'] = str(sim.device)
        save()
        assert bodies.count == count, (bodies.count, count)
        assert str(sim.device).startswith('cuda'), sim.device
        initial = bodies.get_simulation_nodal_positions().numpy().copy().reshape(count, -1, 3)
        report['status'] = 'simulating'
        save()
        for step in range(1, 181):
            physics.simulate(dt, step * dt)
            physics.fetch_results()
            if step % 30 == 0:
                current = bodies.get_simulation_nodal_positions().numpy().reshape(count, -1, 3)
                assert np.isfinite(current).all(), f'Nonfinite at {step}'
                print(f'PHYSX172K_STEP {step} z_min={current[:,:,2].min():.5f} z_max={current[:,:,2].max():.5f}', flush=True)
        final = bodies.get_simulation_nodal_positions().numpy().copy().reshape(count, -1, 3)
        dropped = initial[:, :, 2].mean(axis=1) - final[:, :, 2].mean(axis=1)
        assert (dropped > 0.2).all(), dropped.min()
        assert final[:, :, 2].min() > -0.03, final[:, :, 2].min()
        report.update(status='pass_physics', steps=180,
                      min_drop_m=float(dropped.min()), max_drop_m=float(dropped.max()),
                      final_z_min_m=float(final[:,:,2].min()), final_z_max_m=float(final[:,:,2].max()))
        np.savez_compressed(OUT / 'positions.npz', initial=initial, final=final)
        save()
        del bodies, sim
        physics.detach_stage()
        print('PHYSX172K_PHYSICS_PASS ' + json.dumps({k:v for k,v in report.items() if k not in ('loaded_libraries', 'extensions')}), flush=True)
except BaseException:
    report['status'] = 'fail'
    report['traceback'] = traceback.format_exc()
    print(report['traceback'], flush=True)
    raise
finally:
    save()
    app.close(exit_code=0 if report['status'].startswith('pass_') else 1)
