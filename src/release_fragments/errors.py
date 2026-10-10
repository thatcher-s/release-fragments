"""The single exception type the CLI turns into a non-zero exit; no I/O."""


class ReleaseFragmentsError(Exception):
    """A user-facing failure: bad input, a policy violation, or a failed release step."""
