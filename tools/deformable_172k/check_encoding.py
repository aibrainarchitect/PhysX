#!/usr/bin/env python3
"""Compile and run the encoding check using include paths from a configured SDK."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build_dir', type=Path, help='e.g. ../PhysX-172k-build/checked-gcc')
    args = parser.parse_args()
    build = args.build_dir.resolve()
    commands = json.loads((build / 'compile_commands.json').read_text())
    entry = next(e for e in commands if e['file'].endswith('/PxgSoftBodyCore.cpp'))
    original = entry.get('arguments') or shlex.split(entry['command'])
    flags = []
    index = 1
    while index < len(original):
        arg = original[index]
        if arg in ('-I', '-isystem', '-D'):
            flags.extend(original[index:index + 2])
            index += 2
            continue
        if arg.startswith(('-I', '-D')):
            flags.append(arg)
        index += 1
    binary = build / 'check_deformable_encoding'
    command = [original[0], *flags, '-std=c++14', '-O2',
               str(Path(__file__).with_suffix('.cpp')), '-o', str(binary)]
    subprocess.run(command, cwd=entry['directory'], check=True)
    subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    main()
