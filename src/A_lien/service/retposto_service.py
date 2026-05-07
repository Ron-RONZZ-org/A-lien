"""RetpostoService — composed from mixins.

Account management, IMAP sync, SMTP send, message operations.
All methods are provided by mixin classes below.
"""

from __future__ import annotations

from A.core.service import CRUDService
from A_lien.data.storage import get_db
from A_lien.imap import MessageStore

from A_lien.service.retposto_signature import RetpostoSignatureMixin
from A_lien.service.retposto_contact_mixin import RetpostoContactMixin
from A_lien.service.retposto_spamo import RetpostoSpamoMixin
from A_lien.service.retposto_accounts import RetpostoAccountsMixin
from A_lien.service.retposto_messaging import RetpostoMessagingMixin
from A_lien.service.retposto_msg_ops import RetpostoMessageOpsMixin
from A_lien.service.retposto_sync import RetpostoSyncMixin


class RetpostoService(
    CRUDService,
    MessageStore,
    RetpostoSignatureMixin,
    RetpostoContactMixin,
    RetpostoSpamoMixin,
    RetpostoAccountsMixin,
    RetpostoMessagingMixin,
    RetpostoMessageOpsMixin,
    RetpostoSyncMixin,
):
    """Email account management — composed from mixins."""

    def __init__(self, db):
        super().__init__(db, "kontoj", undo_size=5)


_retposto_service: RetpostoService | None = None


def get_retposto_service() -> RetpostoService:
    """Get the singleton RetpostoService."""
    global _retposto_service
    if _retposto_service is None:
        _retposto_service = RetpostoService(get_db())
    return _retposto_service
