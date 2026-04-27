# Oracle 2PC Distributed Transaction Simulator

An interactive, Docker-based simulator that demonstrates Oracle's Two-Phase Commit
(2PC) protocol, row-level locking, and in-doubt transaction recovery.  The project
runs two Oracle Free 23c instances connected by a private database link and exposes
a Streamlit web application with three guided scenarios.

## Project Overview

Oracle's Two-Phase Commit protocol guarantees atomicity for transactions that span
multiple database instances.  When a transaction modifies data on more than one node,
the coordinator executes a two-phase sequence before reporting success to the client:

- Phase 1 (PREPARE): the coordinator asks every participant to write a prepare record
  to its redo log and respond READY.  Once all participants have responded, the outcome
  is decided and durable on the coordinator.
- Phase 2 (COMMIT): the coordinator writes its own commit record, then sends COMMIT to
  each participant and waits for COMMITTED acknowledgements.

This simulator lets you observe each phase, trigger a network failure between phases to
produce an in-doubt state, and issue manual recovery commands (COMMIT FORCE, ROLLBACK
FORCE) as a DBA would in a real incident.

## Project Structure

```
oracle-2pc-simulator/
├── .env                          Environment variable defaults for Docker Compose
├── docker-compose.yml            Three-service stack: node_a, node_b, streamlit
├── Dockerfile                    Python 3.11-slim image for the Streamlit application
├── requirements.txt              Python dependencies: streamlit, oracledb, docker, pandas, pytest
├── scripts/
│   ├── 00_grants_a.sh            Node A init: SYSDBA grants, account table, seed data, DB link
│   └── 00_grants_b.sh            Node B init: SYSDBA grants, account table, seed data
└── src/
    ├── app.py                    Streamlit entry point; sidebar navigation to all four pages
    ├── config.py                 Connection constants and seed balance values (env-configurable)
    ├── db.py                     Connection factory, query helpers, test reset utility
    ├── scenarios/
    │   ├── __init__.py
    │   ├── scenario1.py          Successful distributed 2PC transfer via DB link
    │   ├── scenario2.py          Row-level locking and competing UPDATE demonstration
    │   └── scenario3.py          Network failure simulation and in-doubt recovery
    └── tests/
        ├── __init__.py
        └── test_scenarios.py     pytest suite covering all three scenarios
```

## Prerequisites

- Docker Engine 24.0 or later
- Docker Compose 2.20 or later (included in Docker Desktop or installable as a plugin)
- At least 8 GB of free RAM (Oracle Free 23c uses approximately 2 GB per instance; the
  application container adds around 200 MB)
- 16 GB total system RAM is recommended for comfortable headroom alongside the host OS
- Linux host or Docker Desktop on macOS or Windows

## Architecture

```
oracle_node_a  (Global Coordinator)          oracle_node_b  (Local Site)
Oracle Free 23c                              Oracle Free 23c
host port 1521                               host port 1522
     |                                             |
     |  node_b_link (private DB link)              |
     +---------------------------------------------+
                   oracle_net (bridge)
                         |
                  streamlit_app
                  Python 3.11
                  host port 8501
                  /var/run/docker.sock
```

Node A is the global coordinator.  It holds the private database link `node_b_link`
that routes remote DML to Node B.  When `conn.commit()` is called on a connection to
Node A that has touched Node B via the link, Oracle runs the full 2PC protocol
automatically between the two database server processes, invisible to the Python client.

The Streamlit container has access to the Docker socket so that Scenario 3 can
disconnect and reconnect Node B's network interface via the Docker SDK, simulating a
mid-commit network failure without requiring any external network configuration tools.

### Initialisation design

All schema setup (table creation, seed data, grants, DB link) is performed by two
shell scripts placed in `/docker-entrypoint-initdb.d/` inside each Oracle container.
The gvenzl/oracle-free image executes these scripts in lexicographic order on the first
start (empty data volume).  There is no separate setup container.

Node A requires two sqlplus sessions in `00_grants_a.sh`:
- Session 1 connects as SYSDBA and issues GRANT statements, creates the account table,
  and inserts seed data using `ALTER SESSION SET CURRENT_SCHEMA` to place objects in
  app_user's schema.
