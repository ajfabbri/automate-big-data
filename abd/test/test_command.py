import abd.core.command as cmd

import logging
import unittest

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class TestCommand(unittest.TestCase):

    def test_run_command_output(self):
        (err, output) = cmd.run("whoami")
        self.assertEqual(err, 0)
        self.assertGreater(len(output), 0)
        log.info(f"whoami output: '{output}'")

        (err, output) = cmd.run("echo \"some data\" > /tmp/testfile.test_command_py")
        self.assertEqual(err, 0)

        (err, output) = cmd.run("bash -elc 'md5sum /tmp/testfile.test_command_py "
                                + "| awk '\"'\"'{print $1}'\"'\"")
        self.assertEqual(err, 0)
        log.info(f"md5sum output: '{output}'")
        self.assertEqual(output, "5febbef14389ebcfc3e501fa1091adcb")
