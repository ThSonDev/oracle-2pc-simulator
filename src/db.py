"""
Database access helpers for the Oracle 2PC Simulator.

All functions connect as app_user using python-oracledb in thin mode, which
requires no Oracle Instant Client installation.  Every public function accepts
or returns plain Python types (lists of dicts, floats, bools) so callers do
not need to import oracledb directly.
"""

import time
import oracledb
from src.config import (
    APP_USER, APP_USER_PASSWORD,
    NODE_A_DSN, NODE_B_DSN,
)


def get_connection(node: str = "node_a", autocommit: bool = False) -> oracledb.Connection:
    """
    Open and return a new python-oracledb thin-mode connection to the named node.

    Parameters
    ----------
    node:
        Either "node_a" or "node_b".  Any other value defaults to node_b DSN.
    autocommit:
        When True, each DML statement is committed immediately without an
        explicit conn.commit() call.  Required for COMMIT FORCE and
        ROLLBACK FORCE statements, which are DDL-like and must not be wrapped
        in a manual transaction.

    Returns
    -------
    An open oracledb.Connection.  The caller is responsible for closing it.
    """
    dsn = NODE_A_DSN if node == "node_a" else NODE_B_DSN
    conn = oracledb.connect(user=APP_USER, password=APP_USER_PASSWORD, dsn=dsn)
    conn.autocommit = autocommit
    return conn


def fetch_accounts(conn: oracledb.Connection) -> list[dict]:
    """
    Return all rows from the account table on the node the connection points to.

    Each row is returned as a dict with lowercase keys: id, name, balance.
    The results are ordered by account id for consistent display ordering.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, balance FROM account ORDER BY id")
        cols = [c[0].lower() for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_total_balance(conn: oracledb.Connection) -> float:
    """
    Return the sum of all account balances on the node the connection points to.

    Used by the consistency checks in Scenario 1 and the test suite to verify
    that the total amount of money across both nodes is conserved after a
    distributed transfer.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT SUM(balance) FROM account")
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0


def reset_balances(node: str, seed: dict[int, float]) -> None:
    """
    Restore account balances to their seed values on the named node.

    Opens a new connection, issues one UPDATE per account in a single
    transaction, and commits.  Used by the test fixture before and after
    each test to guarantee a known starting state regardless of what the
    previous test did to the data.

    Parameters
    ----------
    node:
        "node_a" or "node_b".
    seed:
        Mapping from account id to the desired balance (e.g., SEED_NODE_A).
    """
    conn = get_connection(node, autocommit=False)
    try:
        with conn.cursor() as cur:
            for acct_id, bal in seed.items():
                cur.execute(
                    "UPDATE account SET balance = :1 WHERE id = :2",
                    [bal, acct_id],
                )
        conn.commit()
    finally:
        conn.close()


def wait_for_db(node: str = "node_a", retries: int = 30, delay: float = 10.0) -> bool:
    """
    Poll the named Oracle node until a connection succeeds or retries are exhausted.

    Attempts a minimal round-trip (SELECT 1 FROM DUAL) on each try.  Used by
    the test session fixture to block test execution until both Oracle instances
    have finished their first-time initialisation, which can take 2-5 minutes
    for the gvenzl/oracle-free:23-slim-faststart image.

    Parameters
    ----------
    node:
        "node_a" or "node_b".
    retries:
        Maximum number of connection attempts before returning False.
    delay:
        Seconds to wait between attempts.

    Returns
    -------
    True if a connection was established within the allowed retries, False otherwise.
    """
    dsn = NODE_A_DSN if node == "node_a" else NODE_B_DSN
    for attempt in range(1, retries + 1):
        try:
            conn = oracledb.connect(user=APP_USER, password=APP_USER_PASSWORD, dsn=dsn)
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM DUAL")
            conn.close()
            return True
        except Exception:
            if attempt < retries:
                time.sleep(delay)
    return False


def fetch_pending_transactions(conn: oracledb.Connection) -> list[dict]:
    """
    Query DBA_2PC_PENDING on the node the connection points to and return all rows.

    DBA_2PC_PENDING records distributed transactions that have been prepared
    (Phase 1 of 2PC complete) but not yet fully committed or rolled back across
    all participants.  This view is relevant to Scenario 3, where a network
    interruption during Phase 2 leaves a transaction in-doubt on Node A.

    app_user requires SELECT ON SYS.DBA_2PC_PENDING for this query to succeed.
    This grant is applied by the SYSDBA session in scripts/00_grants_a.sh and
    scripts/00_grants_b.sh during container initialisation.

    Returns a list of dicts with lowercase keys corresponding to the selected
    columns: local_tran_id, global_tran_id, state, mixed, advice, tran_comment.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT local_tran_id, global_tran_id, state, mixed, advice, tran_comment "
            "FROM DBA_2PC_PENDING ORDER BY local_tran_id"
        )
        cols = [c[0].lower() for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
