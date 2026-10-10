"""Tests for the in-memory adapter: the shared contract, plus behaviour specific to memory."""

import unittest

from habits.adapters.memory_repository import InMemoryHabitRepository
from tests.adapters.repository_contract import HabitRepositoryContract


class InMemoryHabitRepositoryTests(HabitRepositoryContract, unittest.TestCase):
    def make_repository(self):
        return InMemoryHabitRepository()
