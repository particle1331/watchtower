"""CLI tests: argument handling and output, against the in-memory adapter."""

import datetime
import io
import unittest

from habits.adapters.memory_repository import InMemoryHabitRepository
from habits.application.habit_service import HabitService
from habits.cli.commands import EXIT_DOMAIN_ERROR, EXIT_OK, run

TODAY = datetime.date(2026, 10, 9)


class CommandsTest(unittest.TestCase):
    def setUp(self):
        self.service = HabitService(InMemoryHabitRepository())

    def run_cli(self, *argv):
        # Fresh buffers per call, so each assertion sees only that command's output.
        out, err = io.StringIO(), io.StringIO()
        code = run(list(argv), self.service, TODAY, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_add_prints_new_id(self):
        code, out, _ = self.run_cli("add", "Read")
        self.assertEqual((code, out), (EXIT_OK, "added habit 1: Read\n"))

    def test_add_invalid_name_is_a_domain_error_on_stderr(self):
        code, out, err = self.run_cli("add", "   ")
        self.assertEqual(code, EXIT_DOMAIN_ERROR)
        self.assertEqual(out, "")
        self.assertIn("habit name must not be empty", err)

    def test_checkin_defaults_to_today(self):
        self.run_cli("add", "Read")
        code, out, _ = self.run_cli("checkin", "1")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("checked in habit 1 for 2026-10-09", out)

    def test_checkin_with_explicit_date(self):
        self.run_cli("add", "Read")
        code, out, _ = self.run_cli("checkin", "1", "--date", "2026-10-01")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("for 2026-10-01", out)

    def test_checkin_missing_habit_is_a_domain_error(self):
        code, _, err = self.run_cli("checkin", "7")
        self.assertEqual(code, EXIT_DOMAIN_ERROR)
        self.assertIn("no habit with id 7", err)

    def test_duplicate_checkin_is_a_domain_error(self):
        self.run_cli("add", "Read")
        self.run_cli("checkin", "1")
        code, _, err = self.run_cli("checkin", "1")
        self.assertEqual(code, EXIT_DOMAIN_ERROR)
        self.assertIn("already checked in", err)

    def test_list_empty(self):
        code, out, _ = self.run_cli("list")
        self.assertEqual((code, out), (EXIT_OK, "No habits yet.\n"))

    def test_list_shows_streaks(self):
        self.run_cli("add", "Read")
        self.run_cli("checkin", "1")
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "  1  streak   1  Read\n")

    def test_bad_date_is_a_usage_error(self):
        self.run_cli("add", "Read")
        with self.assertRaises(SystemExit) as caught:
            self.run_cli("checkin", "1", "--date", "09/10/2026")
        self.assertEqual(caught.exception.code, 2)

    def test_missing_command_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_cli()
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()


class ExportCommandTest(unittest.TestCase):
    def test_export_prints_versioned_json_document(self):
        import json

        service = HabitService(InMemoryHabitRepository())
        service.add_habit("Read")
        service.check_in(1, TODAY)
        out = io.StringIO()
        code = run(["export"], service, TODAY, out=out, err=io.StringIO())
        self.assertEqual(code, EXIT_OK)
        document = json.loads(out.getvalue())
        self.assertEqual(document, {
            "version": 1,
            "habits": [{"id": 1, "name": "Read", "check_ins": ["2026-10-09"]}],
        })

    def test_export_empty_store(self):
        import json

        out = io.StringIO()
        run(["export"], HabitService(InMemoryHabitRepository()), TODAY, out=out, err=io.StringIO())
        self.assertEqual(json.loads(out.getvalue()), {"version": 1, "habits": []})
