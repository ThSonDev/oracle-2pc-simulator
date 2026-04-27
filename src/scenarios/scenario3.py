"""
Scenario 3: Network Failure and In-Doubt Transaction Recovery.

Simulates a mid-commit network failure during a distributed Oracle transaction
to produce an in-doubt state in DBA_2PC_PENDING, then demonstrates manual
recovery using COMMIT FORCE and ROLLBACK FORCE.

How the failure is produced:
  1. A connection to Node A opens a distributed transaction: one UPDATE on the
     local account table, one UPDATE on Node B through node_b_link.
  2. Just before conn.commit() is called, the Docker SDK is used to disconnect
     Node B's container from the shared oracle_net bridge network.
  3. Oracle attempts the 2PC sequence:
       - If Phase 1 (PREPARE) was not yet complete when the network dropped,
         Oracle cannot get PREPARE READY from Node B, times out (callTimeout),
         and rolls back cleanly.  DBA_2PC_PENDING remains empty.
       - If Phase 1 had already completed and Oracle had written its local
         COMMIT redo record before the network dropped, Phase 2 (COMMIT to
         Node B) stalls.  Oracle records the transaction as in-doubt in
         DBA_2PC_PENDING on Node A and the RECO background process will retry
         delivery when Node B becomes reachable again.
  4. Node B is reconnected.  If an in-doubt entry was created, the user can
     manually resolve it with COMMIT FORCE or ROLLBACK FORCE before RECO
     auto-resolves it.

Recovery privileges:
  app_user holds FORCE ANY TRANSACTION and SELECT ON SYS.DBA_2PC_PENDING,
  granted by the SYSDBA initialisation scripts.  No SYSTEM or SYSDBA
  connection is required for recovery operations.
"""

import docker
import oracledb
import streamlit as st
import pandas as pd

from src.config import NODE_B_CONTAINER, DOCKER_NETWORK_NAME
from src.db import get_connection, fetch_accounts, fetch_pending_transactions


def _disconnect_node_b(client: docker.DockerClient) -> None:
    """
    Remove Node B's container from the shared Docker bridge network.

    Uses force=True so the disconnect is immediate rather than graceful.
    Existing TCP connections from Node A to Node B will become unreachable:
    new packets are dropped at the bridge, while established socket state
    on Node A persists until Oracle's callTimeout triggers or the kernel
    detects the dead path.
    """
    container = client.containers.get(NODE_B_CONTAINER)
    network = client.networks.get(DOCKER_NETWORK_NAME)
    network.disconnect(container, force=True)


def _reconnect_node_b(client: docker.DockerClient) -> None:
    """
    Rejoin Node B's container to the shared Docker bridge network.

    Specifies both the container name and the "node_b" hostname alias so that
    Oracle on Node A can immediately resolve the node_b hostname after the
    reconnect.  The "already exists" API error is suppressed because it means
    the container was never fully disconnected, which is a harmless no-op.
    """
    container = client.containers.get(NODE_B_CONTAINER)
    network = client.networks.get(DOCKER_NETWORK_NAME)
    try:
        network.connect(container, aliases=[NODE_B_CONTAINER, "node_b"])
    except docker.errors.APIError as exc:
        if "already exists" in str(exc).lower():
            pass
        else:
            raise


