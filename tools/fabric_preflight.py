#!/usr/bin/env python3
"""Inspect Fabric metadata without loading classes, extracting files or running Java.

This is a dev-only requirements inventory, not a compatibility verdict or loader.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

MAX_METADATA = 2 * 1024 * 1024
MAX_NESTED = 256 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_DEPTH = 8


def sha512(path):
    digest = hashlib.sha512()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_archive(source, name, budget, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError('nested jar depth exceeds limit')
    with zipfile.ZipFile(source) as jar:
        names = jar.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f'{name}: duplicate archive entry')

        def read(member, limit=MAX_METADATA):
            info = jar.getinfo(member)
            if info.file_size > limit or info.file_size > budget[0]:
                raise ValueError(f'{name}!/{member}: inspection size limit exceeded')
            budget[0] -= info.file_size
            return jar.read(info)

        def document(member):
            value = json.loads(read(member))
            if not isinstance(value, dict):
                raise ValueError(f'{member}: expected a JSON object')
            return value

        if 'fabric.mod.json' not in names:
            raise ValueError(f'{name}: no fabric.mod.json')
        metadata = document('fabric.mod.json')
        if metadata.get('schemaVersion') != 1:
            raise ValueError(f'{name}: only Fabric metadata schema 1 is supported')
        for field in ('id', 'version'):
            if not isinstance(metadata.get(field), str) or not metadata[field]:
                raise ValueError(f'{name}: missing or invalid {field}')
        result = {
            'archive': name,
            'id': metadata['id'],
            'version': metadata['version'],
            'environment': metadata.get('environment', '*'),
            'depends': metadata.get('depends', {}),
            'entrypoints': metadata.get('entrypoints', {}),
            'language_adapters': metadata.get('languageAdapters', {}),
            'class_files': sum(n.endswith('.class') for n in names),
            'mixins': [],
            'access_widener': None,
            'nested_jars': [],
        }
        for declaration in metadata.get('mixins', []):
            config = declaration if isinstance(declaration, str) else declaration['config']
            environment = '*' if isinstance(declaration, str) else declaration.get('environment', '*')
            mixin = document(config)
            counts = {}
            for side in ('mixins', 'client', 'server'):
                entries = mixin.get(side, [])
                if not isinstance(entries, list) or not all(isinstance(x, str) for x in entries):
                    raise ValueError(f'{config}: invalid {side} list')
                counts[side] = len(entries)
            result['mixins'].append({
                'config': config, 'environment': environment,
                'required': mixin.get('required', False),
                'plugin': mixin.get('plugin'), 'declared_entries': counts,
            })
        widener = metadata.get('accessWidener')
        if widener:
            lines = [line.split('#', 1)[0].strip()
                     for line in read(widener).decode('utf-8').splitlines()]
            lines = [line for line in lines if line]
            if not lines or len(lines[0].split()) != 3 or lines[0].split()[0] != 'accessWidener':
                raise ValueError(f'{widener}: invalid access widener header')
            result['access_widener'] = {
                'file': widener, 'header': lines[0], 'declared_entries': len(lines) - 1,
            }
        for declaration in metadata.get('jars', []):
            member = declaration['file']
            data = read(member, MAX_NESTED)
            nested = inspect_archive(io.BytesIO(data), member, budget, depth + 1)
            nested['sha512'] = hashlib.sha512(data).hexdigest()
            result['nested_jars'].append(nested)
        return result


def audit(path, expected_sha512=None):
    digest = sha512(path)
    if expected_sha512 and digest != expected_sha512.lower():
        raise ValueError('SHA-512 mismatch; refusing to inspect an unpinned artifact')
    return {
        'schema_version': 1,
        'assessment': 'inventory-only; runtime compatibility not tested',
        'sha512': digest,
        'mod': inspect_archive(path, path.name, [MAX_TOTAL]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jar', type=Path)
    parser.add_argument('--sha512', help='reject an artifact that does not match this digest')
    args = parser.parse_args()
    try:
        report = audit(args.jar, args.sha512)
    except (OSError, ValueError, KeyError, TypeError, AttributeError,
            zipfile.BadZipFile, RuntimeError, RecursionError) as error:
        print(f'fabric_preflight: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