- Session 2 connects as app_user and creates the private database link.  Oracle 23c
  Free disallows `CREATE PUBLIC DATABASE LINK` within a PDB even for SYS/SYSDBA
  (ORA-01031), so the link must be created by the owning user.

Node B requires only one SYSDBA session in `00_grants_b.sh` because no database link
is needed on the participant side.

All operational Python code (scenarios, tests) connects only as app_user.  No SYSTEM
or SYSDBA credentials are used at runtime.

## Quick Start

### First-time setup

```bash
git clone <repo_url> oracle-2pc-simulator
cd oracle-2pc-simulator
docker compose up -d
```

Oracle Free 23c uses the `faststart` image variant which includes a pre-built DBCA
template and typically initialises in 2-3 minutes on hardware with fast storage.
Watch the initialisation progress:

```bash
docker compose logs -f node_a node_b
```

Wait until both nodes print:

```
DATABASE IS READY TO USE!
```

followed by the init script completion message:

```
oracle_node_a  | Node A init complete.
oracle_node_b  | Node B init complete.
```

Check that all three services are running and healthy:

```bash
docker compose ps
```

Expected output:

```
NAME             IMAGE                                STATUS
oracle_node_a    gvenzl/oracle-free:23-slim-faststart Up (healthy)
oracle_node_b    gvenzl/oracle-free:23-slim-faststart Up (healthy)
streamlit_app    oracle-2pc-simulator-streamlit        Up
```

### Subsequent starts (data volumes already exist)

```bash
docker compose up -d
```

The init scripts do not re-run when the data volumes are populated.

### Clean reset (wipes all Oracle data)

```bash
docker compose down -v
docker compose up -d
```

The `-v` flag removes named volumes, forcing Oracle to reinitialise from scratch on
the next start.

### Verify the database link

Confirm that the DB link from Node A to Node B is operational:

```bash
docker exec oracle_node_a \
  sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< "SELECT COUNT(*) AS node_b_rows FROM account@node_b_link;"
```

Expected output:

```
NODE_B_ROWS
-----------
          2
```

## Access the GUI

Open a browser and navigate to:

```
http://localhost:8501
```

The sidebar contains four pages:

- **Cluster Health**: connectivity status, current balances, and DB link check.
- **Scenario 1**: Successful 2PC Transfer.
- **Scenario 2**: Concurrency Conflict.
- **Scenario 3**: Network Failure / In-Doubt.

## Scenario Walkthroughs

### Cluster Health

Navigate to Cluster Health in the sidebar.  The page displays the live account tables
for Node A and Node B and performs a SELECT via the database link to confirm it is
working.  All accounts should be visible and the link status should read as working.

### Scenario 1: Successful 2PC Transfer

Demonstrates Oracle's automatic Two-Phase Commit.

1. Navigate to "Scenario 1: Successful 2PC Transfer".
2. Select a debit account on Node A (for example, Alice, id=1, balance=10000.00).
3. Select a credit account on Node B (for example, Bob, id=1, balance=8000.00).
4. Enter a transfer amount, for example 500.
5. Click "Execute Transfer".

What happens internally:

- The application acquires a `SELECT ... FOR UPDATE` lock on the source row, validates
  the balance, then issues a local `UPDATE` on Node A and a remote `UPDATE` via
  `node_b_link` on Node B.
- `conn.commit()` triggers Oracle's 2PC: PREPARE is sent to both nodes, READY is
  received from both, COMMIT is written on the coordinator, then COMMIT is sent to both
  participants.
- The result page shows the 2PC Phase Summary, per-node balance changes, and a global
  consistency check confirming that the sum across both nodes is unchanged.

Expected outcome: Node A balance decreases by the transfer amount; Node B balance
increases by the same amount; the global sum check shows "YES".

### Scenario 2: Concurrency Conflict

Demonstrates row-level locking and read isolation.

1. Navigate to "Scenario 2: Concurrency Conflict".
2. Select an account to lock (for example, Alice, id=1).
3. Set the lock hold duration, for example 20 seconds.
4. Click "Acquire Lock (background)".  The lock status log confirms acquisition.
5. While the lock is active, click "Attempt Competing Update".
   The spinner indicates that the UPDATE is blocked inside Oracle.
