import unittest


class TestProject(unittest.TestCase):
    def test_project_info(self):
        from abd.project import Project
        root = Project.get_project_root()
        self.assertTrue(root.exists())
        self.assertTrue(root.is_dir())
        print(f"Project root: {root}")
        self.assertTrue((root / "abd").exists())
