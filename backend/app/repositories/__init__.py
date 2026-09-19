"""Repository layer: the only place that talks SQL.

Services depend on these functions, never on the ORM query API directly,
which keeps database concerns out of business logic and out of routes.
"""
