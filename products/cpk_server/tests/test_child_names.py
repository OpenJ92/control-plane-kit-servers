"""Account-local naming intent survives reopening and interrupted publication."""
from dataclasses import replace
import importlib
import importlib.util
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from uuid import UUID

from control_plane_kit_core.public_ingress import PublicIngressLifecycle


MODULE = "control_plane_kit_servers_cpk_server.client.child_names"


class ChildNamesTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec(MODULE), "child naming interface is missing")
        self.api = importlib.import_module(MODULE)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "child-installations"
        root = patch.object(self.api, "_assignment_root", side_effect=lambda: self.root)
        root.start()
        self.addCleanup(root.stop)

    def binding(self, **changes):
        roles = tuple(self.api.ChildIngressNameBinding(
            role=role, ingress_id="child-a-" + role,
            authority_ref="child-a-" + role + "-authority",
            lifecycle=PublicIngressLifecycle.EPHEMERAL)
            for role in ("api", "website", "management"))
        values = dict(parent_endpoint="https://parent.example.test",
            parent_installation_id="parent-a", parent_workspace_id="deployments",
            child_installation_id="child-a", zone_name="example.test", ingresses=roles)
        return self.api.ChildNameBinding(**{**values, **changes})

    def files(self):
        return tuple(sorted(self.root.iterdir())) if self.root.exists() else ()

    def committed(self):
        return tuple(path for path in self.files() if path.suffix == ".json")

    def test_create_and_reopen_preserve_one_public_assignment(self):
        binding = self.binding()
        with patch("socket.getaddrinfo", side_effect=AssertionError("unexpected provider call")):
            first = self.api.create_child_names(binding)
            self.assertEqual(self.api.reopen_child_names(binding), first)
            self.assertEqual(self.api.create_child_names(binding), first)
        self.assertEqual(first.binding, binding)
        names = {item.role: item.hostname for item in first.ingresses}
        self.assertEqual(names, {role: prefix + "-" + first.public_id + ".example.test"
            for role, prefix in (("api", "api"), ("website", "web"), ("management", "management"))})
        self.assertEqual(len(set(names.values())), 3)
        self.assertEqual(len(self.files()), 1)

    def test_reopen_does_not_allocate_a_public_identity(self):
        original = self.api.create_child_names(self.binding())
        with patch.object(self.api, "uuid4", side_effect=AssertionError("identity regenerated")):
            self.assertEqual(self.api.reopen_child_names(self.binding()), original)
            self.assertEqual(self.api.create_child_names(self.binding()), original)

    def test_distinct_new_children_have_distinct_valid_public_ids(self):
        first = self.api.create_child_names(self.binding())
        second = self.api.create_child_names(self.binding(child_installation_id="child-b"))
        self.assertNotEqual(first.public_id, second.public_id)
        for assignment in (first, second):
            parsed = UUID(assignment.public_id)
            self.assertEqual(parsed.version, 4)
            self.assertEqual(parsed.hex, assignment.public_id)

    def test_missing_record_on_reopen_is_refused_without_creation(self):
        with self.assertRaises(self.api.ChildNamingError):
            self.api.reopen_child_names(self.binding())
        self.assertFalse(self.committed())

    def test_zone_authority_and_lifecycle_changes_cannot_select_new_files(self):
        binding = self.binding()
        self.api.create_child_names(binding)
        before = {p.name: p.read_bytes() for p in self.files()}
        for altered in (replace(binding, zone_name="other.test"),
                replace(binding, ingresses=(replace(binding.ingresses[0], authority_ref="foreign"),
                    *binding.ingresses[1:])),
                replace(binding, ingresses=(replace(binding.ingresses[0],
                    lifecycle=PublicIngressLifecycle.RETAINED), *binding.ingresses[1:]))):
            for operation in (self.api.create_child_names, self.api.reopen_child_names):
                with self.assertRaises(self.api.ChildNamingError):
                    operation(altered)
        self.assertEqual({p.name: p.read_bytes() for p in self.files()}, before)

    def test_missing_role_duplicate_role_and_duplicate_ingress_are_refused(self):
        binding = self.binding()
        for roles in (binding.ingresses[:2],
                (binding.ingresses[0], binding.ingresses[0], binding.ingresses[2]),
                (binding.ingresses[0], replace(binding.ingresses[1],
                    ingress_id=binding.ingresses[0].ingress_id), binding.ingresses[2])):
            with self.assertRaises(self.api.ChildNamingError):
                self.api.create_child_names(replace(binding, ingresses=roles))
        self.assertFalse(self.files())

    def test_parent_workspace_and_child_are_part_of_the_reopen_key(self):
        binding = self.binding()
        self.api.create_child_names(binding)
        for change in ({"parent_endpoint": "https://other.example.test"},
                {"parent_installation_id": "other-parent"},
                {"parent_workspace_id": "other-workspace"},
                {"child_installation_id": "other-child"}):
            with self.assertRaises(self.api.ChildNamingError):
                self.api.reopen_child_names(replace(binding, **change))
        self.assertEqual(len(self.files()), 1)

    def test_truncated_or_changed_assignment_is_never_replaced(self):
        binding = self.binding()
        self.api.create_child_names(binding)
        path, = self.committed()
        valid = path.read_bytes()
        changed = json.loads(valid)
        changed["public_id"] = "not-a-public-uuid"
        for raw in (b"{", json.dumps(changed).encode()):
            path.write_bytes(raw)
            for operation in (self.api.create_child_names, self.api.reopen_child_names):
                with self.assertRaises(self.api.ChildNamingError):
                    operation(binding)
            self.assertEqual(path.read_bytes(), raw)

    def test_interruption_before_and_after_publication_preserves_pending_refusal(self):
        binding = self.binding()
        original_link = os.link
        for publish in (False, True):
            with self.subTest(published=publish), TemporaryDirectory() as directory:
                self.root = Path(directory) / "child-installations"

                def interrupted(source, destination, **kwargs):
                    if publish:
                        original_link(source, destination, **kwargs)
                    raise OSError("injected publication uncertainty")

                with patch.object(self.api.os, "link", side_effect=interrupted):
                    with self.assertRaises(self.api.ChildNamingError):
                        self.api.create_child_names(binding)
                before = {p.name: p.read_bytes() for p in self.files()}
                self.assertTrue(before)
                self.assertEqual(len(self.committed()), int(publish))
                for operation in (self.api.create_child_names, self.api.reopen_child_names):
                    with self.assertRaises(self.api.ChildNamingError):
                        operation(binding)
                self.assertEqual({p.name: p.read_bytes() for p in self.files()}, before)

    def test_contender_cannot_remove_the_creators_pending_record(self):
        binding = self.binding()
        original_link = os.link
        waiting, release = threading.Event(), threading.Event()
        completed, failed = [], []

        def blocked_link(source, destination, **kwargs):
            waiting.set()
            if not release.wait(5):
                raise OSError("test creator timeout")
            return original_link(source, destination, **kwargs)

        def create():
            try:
                completed.append(self.api.create_child_names(binding))
            except Exception as error:
                failed.append(type(error).__name__)

        with patch.object(self.api.os, "link", side_effect=blocked_link):
            creator = threading.Thread(target=create)
            creator.start()
            try:
                self.assertTrue(waiting.wait(5))
                before = {p.name: p.read_bytes() for p in self.files()}
                for operation in (self.api.create_child_names, self.api.reopen_child_names):
                    with self.assertRaises(self.api.ChildNamingError):
                        operation(binding)
                self.assertEqual({p.name: p.read_bytes() for p in self.files()}, before)
            finally:
                release.set()
                creator.join(5)
        self.assertFalse(creator.is_alive())
        self.assertEqual(failed, [])
        self.assertEqual(len(completed), 1)
        self.assertEqual(self.api.reopen_child_names(binding), completed[0])

    def test_success_syncs_directory_after_pending_removal(self):
        original_sync = os.fsync
        acknowledged = []

        def sync(descriptor):
            original_sync(descriptor)
            information = os.fstat(descriptor)
            root = self.root.stat()
            if stat.S_ISDIR(information.st_mode) and (information.st_dev, information.st_ino) == (root.st_dev, root.st_ino):
                files = self.files()
                if len(files) == 1 and files[0].suffix == ".json":
                    acknowledged.append(True)

        with patch.object(self.api.os, "fsync", side_effect=sync):
            self.api.create_child_names(self.binding())
        self.assertTrue(acknowledged)

