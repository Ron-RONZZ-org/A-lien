"""A-lien test configuration — prevents tests from touching real DB or keyring."""

import pytest
from A.core.testing import patch_paths, patch_keyring


@pytest.fixture(autouse=True)
def isolate_lien(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    """Redirect all A-core path functions to *tmp_path* and mock keyring.

    Also resets service singletons so that the next call to
    ``get_retposto_service()`` / ``get_kontakto_service()`` creates a fresh
    service pointing at the isolated database.
    """
    patch_paths(monkeypatch, tmp_path)
    patch_keyring(monkeypatch)

    # Reset service singletons so they use the patched (tmp_path) database.
    import A_lien.service.retposto_service as rp
    import A_lien.service.kontakto_service as kt

    rp._retposto_service = None
    kt._kontakto_service = None
