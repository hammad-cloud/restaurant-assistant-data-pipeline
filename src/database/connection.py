
# ==========================================
# 1. IMPORTS
# ==========================================

# Import logging to record connection attempts without secrets.
import logging

# Import os to read database settings from environment variables.
import os

# Import psycopg, the PostgreSQL driver.
import psycopg


# ==========================================
# 2. CONFIGURATION
# ==========================================

# Use the same named logger as the rest of the pipeline.
logger = logging.getLogger("restaurant_pipeline")

# Settings shared by the production and test databases.
SHARED_VARIABLES = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD")


class DatabaseConfigurationError(RuntimeError):
    """Raised when required database environment variables are missing."""


class DatabaseConnectionError(RuntimeError):
    """Raised when PostgreSQL cannot be reached or rejects the connection."""


# ==========================================
# 3. SHARED CONNECTION LOGIC
# ==========================================

def _connect(database_variable: str) -> psycopg.Connection:
    """
    Open a PostgreSQL connection using environment variables.

    Args:
        database_variable: Name of the variable holding the database name
            (PGDATABASE or PGDATABASE_TEST).

    Returns:
        An open psycopg connection.

    Raises:
        DatabaseConfigurationError: If a required variable is missing or empty.
        DatabaseConnectionError: If the connection attempt fails.
    """

    # Check every required variable, reporting names only, never values.
    names = (*SHARED_VARIABLES, database_variable)
    missing = [name for name in names if not os.environ.get(name)]

    if missing:
        raise DatabaseConfigurationError(
            "Missing required database environment variables: "
            + ", ".join(missing)
        )

    host, port, user, password, database = (os.environ[name] for name in names)

    # Describe the target without the password, for logs and error messages.
    target = f"database '{database}' on {host}:{port} as user '{user}'"

    logger.info("Connecting to %s.", target)

    try:
        return psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database
        )
    except psycopg.OperationalError as error:
        # Keep the driver's reason, but strip the password in case it appears.
        reason = str(error).replace(password, "***").strip()

    # Raise outside the except block so the driver error is not kept as
    # __context__, and drop the password so tracebacks capturing locals miss it.
    del password
    logger.error("Could not connect to %s: %s", target, reason)
    raise DatabaseConnectionError(f"Could not connect to {target}: {reason}")


# ==========================================
# 4. PUBLIC CONNECTION FUNCTIONS
# ==========================================

def connect_to_production_database() -> psycopg.Connection:
    """
    Connect to the production database named by PGDATABASE.

    Returns:
        An open psycopg connection.
    """

    return _connect("PGDATABASE")


def connect_to_test_database() -> psycopg.Connection:
    """
    Connect to the test database named by PGDATABASE_TEST.

    Returns:
        An open psycopg connection.
    """

    return _connect("PGDATABASE_TEST")
