"""
Automated tests for all three 2PC simulator scenarios.

Each test class maps to one UI scenario and validates the underlying Oracle
behaviour that the Streamlit GUI demonstrates.  Tests are designed to be run
inside the streamlit_app container where both Oracle nodes are reachable by
their service hostnames:

    docker exec streamlit_app python -m pytest src/tests/ -v

The session-scoped fixture verify_connectivity blocks until both nodes accept
connections.  The function-scoped fixture reset_seed_data restores account
balances to seed values before and after every test so tests do not depend on
execution order.
"""

import threading
import time

import oracledb
import pytest

from src.config import SEED_NODE_A, SEED_NODE_B
from src.db import (
    get_connection,
    fetch_accounts, get_total_balance,
    reset_balances, fetch_pending_transactions, wait_for_db,
)


# -- fixtures -----------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def verify_connectivity():
    """
    Assert that both Oracle nodes are reachable before the test session runs.

    Uses a short retry budget (5 attempts, 5 s apart) because this fixture
    runs after Docker Compose health checks have already passed; the nodes
    should be ready within one or two retries at most.
    """
    assert wait_for_db("node_a", retries=5, delay=5.0), "Node A is not reachable."
    assert wait_for_db("node_b", retries=5, delay=5.0), "Node B is not reachable."


def _force_recover_all_pending() -> None:
    """
    Resolve every in-doubt transaction in DBA_2PC_PENDING on Node A.

    In-doubt transactions hold row-level locks.  If a previous test left an
    unresolved prepared transaction, the reset_balances UPDATE would block with
    ORA-01591.  This function issues ROLLBACK FORCE for each pending entry (with
    COMMIT FORCE as a fallback) so the fixture can safely reset account rows.

    Silently returns if the query fails (e.g., Node A is momentarily offline).
    """
    try:
        conn = get_connection("node_a")
        pending = fetch_pending_transactions(conn)
        conn.close()
    except Exception:
        return
    if not pending:
        return
    recover_conn = get_connection("node_a", autocommit=True)
    for row in pending:
        tran_id = row["local_tran_id"]
        try:
            with recover_conn.cursor() as cur:
                cur.execute(f"ROLLBACK FORCE '{tran_id}'")
        except oracledb.DatabaseError:
            # If ROLLBACK FORCE fails (e.g., the transaction was already
            # committed on Node B and RECO auto-resolved it as committed),
            # try COMMIT FORCE to match the coordinator's decision.
            try:
                with recover_conn.cursor() as cur:
                    cur.execute(f"COMMIT FORCE '{tran_id}'")
            except oracledb.DatabaseError:
                pass
    recover_conn.close()


@pytest.fixture(autouse=True)
def reset_seed_data():
    """
    Restore both nodes to their seed balances before and after each test.

    The setup phase (_force_recover_all_pending + reset_balances) runs first
    to guarantee a clean starting state.  The teardown phase (after yield)
    runs the same cleanup regardless of whether the test passed or failed,
    so subsequent tests always start from a known baseline.
    """
    _force_recover_all_pending()
    reset_balances("node_a", SEED_NODE_A)
    reset_balances("node_b", SEED_NODE_B)
    yield
    _force_recover_all_pending()
    reset_balances("node_a", SEED_NODE_A)
    reset_balances("node_b", SEED_NODE_B)


# -- helpers ------------------------------------------------------------------

def _total_across_both() -> float:
    """Return the combined sum of all account balances on Node A and Node B."""
    c_a = get_connection("node_a")
    c_b = get_connection("node_b")
    total = get_total_balance(c_a) + get_total_balance(c_b)
    c_a.close()
    c_b.close()
    return total


def _transfer_2pc(src_id: int, dst_id: int, amount: float) -> None:
    """
    Execute a distributed 2PC transfer from Node A account src_id to Node B account dst_id.

    Issues a local UPDATE on Node A and a remote UPDATE via node_b_link, then
    calls conn.commit() which triggers Oracle's automatic Two-Phase Commit.
    The connection is always closed in the finally block.
    """
    conn = get_connection("node_a", autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE account SET balance = balance - :1 WHERE id = :2",
                [amount, src_id],
            )
            cur.execute(
                "UPDATE account@node_b_link SET balance = balance + :1 WHERE id = :2",
                [amount, dst_id],
            )
        conn.commit()
    finally:
        conn.close()


