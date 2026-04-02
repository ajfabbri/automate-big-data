from unittest import TestCase


from abd.abd import main


class TestClusterSSH(TestCase):
    def test_cluster_ssh(self):
        err = main(["exec", "-t", "deploy:shared-ssh"])
        self.assertNotEqual(err, 0)