def _simulate_failure(src_id: int, dst_id: int, amount: float, log: list) -> dict:
    """
    Execute a distributed transaction and disconnect Node B before the commit.

    Opens a connection to Node A, issues DML on both nodes via the DB link,
    disconnects Node B from the Docker network, then calls conn.commit().
    callTimeout is set to 30 seconds so that if Oracle cannot complete Phase 1
    (PREPARE READY from Node B never arrives), the commit fails with a clear
    error rather than hanging indefinitely.

    After the commit attempt (successful or not), Node B is immediately
    reconnected.  DBA_2PC_PENDING on Node A is queried to discover any
    in-doubt entries created by the failed commit.

    Parameters
    ----------
    src_id:
        Account id on Node A to debit.
    dst_id:
        Account id on Node B to credit.
    amount:
        Transfer amount.
    log:
        Mutable list to which step-by-step status strings are appended.
        The caller displays this list in the UI after the function returns.

    Returns
    -------
    A dict with keys:
      error: the error message string if the commit raised an exception, else None.
      pending: list of DBA_2PC_PENDING row dicts found after the commit attempt.
    """
    client = docker.from_env()
    conn = get_connection("node_a", autocommit=False)
    # callTimeout prevents indefinite hang when the network drop causes
    # Oracle's Phase 1 PREPARE to go unanswered.  The timeout is expressed
    # in milliseconds and applies to individual round-trip operations on the
    # connection, not to the total time of conn.commit().
    conn.callTimeout = 30000
    result = {"error": None, "pending": []}

    try:
        with conn.cursor() as cur:
            log.append("Starting distributed transaction on Node A...")
            cur.execute(
                "UPDATE account SET balance = balance - :1 WHERE id = :2",
                [amount, src_id],
            )
            log.append(f"  Node A: deducted {amount:.2f} from account id={src_id}.")

            cur.execute(
                "UPDATE account@node_b_link SET balance = balance + :1 WHERE id = :2",
                [amount, dst_id],
            )
            log.append(f"  Node B (via DB link): credited {amount:.2f} to account id={dst_id}.")

            log.append("Disconnecting Node B from Docker network to simulate crash...")
            _disconnect_node_b(client)
            log.append("  Node B is now unreachable.")

            log.append("Attempting COMMIT (Oracle will try 2PC PREPARE + COMMIT)...")
            try:
                conn.commit()
                log.append("  COMMIT completed (Oracle may have used a cached connection).")
            except oracledb.DatabaseError as exc:
                (error,) = exc.args
                log.append(f"  COMMIT FAILED: {error.message.strip()}")
                result["error"] = error.message.strip()
    except Exception as exc:
        result["error"] = str(exc)
        log.append(f"  Unexpected error: {exc}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

    log.append("Reconnecting Node B to Docker network...")
    try:
        _reconnect_node_b(client)
        log.append("  Node B reconnected.")
    except Exception as exc:
        log.append(f"  Reconnect warning: {exc}")

    # Query DBA_2PC_PENDING before RECO has a chance to auto-resolve any
    # in-doubt entry now that Node B is back on the network.
    log.append("Querying DBA_2PC_PENDING on Node A...")
    try:
        pending_conn = get_connection("node_a")
        result["pending"] = fetch_pending_transactions(pending_conn)
        pending_conn.close()
        log.append(f"  Found {len(result['pending'])} in-doubt transaction(s).")
    except Exception as exc:
        log.append(f"  Could not query DBA_2PC_PENDING: {exc}")

    return result


def _force_recover(local_tran_id: str, action: str, log: list) -> None:
    """
    Manually resolve an in-doubt transaction using COMMIT FORCE or ROLLBACK FORCE.

    app_user holds FORCE ANY TRANSACTION, which allows issuing these statements
    without SYSDBA access.

    COMMIT FORCE applies the coordinator's committed decision to Node A's local
    transaction record, effectively completing Phase 2 on the coordinator side.
    Oracle's RECO process will propagate the resolution to Node B when it
    becomes reachable.

    ROLLBACK FORCE undoes the prepared transaction on Node A.  The Node B side
    was never committed, so no further action is required there.

    Parameters
    ----------
    local_tran_id:
        The LOCAL_TRAN_ID value from DBA_2PC_PENDING identifying the in-doubt
        transaction.  This is the Oracle-assigned identifier for the transaction
        on the coordinator (Node A) side.
    action:
        Either "commit" or "rollback".
    log:
        Mutable list to which the outcome message is appended.
    """
    conn = get_connection("node_a", autocommit=True)
    try:
        with conn.cursor() as cur:
            if action == "commit":
                cur.execute(f"COMMIT FORCE '{local_tran_id}'")
                log.append(f"COMMIT FORCE '{local_tran_id}' succeeded.")
            else:
                cur.execute(f"ROLLBACK FORCE '{local_tran_id}'")
                log.append(f"ROLLBACK FORCE '{local_tran_id}' succeeded.")
    except oracledb.DatabaseError as exc:
        (error,) = exc.args
        log.append(f"Force recover error: {error.message.strip()}")
    finally:
        conn.close()


def render() -> None:
    """Render the Scenario 3 page in the Streamlit application."""
    st.header("Scenario 3: Network Failure / In-Doubt Transaction")
    st.write(
        "This scenario starts a distributed transaction and then severs Node B's "
        "network connection just before the commit phase.  Oracle cannot complete "
        "2PC and the transaction is recorded in DBA_2PC_PENDING as in-doubt.  "
        "You can then manually force a commit or rollback."
    )

    if "s3_log" not in st.session_state:
        st.session_state.s3_log = []
    if "s3_pending" not in st.session_state:
        st.session_state.s3_pending = []
    if "s3_recovery_log" not in st.session_state:
        st.session_state.s3_recovery_log = []

    conn_a = get_connection("node_a")
    conn_b = get_connection("node_b")
    accounts_a = fetch_accounts(conn_a)
    accounts_b = fetch_accounts(conn_b)
    conn_a.close()
    conn_b.close()

    a_opts = {f"[A] {r['name']} (id={r['id']}, balance={r['balance']:.2f})": r["id"] for r in accounts_a}
    b_opts = {f"[B] {r['name']} (id={r['id']}, balance={r['balance']:.2f})": r["id"] for r in accounts_b}

    col1, col2 = st.columns(2)
    with col1:
        src_label = st.selectbox("Debit account (Node A)", list(a_opts.keys()), key="s3_src")
        src_id = a_opts[src_label]
    with col2:
        dst_label = st.selectbox("Credit account (Node B)", list(b_opts.keys()), key="s3_dst")
        dst_id = b_opts[dst_label]

    amount = st.number_input("Transfer amount", min_value=1.0, max_value=50000.0, value=200.0, step=50.0, key="s3_amount")

    if st.button("Simulate Network Failure During Commit", type="primary"):
        st.session_state.s3_log = []
        st.session_state.s3_pending = []
        st.session_state.s3_recovery_log = []
        with st.spinner("Simulating network failure..."):
            result = _simulate_failure(src_id, dst_id, amount, st.session_state.s3_log)
            st.session_state.s3_pending = result.get("pending", [])
        st.rerun()

    if st.session_state.s3_log:
        st.subheader("Execution Log")
        for line in st.session_state.s3_log:
            st.text(line)

    if st.session_state.s3_pending:
        st.subheader("DBA_2PC_PENDING - In-Doubt Transactions")
        df = pd.DataFrame(st.session_state.s3_pending)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("Manual Recovery")
        tran_ids = [r["local_tran_id"] for r in st.session_state.s3_pending]
        selected_tran = st.selectbox("Select transaction to resolve", tran_ids, key="s3_tran_sel")

        col_commit, col_rollback = st.columns(2)
        with col_commit:
            if st.button("Force Commit", key="s3_force_commit"):
                _force_recover(selected_tran, "commit", st.session_state.s3_recovery_log)
                st.rerun()
        with col_rollback:
            if st.button("Force Rollback", key="s3_force_rollback"):
                _force_recover(selected_tran, "rollback", st.session_state.s3_recovery_log)
                st.rerun()

        if st.session_state.s3_recovery_log:
            for line in st.session_state.s3_recovery_log:
                st.write(line)

    if st.button("Refresh DBA_2PC_PENDING", key="s3_refresh"):
        try:
            pending_conn = get_connection("node_a")
            st.session_state.s3_pending = fetch_pending_transactions(pending_conn)
            pending_conn.close()
        except Exception as exc:
            st.error(str(exc))
        st.rerun()

    st.divider()
    st.subheader("Current Balances")
    col_a, col_b = st.columns(2)
    try:
        c_a = get_connection("node_a")
        with col_a:
            st.write("Node A")
            st.dataframe(pd.DataFrame(fetch_accounts(c_a)), use_container_width=True, hide_index=True)
        c_a.close()
    except Exception as exc:
        col_a.error(f"Node A unreachable: {exc}")
    try:
        c_b = get_connection("node_b")
        with col_b:
            st.write("Node B")
            st.dataframe(pd.DataFrame(fetch_accounts(c_b)), use_container_width=True, hide_index=True)
        c_b.close()
    except Exception as exc:
        col_b.error(f"Node B unreachable: {exc}")
