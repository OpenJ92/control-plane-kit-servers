"""Protected bootstrap material is created once in empty owned fixture volumes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from child_bootstrap_fixture import populate


class ChildBootstrapFixtureTests(unittest.TestCase):
    def directories(self, root):
        paths = tuple(root/name for name in ("provider","client","data"))
        for path in paths:
            path.mkdir()
        return paths

    def test_prepopulated_volume_is_refused_before_any_seed_write(self):
        with TemporaryDirectory() as directory:
            provider,client,data = self.directories(Path(directory))
            (provider/"credentials.json").write_bytes(b"foreign-fixture-marker")
            with self.assertRaisesRegex(ValueError,"not empty"):
                populate(provider,client,data)
            self.assertEqual((provider/"credentials.json").read_bytes(),b"foreign-fixture-marker")
            self.assertEqual(tuple(client.iterdir()),())
            self.assertEqual(tuple(data.iterdir()),())

    def test_fresh_seed_has_protected_ownership_and_refuses_reinitialization(self):
        with TemporaryDirectory() as directory:
            provider,client,data = self.directories(Path(directory))
            populate(provider,client,data)
            self.assertEqual({path.name for path in provider.iterdir()},{"master.key","credentials.json"})
            self.assertEqual({path.name for path in client.iterdir()},{"provider-token","application-value"})
            for path in provider.iterdir():
                self.assertEqual(path.stat().st_uid,10006)
                self.assertEqual(path.stat().st_mode & 0o777,0o400)
            with self.assertRaisesRegex(ValueError,"not empty"):
                populate(provider,client,data)
