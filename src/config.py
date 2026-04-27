"""
Configuration constants for the Oracle 2PC Simulator.

All values are read from environment variables so the same image can be used
against different Oracle deployments without rebuilding.  Defaults match the
values set in the project .env file and are suitable for local development.

Seed balances (SEED_NODE_A, SEED_NODE_B) define the account state that the
test suite restores before and after each test run.
"""

import os

APP_USER = os.environ.get("APP_USER", "app_user")
APP_USER_PASSWORD = os.environ.get("APP_USER_PASSWORD", "AppPass1")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "OraclePass1")

NODE_A_HOST = os.environ.get("NODE_A_HOST", "node_a")
NODE_B_HOST = os.environ.get("NODE_B_HOST", "node_b")
ORACLE_PORT = 1521
ORACLE_SERVICE = "FREEPDB1"

# EZConnect DSN strings used by python-oracledb in thin mode (no Instant Client required).
NODE_A_DSN = f"{NODE_A_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
NODE_B_DSN = f"{NODE_B_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"

# Container names must match those declared in docker-compose.yml.
# Scenario 3 uses these names to locate containers via the Docker SDK.
NODE_A_CONTAINER = os.environ.get("NODE_A_CONTAINER", "oracle_node_a")
NODE_B_CONTAINER = os.environ.get("NODE_B_CONTAINER", "oracle_node_b")

# The Docker bridge network name is derived from the Compose project name so
# that Scenario 3 can disconnect and reconnect Node B from the correct network.
COMPOSE_PROJECT_NAME = os.environ.get("COMPOSE_PROJECT_NAME", "oracle-2pc-simulator")
DOCKER_NETWORK_NAME = f"{COMPOSE_PROJECT_NAME}_oracle_net"

# Account balances inserted during database initialisation.
# Keys are account IDs; values are the initial balances in currency units.
SEED_NODE_A = {1: 10000.0, 2: 5000.0}
SEED_NODE_B = {1: 8000.0, 2: 3000.0}