# -- Scenario 1 ---------------------------------------------------------------

class TestScenario1:
    """Verify that Oracle's automatic 2PC correctly transfers funds across both nodes."""

    def test_transfer_updates_both_nodes(self):
        """The debit and credit are both applied and visible after commit."""
        amount = 500.0
        total_before = _total_across_both()

        _transfer_2pc(src_id=1, dst_id=1, amount=amount)

        c_a = get_connection("node_a")
        c_b = get_connection("node_b")
        rows_a = {r["id"]: r["balance"] for r in fetch_accounts(c_a)}
        rows_b = {r["id"]: r["balance"] for r in fetch_accounts(c_b)}
        c_a.close()
        c_b.close()

        assert rows_a[1] == SEED_NODE_A[1] - amount, "Node A balance should decrease."
        assert rows_b[1] == SEED_NODE_B[1] + amount, "Node B balance should increase."

    def test_global_sum_is_constant(self):
        """The total balance across both nodes is conserved after a distributed transfer."""
        total_before = _total_across_both()
        _transfer_2pc(src_id=1, dst_id=1, amount=1000.0)
        total_after = _total_across_both()
        assert abs(total_before - total_after) < 0.01, "Global balance must be conserved."

    def test_insufficient_balance_raises(self):
        """A transfer that would produce a negative balance is rejected by the CHECK constraint."""
        with pytest.raises(Exception):
            _transfer_2pc(src_id=1, dst_id=1, amount=999999.0)

    def test_multiple_sequential_transfers(self):
        """Three consecutive transfers keep the global sum unchanged."""
        total_before = _total_across_both()
        for _ in range(3):
            _transfer_2pc(src_id=1, dst_id=1, amount=100.0)
        total_after = _total_across_both()
        assert abs(total_before - total_after) < 0.01


# -- Scenario 2 ---------------------------------------------------------------

class TestScenario2:
    """Verify Oracle's row-level locking and read isolation behaviour on Node A."""

    def test_blocking_update_succeeds_after_lock_release(self):
        """
        A competing UPDATE blocks until the row lock is released, then succeeds.

        A background thread acquires a FOR UPDATE lock and holds it.  A second
        thread issues a plain UPDATE on the same row; that UPDATE blocks inside
        Oracle until the first thread rolls back.  The test asserts that the
        competing UPDATE eventually succeeds rather than failing permanently.
        """
        release_event = threading.Event()
        lock_status = []
        hold_seconds = 5

        def lock_holder():
            conn = get_connection("node_a", autocommit=False)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM account WHERE id = 1 FOR UPDATE")
                    lock_status.append("locked")
                    release_event.wait(timeout=hold_seconds)
                conn.rollback()
                lock_status.append("released")
            finally:
                conn.close()

        t = threading.Thread(target=lock_holder, daemon=True)
        t.start()

        deadline = time.time() + 5.0
        while "locked" not in lock_status and time.time() < deadline:
            time.sleep(0.1)
        assert "locked" in lock_status, "Background thread should have acquired the lock."

        def competing():
            conn = get_connection("node_a", autocommit=False)
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE account SET balance = balance + 1 WHERE id = 1")
                conn.commit()
                lock_status.append("competing_success")
            except Exception as exc:
                lock_status.append(f"competing_error:{exc}")
            finally:
                conn.close()

        ct = threading.Thread(target=competing, daemon=True)
        ct.start()

        time.sleep(1.5)
        release_event.set()

        ct.join(timeout=15)
        t.join(timeout=5)

        assert "competing_success" in lock_status, "Competing update should succeed after lock is released."

    def test_lock_prevents_concurrent_read_write_isolation(self):
        """
        A reader sees the last committed value, not an uncommitted change held by another session.

        Oracle's default isolation level (READ COMMITTED) guarantees that a SELECT
        without FOR UPDATE returns the most recently committed row value, even when
        another session holds a lock and has applied an uncommitted UPDATE to the
        same row.
        """
        release_event = threading.Event()
        committed_balance = []

        def holder():
            conn = get_connection("node_a", autocommit=False)
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM account WHERE id = 1 FOR UPDATE")
                # Apply an uncommitted change to verify that the reader below
                # does not see this value before it is committed.
                cur.execute("UPDATE account SET balance = balance + 9999 WHERE id = 1")
                release_event.wait(timeout=10)
                conn.rollback()
            conn.close()

        t = threading.Thread(target=holder, daemon=True)
        t.start()
        time.sleep(0.5)

        c = get_connection("node_a")
        with c.cursor() as cur:
            cur.execute("SELECT balance FROM account WHERE id = 1")
            committed_balance.append(float(cur.fetchone()[0]))
        c.close()

        release_event.set()
        t.join(timeout=5)

        assert committed_balance[0] == SEED_NODE_A[1], (
            f"Reader should see committed value {SEED_NODE_A[1]}, got {committed_balance[0]}."
        )


