#!/usr/bin/env python3
"""Reproduce the standalone Linux PhysX SDK builds for this branch."""
import argparse
from pathlib import Path
import shlex
import subprocess


def main():
    source = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cuda-root', type=Path, required=True)
    parser.add_argument('--build-root', type=Path, default=source.parent / (source.name + '-build'))
    parser.add_argument('--configuration', choices=('checked', 'release'), action='append')
    parser.add_argument('--cc', default='gcc-11')
    parser.add_argument('--cxx', default='g++-11')
    parser.add_argument('--arch', default='120', help='Single CUDA architecture; tested: 120')
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--nvcc-threads', type=int, default=2)
    args = parser.parse_args()
    cuda = args.cuda_root.resolve()
    if not (cuda / 'bin/nvcc').is_file():
        parser.error('--cuda-root must contain bin/nvcc')
    if not args.arch.isdecimal() or args.jobs < 1 or args.nvcc_threads < 1:
        parser.error('architecture, jobs, and nvcc threads must be positive integers')
    for config in args.configuration or ('checked', 'release'):
        build = args.build_root.resolve() / (config + '-gcc')
        commands = [
            ['cmake', '-S', str(source / 'physx/compiler/public'), '-B', str(build), '-G', 'Ninja',
             '-DCMAKE_BUILD_TYPE=' + config,
             '-DPHYSX_ROOT_DIR=' + str(source / 'physx'), '-DTARGET_BUILD_PLATFORM=linux',
             '-DCMAKE_C_COMPILER=' + args.cc, '-DCMAKE_CXX_COMPILER=' + args.cxx,
             '-DCMAKE_CUDA_HOST_COMPILER=' + args.cxx,
             '-DCMAKE_CUDA_COMPILER=' + str(cuda / 'bin/nvcc'), '-DCUDAToolkit_ROOT=' + str(cuda),
             '-DCMAKE_CUDA_ARCHITECTURES=' + args.arch,
             '-DPX_CUDA_SASS_ARCHITECTURES=' + args.arch,
             '-DPX_CUDA_PTX_ARCHITECTURES=' + args.arch,
             '-DPX_CUDA_COMPILER_THREADS=' + str(args.nvcc_threads),
             '-DPX_GENERATE_GPU_PROJECTS=ON', '-DPX_GENERATE_STATIC_LIBRARIES=ON',
             '-DPX_BUILDSNIPPETS=OFF', '-DPX_BUILDPVDRUNTIME=ON',
             '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
             '-DPX_OUTPUT_LIB_DIR=' + str(source / 'physx'),
             '-DPX_OUTPUT_BIN_DIR=' + str(source / 'physx')],
            ['cmake', '--build', str(build), '--parallel', str(args.jobs)],
        ]
        for command in commands:
            print(shlex.join(command), flush=True)
            subprocess.run(command, cwd=source, check=True)


if __name__ == '__main__':
    main()
