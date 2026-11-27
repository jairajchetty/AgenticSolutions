"""Errors whose message is safe to show to a person as is."""


class UserFacingError(Exception):
    """A plain, specific failure. The web runner shows `str(error)` to the visitor."""
