"""Smoke tests for the queue package."""


def test_package_imports():
    """The domain package is importable."""
    import domain

    assert domain is not None


def test_truth():
    """pytest itself is wired up correctly."""
    assert 1 + 1 == 2
