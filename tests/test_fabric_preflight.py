"""Synthetic metadata fixtures only; no game/mod bytecode or assets."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from tools import fabric_preflight as preflight


def archive(metadata=None, files=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as jar:
        jar.writestr('fabric.mod.json', json.dumps(metadata or {
            'schemaVersion': 1, 'id': 'fixture', 'version': '1.0',
        }))
        for name, data in (files or {}).items():
            jar.writestr(name, data)
    return stream.getvalue()


class FabricPreflightTests(unittest.TestCase):
    def inspect(self, data):
        return preflight.inspect_archive(io.BytesIO(data), 'fixture.jar', [preflight.MAX_TOTAL])

    def test_nested_requirements_and_side_scoped_mixins(self):
        metadata = {
            'schemaVersion': 1, 'id': 'fixture', 'version': '1.0',
            'depends': {'minecraft': '1.21.1', 'java': '>=21'},
            'entrypoints': {'main': [{'adapter': 'kotlin', 'value': 'example.Main'}]},
            'mixins': ['common.json', {'config': 'client.json', 'environment': 'client'}],
            'jars': [{'file': 'META-INF/jars/library.jar'}],
            'accessWidener': 'fixture.aw',
        }
        nested_jar = archive()
        data = archive(metadata, {
            'common.json': json.dumps({'mixins': ['One', 'Two'], 'plugin': 'example.Plugin'}),
            'client.json': json.dumps({'client': ['Three']}),
            'fixture.aw': '# comment\naccessWidener\tv2\tintermediary\n\naccessible class example/One\n',
            'META-INF/jars/library.jar': nested_jar,
        })
        report = self.inspect(data)
        self.assertEqual(report['depends']['minecraft'], '1.21.1')
        self.assertEqual(report['entrypoints'], metadata['entrypoints'])
        self.assertEqual(report['mixins'][0]['declared_entries']['mixins'], 2)
        self.assertEqual(report['mixins'][0]['plugin'], 'example.Plugin')
        self.assertEqual(report['mixins'][1]['environment'], 'client')
        self.assertEqual(report['access_widener']['declared_entries'], 1)
        self.assertEqual(report['nested_jars'][0]['sha512'], hashlib.sha512(nested_jar).hexdigest())

    def test_missing_declared_resource_fails(self):
        with self.assertRaises(KeyError):
            self.inspect(archive({'schemaVersion': 1, 'id': 'x', 'version': '1',
                                  'mixins': ['missing.json']}))

    def test_malformed_metadata_and_config_fail(self):
        with self.assertRaises(ValueError):
            self.inspect(archive({'schemaVersion': 2, 'id': 'x', 'version': '1'}))
        with self.assertRaises(ValueError):
            self.inspect(archive({'schemaVersion': 1, 'id': 'x', 'version': '1',
                                  'mixins': ['bad.json']}, {'bad.json': '{'}))

    def test_budget_and_depth_are_bounded(self):
        data = archive()
        with self.assertRaises(ValueError):
            preflight.inspect_archive(io.BytesIO(data), 'x', [1])
        with patch.object(preflight, 'MAX_DEPTH', 0):
            with self.assertRaises(ValueError):
                self.inspect(archive({'schemaVersion': 1, 'id': 'x', 'version': '1',
                                      'jars': [{'file': 'inner.jar'}]}, {'inner.jar': data}))

    def test_duplicate_names_rejected(self):
        stream = io.BytesIO(archive())
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(stream, 'a') as jar:
                jar.writestr('fabric.mod.json', '{}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.inspect(stream.getvalue())

    def test_pin_and_cli_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.jar'
            path.write_bytes(archive())
            digest = hashlib.sha512(path.read_bytes()).hexdigest()
            report = preflight.audit(path, digest)
            self.assertEqual(report['sha512'], digest)
            self.assertIn('not tested', report['assessment'])
            result = subprocess.run([sys.executable, str(Path(preflight.__file__)),
                                     str(path), '--sha512', '0' * 128], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('SHA-512 mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
