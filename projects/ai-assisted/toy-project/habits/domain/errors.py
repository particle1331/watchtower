"""Domain errors. Domain rule violations raise a DomainError subclass."""


class DomainError(Exception):
    """Base class for violations of domain rules."""


class InvalidHabitName(DomainError):
    """A habit name is empty or longer than the allowed length."""


class DuplicateCheckIn(DomainError):
    """A habit already has a check-in for the given day."""


class HabitNotFound(DomainError):
    """No habit exists with the given id."""
