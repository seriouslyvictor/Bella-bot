"""Single-instance Evolution/PostgreSQL connection policy.

The Compose and shell contracts repeat these values because they cannot import
Python. Deployment contract tests bind those explicit values to this module.
"""

EVOLUTION_ROLE = "evolution"
ROLE_CONNECTION_LIMIT = 30
WARNING_THRESHOLD = 24
AUTH_POOL_CEILING = 20
QUIET_AUTH_IDLE_CEILING = 5
ROLE_IDLE_SESSION_TIMEOUT = "5min"
MIN_RECONNECT_CYCLES = 30
MIN_PLATEAU_SAMPLES = 10