# -- Scenario 3 ---------------------------------------------------------------

class TestScenario3:
    """
    Verify that app_user has the privileges required for Scenario 3 recovery.

    Oracle's native 2PC via DB links operates through dedicated-server sessions.
    In dedicated-server mode all DB links are non-migratable in XA/TPC context,
    which causes ORA-24777 when tpc_prepare is called on a transaction that
    touched a DB link.  Transactions with only local DML are rejected with
    ORA-24771 ("cannot prepare a local transaction").  There is therefore no
    Python path to synthetically produce a DBA_2PC_PENDING entry without
    kernel-level network manipulation tools (tc, iptables) that are absent from
    the Oracle container images.

    These tests instead validate the two access controls that the Scenario 3
    recovery UI depends on:
      1. SELECT on SYS.DBA_2PC_PENDING:  in-doubt transactions are visible to app_user.
      2. FORCE ANY TRANSACTION:           COMMIT FORCE and ROLLBACK FORCE are executable.

    If either grant is absent the Streamlit UI would fail at runtime.  These
    tests serve as a fast pre-flight check of the SYSDBA initialisation scripts.
    """

    def test_dba_2pc_pending_view_accessible(self):
        """DBA_2PC_PENDING can be queried without error, confirming the SELECT grant."""
        conn = get_connection("node_a")
        try:
            pending = fetch_pending_transactions(conn)
        finally:
            conn.close()
        assert isinstance(pending, list), (
            "fetch_pending_transactions should return a list; "
            "check SELECT on SYS.DBA_2PC_PENDING grant for app_user."
        )

    def test_commit_force_privilege_granted(self):
        """
        COMMIT FORCE does not raise ORA-01031, confirming FORCE ANY TRANSACTION grant.

        The statement is issued against a non-existent transaction ID.  Oracle
        may return a different error (e.g., ORA-02058 "no prepared transaction found")
        or silently succeed depending on version.  The only outcome that indicates
        a missing privilege is ORA-01031.
        """
        conn = get_connection("node_a", autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("COMMIT FORCE 'nonexistent.tran.id.0'")
        except oracledb.DatabaseError as exc:
            (error,) = exc.args
            assert error.code != 1031, (
                "COMMIT FORCE raised ORA-01031 (insufficient privileges); "
                "check FORCE ANY TRANSACTION grant for app_user."
            )
        finally:
            conn.close()

    def test_rollback_force_privilege_granted(self):
        """
        ROLLBACK FORCE does not raise ORA-01031, confirming FORCE ANY TRANSACTION grant.

        See test_commit_force_privilege_granted for the reasoning behind using
        a non-existent transaction ID.
        """
        conn = get_connection("node_a", autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute("ROLLBACK FORCE 'nonexistent.tran.id.0'")
        except oracledb.DatabaseError as exc:
            (error,) = exc.args
            assert error.code != 1031, (
                "ROLLBACK FORCE raised ORA-01031 (insufficient privileges); "
                "check FORCE ANY TRANSACTION grant for app_user."
            )
        finally:
            conn.close()
