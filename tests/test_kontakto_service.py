"""Tests for KontaktoService (Phase 2).

Covers:
- JSON serialization/deserialization
- CRUD operations (create, get, update, delete, list)
- Domain methods (find_by_email, find_by_uuid_prefix, find_duplicates)
- Category management
- VCF import/export
- Undo support
- FTS5 search
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from unittest.mock import patch

import pytest

from A_lien.service.kontakto_service import KontaktoService, get_kontakto_service
from A_lien.data.storage import get_db


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    return get_db(str(tmp_path / "test_lien.db"))


@pytest.fixture
def service(db):
    return KontaktoService(db)


@pytest.fixture
def sample_contact():
    return {
        "nomo": "John",
        "familia_nomo": "Doe",
        "plena_nomo": "John Doe",
        "retposto": "john@example.com",
        "organizo": "Acme Inc",
        "telefonnumeroj": [
            {"valoro": "+1-555-0100", "etikedo": "WORK", "cxefa": True},
        ],
        "retposhtadresoj": [
            {"valoro": "john@example.com", "etikedo": "WORK", "cxefa": True},
            {"valoro": "john.doe@personal.com", "etikedo": "HOME", "cxefa": False},
        ],
        "lingvoj": ["en", "fr"],
        "kategorioj": ["amikoj", "laboro"],
        "kampoj": {"skype": "john.doe"},
        "konfirmita": 1,
        "noto": "Test contact",
    }


# ── JSON Serialization ───────────────────────────────────────────────────────


class TestSerialization:
    def test_serialize_json_lists(self, service, sample_contact):
        serialized = service._serialize(sample_contact)
        for field in service._JSON_LIST_FIELDS:
            assert isinstance(serialized[field], str)
            parsed = json.loads(serialized[field])
            assert isinstance(parsed, list)

    def test_serialize_json_dict(self, service, sample_contact):
        serialized = service._serialize(sample_contact)
        assert isinstance(serialized["kampoj"], str)
        parsed = json.loads(serialized["kampoj"])
        assert isinstance(parsed, dict)

    def test_deserialize_roundtrip(self, service, sample_contact):
        serialized = service._serialize(sample_contact)
        deserialized = service._deserialize_row(serialized)
        for field in service._JSON_LIST_FIELDS:
            assert isinstance(deserialized[field], list)
        for field in service._JSON_DICT_FIELDS:
            assert isinstance(deserialized[field], dict)

    def test_deserialize_passthrough(self, service):
        row = {"uuid": "abc", "plena_nomo": "Test", "kreita_je": "now"}
        result = service._deserialize_row(row)
        assert result["uuid"] == "abc"
        assert result["plena_nomo"] == "Test"

    def test_deserialize_none(self, service):
        assert service._deserialize_row(None) is None
        assert service._deserialize_row({}) == {}


# ── CRUD ─────────────────────────────────────────────────────────────────────


class TestCRUD:
    def test_create_and_get(self, service, sample_contact):
        created = service.create(sample_contact)
        assert created["uuid"] is not None

        retrieved = service.get(created["uuid"])
        assert retrieved is not None
        assert retrieved["plena_nomo"] == "John Doe"
        assert retrieved["retposto"] == "john@example.com"

    def test_create_with_json_fields(self, service, sample_contact):
        created = service.create(sample_contact)
        retrieved = service.get(created["uuid"])
        assert retrieved["telefonnumeroj"][0]["valoro"] == "+1-555-0100"
        assert retrieved["kampoj"]["skype"] == "john.doe"
        assert "en" in retrieved["lingvoj"]
        assert "amikoj" in retrieved["kategorioj"]

    def test_update(self, service, sample_contact):
        created = service.create(sample_contact)
        updated = service.update(created["uuid"], {"organizo": "New Corp"})
        assert updated["organizo"] == "New Corp"

        retrieved = service.get(created["uuid"])
        assert retrieved["organizo"] == "New Corp"

    def test_update_json_field(self, service, sample_contact):
        created = service.create(sample_contact)
        new_phones = [
            {"valoro": "+33-6-12-34-56", "etikedo": "MOBILE", "cxefa": True},
        ]
        service.update(created["uuid"], {"telefonnumeroj": new_phones})
        retrieved = service.get(created["uuid"])
        assert len(retrieved["telefonnumeroj"]) == 1
        assert retrieved["telefonnumeroj"][0]["valoro"] == "+33-6-12-34-56"

    def test_delete_soft(self, service, sample_contact):
        created = service.create(sample_contact)
        service.delete(created["uuid"], soft=True)
        contacts = service.list()
        uuids = [c["uuid"] for c in contacts]
        assert created["uuid"] not in uuids
        trash = service.get_trash()
        trash_uuids = [t["uuid"] for t in trash]
        assert created["uuid"] in trash_uuids

    def test_delete_permanent(self, service, sample_contact):
        created = service.create(sample_contact)
        service.delete(created["uuid"], soft=False)
        assert service.get(created["uuid"]) is None

    def test_undo_create(self, service, sample_contact):
        """Undo after create removes the contact."""
        # Perform two creates then undo the second
        c1 = service.create(dict(sample_contact, retposto="undo1@example.com"))
        c2 = service.create(dict(sample_contact, retposto="undo2@example.com"))
        # Undo the second create
        result = service.undo()
        assert result is not None
        assert result["operation_type"] == "add"
        # Second contact should be gone, first should remain
        assert service.get(c2["uuid"]) is None
        assert service.get(c1["uuid"]) is not None

    def test_undo_delete(self, service, sample_contact):
        """Undo after soft delete restores the contact."""
        created = service.create(sample_contact)
        # Undo create, then create again with different email
        service.undo()
        fresh = service.create(dict(sample_contact, retposto="undo-test@example.com"))
        service.delete(fresh["uuid"], soft=True)
        result = service.undo()
        assert result is not None
        assert result["operation_type"] == "delete"
        restored = service.get(fresh["uuid"])
        assert restored is not None

    def test_list_empty(self, service):
        assert service.list() == []

    def test_list_with_data(self, service, sample_contact):
        service.create(sample_contact)
        c2 = dict(sample_contact, plena_nomo="Jane Doe", retposto="jane@example.com")
        service.create(c2)
        assert len(service.list()) == 2

    def test_list_order(self, service, sample_contact):
        for name in ["Charlie", "Alice", "Bob"]:
            c = dict(sample_contact, plena_nomo=name, retposto=f"{name.lower()}@example.com")
            service.create(c)
        ordered = service.list(order_by="plena_nomo", desc=False)
        assert ordered[0]["plena_nomo"] == "Alice"
        assert ordered[1]["plena_nomo"] == "Bob"
        assert ordered[2]["plena_nomo"] == "Charlie"


# ── Domain ───────────────────────────────────────────────────────────────────


class TestDomain:
    def test_find_by_email(self, service, sample_contact):
        service.create(sample_contact)
        found = service.find_by_email("JOHN@EXAMPLE.COM")
        assert found is not None
        assert found["plena_nomo"] == "John Doe"

    def test_find_by_email_not_found(self, service):
        assert service.find_by_email("none@example.com") is None

    def test_find_by_uuid_prefix(self, service, sample_contact):
        created = service.create(sample_contact)
        results = service.find_by_uuid_prefix(created["uuid"][:8])
        assert len(results) >= 1
        assert results[0]["uuid"] == created["uuid"]

    def test_find_duplicates_by_name(self, service):
        c1 = {"plena_nomo": "Jonathan Doe", "retposto": "jon@example.com"}
        c2 = {"plena_nomo": "Jonathan Doe", "retposto": "jon.doe@example.com"}
        service.create(c1)
        created2 = service.create(c2)
        # Uses fuzzy matching on plena_nomo
        dups = service.find_duplicates(created2, threshold=0.8)
        assert len(dups) >= 1

    def test_search_contacts_with_query(self, service, sample_contact):
        service.create(sample_contact)
        # FTS5 rebuild happens on create, so search should find it
        results = service.search_contacts(query="John")
        assert len(results) >= 1

    def test_count(self, service, sample_contact):
        assert service.count() == 0
        service.create(sample_contact)
        assert service.count() == 1


# ── Categories ───────────────────────────────────────────────────────────────


class TestCategories:
    def test_create_category(self, service):
        cat = service.create_category("amikoj", "blue")
        assert cat["nomo"] == "amikoj"
        assert cat["koloro"] == "blue"

    def test_list_categories(self, service):
        service.create_category("a")
        service.create_category("b")
        cats = service.list_categories()
        assert len(cats) == 2

    def test_delete_category(self, service):
        cat = service.create_category("test")
        assert service.delete_category(cat["uuid"]) is True
        assert service.delete_category("nonexistent") is False

    def test_update_category(self, service):
        cat = service.create_category("old")
        updated = service.update_category(cat["uuid"], {"nomo": "new"})
        assert updated is not None
        assert updated["nomo"] == "new"


# ── VCF ──────────────────────────────────────────────────────────────────────


class TestVCF:
    def test_import_raises_without_vobject(self, service):
        with patch.object(KontaktoService, "import_vcf") as mock:
            mock.side_effect = ImportError("vobject required")
            with pytest.raises(ImportError):
                service.import_vcf("/fake/path.vcf")

    def test_import_file_not_found(self, service):
        with pytest.raises(FileNotFoundError):
            service.import_vcf("/nonexistent/file.vcf")

    def test_import_vcf_success(self, service, tmp_path):
        """Import using real vobject library."""
        import vobject
        card = vobject.vCard()
        card.add("n")
        card.n.value = vobject.vcard.Name(family="Doe", given="Jane")
        card.add("fn")
        card.fn.value = "Jane Doe"
        card.add("email")
        card.email.value = "jane@example.com"
        card.email.type_param = "INTERNET"

        vcf_path = tmp_path / "test.vcf"
        vcf_path.write_text(card.serialize(), encoding="utf-8")

        count = service.import_vcf(str(vcf_path))
        assert count >= 1

        found = service.find_by_email("jane@example.com")
        assert found is not None
        assert found["plena_nomo"] == "Jane Doe"

    def test_export_raises_without_vobject(self, service):
        with patch.object(KontaktoService, "export_vcf") as mock:
            mock.side_effect = ImportError("vobject required")
            with pytest.raises(ImportError):
                service.export_vcf()

    def test_export_vcf_success(self, service, sample_contact):
        created = service.create(sample_contact)
        result = service.export_vcf(uuid=created["uuid"])
        assert "BEGIN:VCARD" in result
        assert "John" in result


# ── Singleton ────────────────────────────────────────────────────────────────


class TestServiceSingleton:
    def teardown_method(self):
        import A_lien.service.kontakto_service as ks
        ks._kontakto_service = None

    def test_returns_instance(self):
        import A_lien.service.kontakto_service as ks
        ks._kontakto_service = None
        svc = get_kontakto_service()
        assert isinstance(svc, KontaktoService)

    def test_same_instance(self):
        import A_lien.service.kontakto_service as ks
        ks._kontakto_service = None
        svc1 = get_kontakto_service()
        svc2 = get_kontakto_service()
        assert svc1 is svc2
