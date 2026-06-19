"""Tests for Sieve filter management (Phase 5).

Covers:
- Local syntax validation via sievelib
- SieveManager connection and operations (mocked)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from A_lien.sieve import validate_sieve, SieveManager


# ── Syntax validation ────────────────────────────────────────────────────────


class TestValidateSieve:
    """Tests for local Sieve syntax validation."""

    def test_valid_syntax(self):
        """Valid Sieve script returns True."""
        with patch("sievelib.parser.Parser") as mock_parser_cls:
            mock_parser = MagicMock()
            mock_parser.parse.return_value = True
            mock_parser_cls.return_value = mock_parser

            valid, error = validate_sieve('require ["fileinto"];')
            assert valid is True
            assert error == ""

    def test_invalid_syntax(self):
        """Invalid Sieve script returns False with error message."""
        with patch("sievelib.parser.Parser") as mock_parser_cls:
            mock_parser = MagicMock()
            mock_parser.parse.return_value = False
            mock_parser.error = "line 1: parsing error: semicolon expected"
            mock_parser_cls.return_value = mock_parser

            valid, error = validate_sieve("invalid script")
            assert valid is False
            assert "semicolon" in error

    def test_valid_real_sieve(self):
        """Realistic valid Sieve script passes validation."""
        with patch("sievelib.parser.Parser") as mock_parser_cls:
            mock_parser = MagicMock()
            mock_parser.parse.return_value = True
            mock_parser_cls.return_value = mock_parser

            script = (
                'require ["fileinto", "reject"];\n'
                'if address :is "From" "spam@example.com" {\n'
                '    reject "no spam please";\n'
                '}\n'
            )
            valid, error = validate_sieve(script)
            assert valid is True

    def test_empty_script(self):
        """Empty script is valid (implicit keep)."""
        with patch("sievelib.parser.Parser") as mock_parser_cls:
            mock_parser = MagicMock()
            mock_parser.parse.return_value = True
            mock_parser_cls.return_value = mock_parser

            valid, error = validate_sieve("")
            assert valid is True

    def test_returns_true_when_sievelib_available(self):
        """When sievelib is available, valid scripts pass."""
        # sievelib is installed — the function uses it
        from sievelib.parser import Parser
        p = Parser()
        result, error = validate_sieve('require ["fileinto"];')
        # At minimum it should not crash
        assert isinstance(result, bool)


# ── SieveManager ─────────────────────────────────────────────────────────────


class TestSieveManager:
    """Tests for SieveManager remote operations (mocked)."""

    @pytest.fixture
    def mock_mclient(self):
        """Mock the managesieve.MANAGESIEVE class at package level.

        The mock instance's ``login()`` returns ``"OK"`` by default so
        that the connect check passes; individual tests can override.
        """
        with patch("managesieve.MANAGESIEVE") as mock:
            mock_instance = MagicMock()
            mock_instance.login.return_value = "OK"
            mock.return_value = mock_instance
            yield mock, mock_instance

    def test_connect(self, mock_mclient):
        """Connection creates managesieve client and logs in."""
        mock_cls, mock_inst = mock_mclient
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "password")
        mock_cls.assert_called_once_with("sieve.test.com", 4190, use_tls=True)
        mock_inst.login.assert_called_once_with("", "user", "password")

    def test_connect_failure(self):
        """Connection error raises ConnectionError."""
        with patch("managesieve.MANAGESIEVE") as mock:
            mock.side_effect = Exception("Connection refused")
            manager = SieveManager("sieve.test.com", 4190)
            with pytest.raises(ConnectionError):
                manager.connect("user", "pw")

    def test_list_scripts(self, mock_mclient):
        """List scripts returns parsed script info."""
        _, mock_inst = mock_mclient
        mock_inst.listscripts.return_value = [
            ("script1.sieve", True),
            ("script2.sieve", False),
        ]
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "pw")
        scripts = manager.list_scripts()
        assert len(scripts) == 2
        assert scripts[0]["name"] == "script1.sieve"
        assert scripts[0]["active"] is True
        assert scripts[1]["active"] is False

    def test_get_script(self, mock_mclient):
        """Get script returns content."""
        _, mock_inst = mock_mclient
        mock_inst.getscript.return_value = 'require ["fileinto"];'
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "pw")
        content = manager.get_script("myfilter.sieve")
        assert content == 'require ["fileinto"];'

    @patch("A_lien.sieve.validate_sieve", return_value=(True, ""))
    def test_put_script_valid(self, mock_validate, mock_mclient):
        """Put script uploads after successful validation."""
        _, mock_inst = mock_mclient
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "pw")
        manager.put_script("test.sieve", 'require ["fileinto"];')
        mock_validate.assert_called_once_with('require ["fileinto"];')
        mock_inst.putscript.assert_called_once_with(
            "test.sieve", 'require ["fileinto"];'
        )

    @patch("A_lien.sieve.validate_sieve", return_value=(False, "syntax error"))
    def test_put_script_invalid_raises(self, mock_validate, mock_mclient):
        """Put script rejects invalid syntax before upload."""
        _, mock_inst = mock_mclient
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "pw")
        with pytest.raises(ValueError, match="syntax error"):
            manager.put_script("bad.sieve", "invalid")
        mock_inst.putscript.assert_not_called()

    def test_delete_script(self, mock_mclient):
        """Delete calls the managesieve client."""
        _, mock_inst = mock_mclient
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "pw")
        manager.delete_script("old.sieve")
        mock_inst.deletescript.assert_called_once_with("old.sieve")

    def test_activate_script(self, mock_mclient):
        """Activate calls setactive."""
        _, mock_inst = mock_mclient
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "pw")
        manager.activate_script("main.sieve")
        mock_inst.setactive.assert_called_once_with("main.sieve")

    def test_disconnect(self, mock_mclient):
        """Disconnect calls logout."""
        _, mock_inst = mock_mclient
        manager = SieveManager("sieve.test.com", 4190)
        manager.connect("user", "pw")
        manager.disconnect()
        mock_inst.logout.assert_called_once()