6. To observe the blocking session from a separate terminal:

```bash
docker exec oracle_node_a \
  sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< "SELECT sid, state, seconds_in_wait FROM v\$session WHERE wait_class = 'Application';"
```

7. Click "Release Lock" to roll back the holding transaction.

Expected outcome: the competing UPDATE status changes from blocked to "succeeded after
Xs", where X is the time the lock was held.  The balance shows the +1.00 increment
applied by the competing UPDATE.

Oracle's READ COMMITTED isolation (the default) ensures that a concurrent reader sees
only the last committed balance, not the uncommitted change held by the lock holder.
This is also demonstrated by the `test_lock_prevents_concurrent_read_write_isolation`
test in the automated suite.

### Scenario 3: Network Failure and In-Doubt Transaction Recovery

Demonstrates what happens when Node B becomes unreachable during the 2PC commit phase.

**Note on expected behaviour**: The 2PC window between Phase 1 completion and Phase 2
delivery is sub-millisecond in a single-host Docker environment.  The network disconnect
may arrive before Phase 1 completes, in which case Oracle rolls back cleanly
(callTimeout fires) and DBA_2PC_PENDING remains empty.  Run the simulation several
times; eventually the disconnect arrives at a point where Oracle has already committed
locally but cannot deliver COMMIT to Node B, producing an in-doubt entry.

Steps:

1. Navigate to "Scenario 3: Network Failure / In-Doubt".
2. Select a debit account on Node A and a credit account on Node B.
3. Enter a small transfer amount, for example 200.
4. Click "Simulate Network Failure During Commit".

What happens internally:

- The application runs a distributed transaction (local UPDATE on Node A, remote UPDATE
  on Node B via DB link), then disconnects Node B from the Docker bridge network using
  the Docker SDK just before calling `conn.commit()`.
- Oracle attempts 2PC.  If Phase 1 (PREPARE READY from Node B) completes before the
  network drops and Oracle writes its commit redo record, the transaction becomes
  in-doubt: it is committed on the coordinator but unconfirmed on the participant.
- Node B is immediately reconnected after the commit attempt.
- DBA_2PC_PENDING on Node A is queried to surface any in-doubt entries.

If an in-doubt transaction appears:

5. The DBA_2PC_PENDING table is displayed with the `local_tran_id` and state.
6. Select the transaction from the dropdown.
7. Click "Force Commit" to apply the coordinator's committed decision, or "Force
   Rollback" to undo the transaction on Node A (Node B was never committed, so no
   further action is required there).
8. Click "Refresh DBA_2PC_PENDING" to confirm the entry has been removed.

If the table is empty after the simulation:

- Oracle rolled back cleanly before writing the commit redo record.
- Click the button again; the timing outcome varies between runs.

Recovery privilege notes: app_user holds `FORCE ANY TRANSACTION` (granted in
`scripts/00_grants_a.sh`) which allows COMMIT FORCE and ROLLBACK FORCE without
requiring a SYSDBA or SYSTEM connection.

## Testing

The test suite verifies the behaviour demonstrated by all three scenarios.  Run it
inside the streamlit_app container, which already has both Oracle nodes as reachable
hostnames:

```bash
docker exec streamlit_app python -m pytest src/tests/ -v
```

Expected output (4.1 seconds):

```
PASSED src/tests/test_scenarios.py::TestScenario1::test_transfer_updates_both_nodes
PASSED src/tests/test_scenarios.py::TestScenario1::test_global_sum_is_constant
PASSED src/tests/test_scenarios.py::TestScenario1::test_insufficient_balance_raises
PASSED src/tests/test_scenarios.py::TestScenario1::test_multiple_sequential_transfers
PASSED src/tests/test_scenarios.py::TestScenario2::test_blocking_update_succeeds_after_lock_release
PASSED src/tests/test_scenarios.py::TestScenario2::test_lock_prevents_concurrent_read_write_isolation
PASSED src/tests/test_scenarios.py::TestScenario3::test_dba_2pc_pending_view_accessible
PASSED src/tests/test_scenarios.py::TestScenario3::test_commit_force_privilege_granted
PASSED src/tests/test_scenarios.py::TestScenario3::test_rollback_force_privilege_granted
9 passed
```

