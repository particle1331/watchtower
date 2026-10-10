"""End-to-end test of the composition root, using a temporary SQLite file."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from habits.main import DB_ENV_VAR, main


class MainTest(unittest.TestCase):
    def test_add_checkin_and_list_persist_across_invocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "habits.sqlite3")
            with mock.patch.dict(os.environ, {DB_ENV_VAR: db}):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["add", "Read"]), 0)
                    self.assertEqual(main(["checkin", "1"]), 0)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["list"]), 0)
            self.assertIn("streak   1  Read", out.getvalue())

    def test_unopenable_database_is_a_clean_error(self):
        with mock.patch.dict(os.environ, {DB_ENV_VAR: "/nonexistent-dir-for-test/h.sqlite3"}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(main(["list"]), 1)
        self.assertIn("cannot open database", err.getvalue())


if __name__ == "__main__":
    unittest.main()
