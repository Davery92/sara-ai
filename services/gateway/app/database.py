import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

env_path = os.path.join(os.path.dirname(__file__), '../../.env')
load_dotenv(dotenv_path=env_path)

# Attempt to load DATABASE_URL directly
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# If DATABASE_URL is not set, try to construct it from component environment variables
if SQLALCHEMY_DATABASE_URL is None:
    pg_user = os.getenv("POSTGRES_USER")
    pg_pass = os.getenv("POSTGRES_PASSWORD")
    pg_host = os.getenv("POSTGRES_HOST")
    pg_port = os.getenv("POSTGRES_PORT")
    pg_db   = os.getenv("POSTGRES_DB")

    if all([pg_user, pg_pass, pg_host, pg_port, pg_db]):
        SQLALCHEMY_DATABASE_URL = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    else:
        missing_vars = [
            var_name for var_name, var_val in {
                "POSTGRES_USER": pg_user, "POSTGRES_PASSWORD": pg_pass,
                "POSTGRES_HOST": pg_host, "POSTGRES_PORT": pg_port,
                "POSTGRES_DB": pg_db
            }.items() if var_val is None
        ]
        if missing_vars:
            raise EnvironmentError(
                f"Database configuration error: DATABASE_URL is not set, "
                f"and the following component environment variables are missing: {', '.join(missing_vars)}. "
                f"Please ensure they are set in your .env file or environment."
            )
        # If somehow all components are None but missing_vars is empty (should not happen),
        # or if we want a default that will explicitly fail parsing if used:
        # SQLALCHEMY_DATABASE_URL = "postgresql://invalid:invalid@invalid:invalid/invalid" # Fallback to an invalid URL that won't parse 'port'
        # However, the EnvironmentError above is preferred.


if SQLALCHEMY_DATABASE_URL is None:
    # This state should ideally be prevented by the error check above if components were missing.
    # If it's reached, it means DATABASE_URL was None and construction also failed silently.
    raise EnvironmentError(
        "Failed to configure SQLALCHEMY_DATABASE_URL. "
        "Ensure DATABASE_URL or all POSTGRES_* variables are set in your .env file."
    )

try:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
except Exception as e:
    # Catch potential parsing errors (like the original ValueError) or other connection string issues
    raise ValueError(
        f"Failed to create database engine. The database URL was '{SQLALCHEMY_DATABASE_URL}'. "
        f"Error: {e}. Check your .env file for DATABASE_URL or POSTGRES_* variables, "
        f"and ensure the port is a number."
    ) from e

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 