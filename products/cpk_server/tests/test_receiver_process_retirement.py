"""Owned process-port retirement; the joined witness supplies actual SDK processes."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationMediaType
from control_plane_kit_core.planning import NodeTarget, RemoveNodeResource, StartNode
from control_plane_kit_core.runtime_effects import EffectResultKind, RuntimeEffectKind
from test_unlisted_process_material import NAME, request


class RecordedChild:
    """Only a child handle double; no control-plane or lifecycle owner behavior."""
    def __init__(self, pid):
        self.pid, self.returncode, self.stdout = pid, None, BytesIO()

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout):
        assert self.returncode is not None
        return self.returncode


def recorded_processes(root):
    # Match the existing process-port tests: importing the live composition
    # during discovery would retain owners across import-isolation tests.
    from live_unlisted_receiver import ReceiverProcesses

    class RecordedProcesses(ReceiverProcesses):
        def selected_files(self, name, material):
            return tuple(ConfigurationArtifact(identity, str(self.root / name / filename),
                ConfigurationMediaType.JSON, '{}') for identity, filename in
                (("wrapper", "wrapper.json"), ("application", "colors.json")))

        def launch(self, name):
            self.generation += 1
            self.children[name] = RecordedChild(self.generation)
            self.identities[name] = str(self.generation) * 64
            self.origins[name] = "http://owned.invalid"
            self.tokens[name] = ("private-test-token", "/health")

    return RecordedProcesses(root, root)


class ReceiverProcessRetirementTests(unittest.TestCase):
    def test_remove_retires_exact_files_and_allows_fresh_install_without_touching_peer(self):
        from live_unlisted_receiver import ProcessCompute
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            port = recorded_processes(root)
            compute = ProcessCompute(port)
            selected = request(StartNode)
            first = compute.execute_with_authority(selected, SimpleNamespace(authority_ref=None))
            self.assertEqual(first.kind, EffectResultKind.SUCCEEDED)
            old = port.children[NAME]
            peer = root / "peer"
            peer.mkdir()
            foreign = peer / "keep.json"
            foreign.write_bytes(b"keep")
            paths = (port.paths[NAME], port.application_paths[NAME])
            removed = compute.execute_with_authority(replace(selected,
                operation=RemoveNodeResource(NodeTarget(NAME)),
                kind=RuntimeEffectKind.REALIZE_ACTIVITY, configuration_instances=None,
                products=()), SimpleNamespace(authority_ref=None))
            self.assertEqual(removed.kind, EffectResultKind.SUCCEEDED)
            self.assertIsNotNone(old.poll())
            self.assertTrue(all(not path.exists() for path in paths), "removal retained installed files")
            self.assertFalse((root / NAME).exists())
            for mapping in (port.paths, port.application_paths, port.hashes, port.identities,
                    port.tokens, port.origins, port.children, compute.installed, compute.identities):
                self.assertNotIn(NAME, mapping)
            self.assertEqual(foreign.read_bytes(), b"keep")
            fresh = compute.execute_with_authority(selected, SimpleNamespace(authority_ref=None))
            self.assertEqual(fresh.kind, EffectResultKind.SUCCEEDED)
            self.assertIsNot(port.children[NAME], old)
            self.assertTrue(all(path.exists() for path in paths))
            port.close()
            self.assertEqual(foreign.read_bytes(), b"keep")
