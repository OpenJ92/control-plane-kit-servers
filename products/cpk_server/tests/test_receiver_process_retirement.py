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

    def test_unowned_file_blocks_retirement_without_deleting_or_freeing_instance(self):
        from live_unlisted_receiver import ProcessCompute
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            port = recorded_processes(root)
            compute = ProcessCompute(port)
            selected = request(StartNode)
            self.assertEqual(compute.execute_with_authority(selected,
                SimpleNamespace(authority_ref=None)).kind, EffectResultKind.SUCCEEDED)
            child, wrapper = port.children[NAME], port.paths[NAME]
            foreign = wrapper.parent / "unowned.txt"
            foreign.write_bytes(b"preserve")
            removed = compute.execute_with_authority(replace(selected,
                operation=RemoveNodeResource(NodeTarget(NAME)), kind=RuntimeEffectKind.REALIZE_ACTIVITY,
                configuration_instances=None, products=()), SimpleNamespace(authority_ref=None))
            self.assertEqual(removed.kind, EffectResultKind.UNCERTAIN)
            self.assertIsNone(child.poll())
            self.assertTrue(wrapper.exists())
            self.assertEqual(foreign.read_bytes(), b"preserve")
            self.assertIn(NAME, port.paths)
            self.assertIn(NAME, compute.installed)
            with self.assertRaises(AssertionError):
                port.install(NAME, selected.products[0])
            port.close()
            self.assertEqual(foreign.read_bytes(), b"preserve")

    def test_partial_retirement_retains_bookkeeping_and_blocks_reinstallation(self):
        from live_unlisted_receiver import ProcessCompute
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            port = recorded_processes(root)
            compute = ProcessCompute(port)
            selected = request(StartNode)
            self.assertEqual(compute.execute_with_authority(selected,
                SimpleNamespace(authority_ref=None)).kind, EffectResultKind.SUCCEEDED)
            child = port.children[NAME]
            foreign = port.paths[NAME].parent / "appeared-during-stop.txt"
            def stop_with_new_file():
                child.returncode = 0
                foreign.write_bytes(b"preserve")
            child.terminate = stop_with_new_file
            removed = compute.execute_with_authority(replace(selected,
                operation=RemoveNodeResource(NodeTarget(NAME)), kind=RuntimeEffectKind.REALIZE_ACTIVITY,
                configuration_instances=None, products=()), SimpleNamespace(authority_ref=None))
            self.assertEqual(removed.kind, EffectResultKind.UNCERTAIN)
            self.assertIsNotNone(child.poll())
            self.assertFalse(port.paths[NAME].exists())
            self.assertIn(NAME, port.paths)
            self.assertIn(NAME, compute.installed)
            with self.assertRaises(AssertionError):
                port.install(NAME, selected.products[0])
            port.close()
            self.assertEqual(foreign.read_bytes(), b"preserve")

    def test_symlinked_installed_file_refuses_before_touching_foreign_target(self):
        from live_unlisted_receiver import ProcessCompute
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            port = recorded_processes(root)
            compute = ProcessCompute(port)
            selected = request(StartNode)
            self.assertEqual(compute.execute_with_authority(selected,
                SimpleNamespace(authority_ref=None)).kind, EffectResultKind.SUCCEEDED)
            wrapper = port.paths[NAME]
            foreign = root / "foreign.json"
            foreign.write_bytes(b"preserve")
            wrapper.unlink()
            wrapper.symlink_to(foreign)
            removed = compute.execute_with_authority(replace(selected,
                operation=RemoveNodeResource(NodeTarget(NAME)), kind=RuntimeEffectKind.REALIZE_ACTIVITY,
                configuration_instances=None, products=()), SimpleNamespace(authority_ref=None))
            self.assertEqual(removed.kind, EffectResultKind.UNCERTAIN)
            self.assertIsNone(port.children[NAME].poll())
            self.assertTrue(wrapper.is_symlink())
            self.assertEqual(foreign.read_bytes(), b"preserve")
            self.assertIn(NAME, compute.installed)
            port.close()
            self.assertEqual(foreign.read_bytes(), b"preserve")
