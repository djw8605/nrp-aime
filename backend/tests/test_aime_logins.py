"""Tests for the AMIE login length helper."""

import pytest

from app.services.aime.logins import AMIE_LOGIN_MAX_LENGTH, amie_login

CILOGON_URL = "http://cilogon.org/serverE/users/546379"


class TestAmieLogin:
    def test_limit_is_thirty(self):
        assert AMIE_LOGIN_MAX_LENGTH == 30

    @pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
    def test_none_and_blank_return_none(self, value):
        assert amie_login(value) is None

    def test_short_login_unchanged(self):
        assert amie_login("alice_nrp") == "alice_nrp"

    def test_strips_whitespace(self):
        assert amie_login("  alice_nrp \n") == "alice_nrp"

    def test_exactly_thirty_unchanged(self):
        login = "a" * 30
        assert amie_login(login) == login

    def test_cilogon_url_keeps_last_thirty(self):
        assert len(CILOGON_URL) == 39
        assert amie_login(CILOGON_URL) == "logon.org/serverE/users/546379"