Scenario 3 tests verify access control rather than full in-doubt transaction creation.
Oracle's dedicated-server mode makes all DB links non-migratable in XA/TPC context
(ORA-24777), and local-only TPC transactions are rejected with ORA-24771.  The tests
therefore confirm that `app_user` holds `SELECT ON SYS.DBA_2PC_PENDING` and
`FORCE ANY TRANSACTION`, which are the two privileges the Scenario 3 recovery UI
depends on.  The full in-doubt creation and resolution cycle is exercised through the
Streamlit UI.

## Troubleshooting

**Oracle takes longer than 5 minutes to initialise**

Check available memory and disk I/O:

```bash
free -h
docker stats --no-stream
```

The slim-faststart image pre-builds the database, so startup should complete in 2-3
minutes on hardware with 8 GB free RAM and an SSD.  On slower hardware or under heavy
load, increase the `start_period` value in the healthcheck section of `docker-compose.yml`.

**Init script failed (Node A or Node B logs show exit code 7)**

Exit code 7 is Oracle error code 1031 (ORA-01031: insufficient privileges) modulo 256.
This typically occurs when the init script runs against a CDB root session rather than
the FREEPDB1 PDB.  Verify that the SYSDBA connection string explicitly targets
`//localhost:1521/FREEPDB1`.  Wipe volumes and restart:

```bash
docker compose down -v
docker compose up -d
```

**DB link check returns ORA-12541 or ORA-12154**

These errors indicate that Node A cannot resolve the `node_b` hostname over the Docker
bridge.  Confirm both containers are on the same network:

```bash
docker network inspect oracle-2pc-simulator_oracle_net
```

Both `oracle_node_a` and `oracle_node_b` should appear in the `Containers` section.
If either is missing, bring the stack down and back up:

```bash
docker compose down
docker compose up -d
```

**DBA_2PC_PENDING is always empty in Scenario 3**

The 2PC commit and network disconnect race against each other.  If the network drops
before Phase 1 completes (PREPARE READY received from Node B), Oracle rolls back
cleanly and creates no DBA_2PC_PENDING entry.  Re-run the simulation; the timing
outcome varies.  If it never produces an in-doubt entry after many attempts, check
whether the Docker SDK is successfully disconnecting Node B:

```bash
docker network inspect oracle-2pc-simulator_oracle_net
```

If `oracle_node_b` is still listed after clicking the button, the disconnect is not
taking effect.  Confirm the streamlit container is running as root and the Docker
socket is mounted:

```bash
docker inspect streamlit_app | grep -A2 '"User"'
docker inspect streamlit_app | grep docker.sock
```

**Docker socket permission error in Scenario 3**

The streamlit service is configured with `user: root` in `docker-compose.yml` to ensure
it can read `/var/run/docker.sock`.  If permission errors persist, verify the socket
ownership on the host:

```bash
ls -la /var/run/docker.sock
```

On Linux the socket is typically owned by `root:docker`.  Running the container as root
bypasses the group membership requirement.

**Streamlit shows "ModuleNotFoundError: No module named 'src'"**

The working directory inside the container is `/app` and the source tree is bind-mounted
as `/app/src`.  Streamlit is launched with `streamlit run src/app.py` from `/app`, so
the `src` package is importable by design.  If running tests from the host machine
directly (not via docker exec), set `PYTHONPATH` first:

```bash
cd oracle-2pc-simulator
PYTHONPATH=. python -m pytest src/tests/ -v
```

**Previous test run left in-doubt transactions**

If `reset_balances` fails with ORA-01591 ("transaction branch was already committed"),
a previous test left an unresolved in-doubt transaction that holds row locks.  The
`reset_seed_data` fixture calls `_force_recover_all_pending()` to handle this
automatically.  If the issue persists outside the test suite, resolve manually:

```bash
docker exec oracle_node_a \
  sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< "SELECT local_tran_id FROM dba_2pc_pending;"
```

Then for each returned ID:

```bash
docker exec oracle_node_a \
  sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< "ROLLBACK FORCE '<local_tran_id>';"
```
