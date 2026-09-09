"""Numeric ownership belongs only to actual protected-file recipients."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from control_plane_kit_servers_cpk_server import bootstrap


class RootFileRecipientTests(unittest.TestCase):
    def test_environment_only_node_never_requests_a_numeric_file_owner(self):
        owner = Mock(side_effect=ValueError("unsupported image user"))
        image = SimpleNamespace(secret_file_owner_uid=owner)
        self.assertIsNone(bootstrap.protected_file_owner([], image))
        owner.assert_not_called()

    def test_file_recipient_uses_the_image_owner_and_preserves_refusal(self):
        files = [{"target": "/run/secrets/control"}]
        owner = Mock(return_value=10001)
        image = SimpleNamespace(secret_file_owner_uid=owner)
        self.assertEqual(bootstrap.protected_file_owner(files, image), 10001)
        owner.assert_called_once_with()
        refusal = ValueError("unsupported image user")
        owner = Mock(side_effect=refusal)
        image = SimpleNamespace(secret_file_owner_uid=owner)
        with self.assertRaises(ValueError) as caught:
            bootstrap.protected_file_owner(files, image)
        self.assertIs(caught.exception, refusal)
        owner.assert_called_once_with()
