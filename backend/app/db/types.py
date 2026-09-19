from sqlalchemy import JSON, BigInteger, Integer
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on PostgreSQL (the production target), plain JSON elsewhere so the
# test suite can run against SQLite without a database server.
FlexibleJSON = JSON().with_variant(JSONB(), "postgresql")

# SQLite only auto-increments a column declared exactly INTEGER PRIMARY KEY,
# so BIGINT keys are mapped down for that dialect. PostgreSQL still gets a
# real bigint.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")
