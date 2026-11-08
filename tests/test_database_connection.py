# ==========================================
# 1. IMPORTS
# ==========================================

# Import logging to capture connection log messages
import logging

# Import traceback to check formatted tracebacks for the password
import traceback

# Import psycopg to raise the driver's real error type
import psycopg

# Import pytest for fixtures and exception checks
import pytest

# Import the connection module under test
from database import connection
from database.connection import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    connect_to_production_database,
    connect_to_test_database,
)


# ==========================================
# 2. TEST HELPERS
# ==========================================

# A fake password that must never appear in logs or errors
FAKE_PASSWORD = "s3cret-test-password"

DATABASE_SETTINGS = {
    "PGHOST": "localhost",
    "PGPORT": "5432",
    "PGUSER": "restaurant_assistant_app",
    "PGPASSWORD": FAKE_PASSWORD,
    "PGDATABASE": "restaurant_assistant",
    "PGDATABASE_TEST": "restaurant_assistant_test",
}


@pytest.fixture
def database_settings(monkeypatch):
    """
    Set every database variable to a known test value.
    """

    for name, value in DATABASE_SETTINGS.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def fake_connect(monkeypatch):
    """
    Replace psycopg.connect so no PostgreSQL server is needed.
    Returns the list of keyword arguments each call received.
    """

    calls = []

    def record_call(**kwargs):
        calls.append(kwargs)
        return "fake connection"

    monkeypatch.setattr(connection.psycopg, "connect", record_call)
    return calls


# ==========================================
# 3. DATABASE SELECTION TESTS
# ==========================================

@pytest.mark.usefixtures("database_settings")
def test_production_connection_uses_production_settings(fake_connect):
    result = connect_to_production_database()

    assert result == "fake connection"
    assert fake_connect == [{
        "host": "localhost",
        "port": "5432",
        "user": "restaurant_assistant_app",
        "password": FAKE_PASSWORD,
        "dbname": "restaurant_assistant",
    }]


@pytest.mark.usefixtures("database_settings")
def test_test_connection_uses_test_database(fake_connect):
    connect_to_test_database()

    # Same shared settings, but the test database is selected
    assert fake_connect[0]["dbname"] == "restaurant_assistant_test"
    assert fake_connect[0]["user"] == "restaurant_assistant_app"


# ==========================================
# 4. MISSING CONFIGURATION TESTS
# ==========================================

@pytest.mark.usefixtures("database_settings")
@pytest.mark.parametrize("missing_name", list(DATABASE_SETTINGS))
def test_missing_variable_is_reported_by_name(monkeypatch, fake_connect, missing_name):
    monkeypatch.delenv(missing_name)

    # PGDATABASE_TEST is only required for the test database, and vice versa
    connect = (
        connect_to_test_database
        if missing_name == "PGDATABASE_TEST"
        else connect_to_production_database
    )

    with pytest.raises(DatabaseConfigurationError, match=missing_name):
        connect()

    # No connection is attempted with incomplete settings
    assert fake_connect == []


@pytest.mark.usefixtures("database_settings")
def test_empty_variable_counts_as_missing(monkeypatch, fake_connect):
    monkeypatch.setenv("PGHOST", "")

    with pytest.raises(DatabaseConfigurationError, match="PGHOST"):
        connect_to_production_database()


@pytest.mark.usefixtures("database_settings")
def test_production_does_not_require_test_database(monkeypatch, fake_connect):
    monkeypatch.delenv("PGDATABASE_TEST")

    connect_to_production_database()

    assert fake_connect[0]["dbname"] == "restaurant_assistant"


# ==========================================
# 5. CONNECTION FAILURE AND SECRECY TESTS
# ==========================================

@pytest.mark.usefixtures("database_settings")
def test_connection_failure_is_clear_and_hides_password(monkeypatch, caplog):

    # Simulate a driver error that (unusually) echoes the password
    def failing_connect(**kwargs):
        raise psycopg.OperationalError(
            f"password authentication failed (password={FAKE_PASSWORD})"
        )

    monkeypatch.setattr(connection.psycopg, "connect", failing_connect)

    with caplog.at_level(logging.INFO, logger="restaurant_pipeline"):
        with pytest.raises(DatabaseConnectionError) as error_info:
            connect_to_test_database()

    message = str(error_info.value)

    # The error names the target and keeps the driver's reason
    assert "restaurant_assistant_test" in message
    assert "localhost:5432" in message
    assert "password authentication failed" in message

    # The password is in neither the error, its chain, its traceback, nor the logs
    assert FAKE_PASSWORD not in message
    assert error_info.value.__cause__ is None
    assert error_info.value.__context__ is None
    formatted = "".join(traceback.TracebackException.from_exception(
        error_info.value, capture_locals=True
    ).format())
    assert FAKE_PASSWORD not in formatted
    assert FAKE_PASSWORD not in caplog.text
    assert "Could not connect" in caplog.text


@pytest.mark.usefixtures("database_settings")
def test_successful_connection_log_hides_password(fake_connect, caplog):
    with caplog.at_level(logging.INFO, logger="restaurant_pipeline"):
        connect_to_production_database()

    assert "restaurant_assistant" in caplog.text
    assert FAKE_PASSWORD not in caplog.text
