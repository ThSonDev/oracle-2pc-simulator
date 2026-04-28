"""
Scenario 1: Successful Distributed 2PC Transfer.

Demonstrates Oracle's automatic Two-Phase Commit (2PC) protocol over a
private database link.  When conn.commit() is called on Node A while the
open transaction contains a remote UPDATE via node_b_link, Oracle
transparently runs the full 2PC sequence:

  Phase 1 (PREPARE):
    Node A sends a PREPARE message to Node B via the DB link TCP session.
    Node B writes a prepare record to its redo log and responds READY.
    Node A receives READY from all participants and writes a COMMIT redo
    record, making the decision durable on the coordinator side.

  Phase 2 (COMMIT):
    Node A sends COMMIT to Node B.
    Node B applies the change, writes a commit record, and responds COMMITTED.
    Node A removes the transaction from DBA_2PC_PENDING and returns success
    to the client.

The global sum of all balances across both nodes must be identical before
and after the transfer, which is verified in the consistency check panel.
"""

import streamlit as st
import pandas as pd
from src.db import get_connection, fetch_accounts, get_total_balance
from src.strings import T


def _do_transfer(src_id: int, dst_id: int, amount: float) -> dict:
    """
    Execute a distributed debit/credit transfer and return balance snapshots.

    Opens a single connection to Node A with autocommit disabled.  Issues a
    SELECT ... FOR UPDATE to lock the source row and validate the available
    balance before proceeding.  The remote credit on Node B is issued through
    the node_b_link database link, making this a distributed transaction that
    Oracle will commit via 2PC.

    On success, reads the post-commit balances from both nodes and returns
    them together with the pre-transfer Node A snapshot and the global totals
    so the caller can display the before/after delta and consistency check.

    On any error the transaction is rolled back before re-raising.

    Parameters
    ----------
    src_id:
        Account id on Node A to debit.
    dst_id:
        Account id on Node B to credit.
    amount:
        Transfer amount; must not exceed the current balance of src_id.

    Returns
    -------
    A dict with keys: before_a, after_a, after_b, total_before, total_after, amount.

    Raises
    ------
    ValueError:
        If src_id does not exist or has insufficient balance.
    oracledb.DatabaseError:
        On any Oracle-level error (constraint violation, link failure, etc.).
    """
    conn = get_connection("node_a", autocommit=False)
    try:
        with conn.cursor() as cur:
            before_a = fetch_accounts(conn)
            total_before = get_total_balance(conn)

            # Lock the source row to prevent a concurrent transfer from
            # overdrawing the account between the balance check and the UPDATE.
            cur.execute(
                "SELECT balance FROM account WHERE id = :1 FOR UPDATE",
                [src_id],
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"Account {src_id} not found on Node A.")
            src_balance = float(row[0])
            if src_balance < amount:
                raise ValueError(
                    f"Insufficient balance: account {src_id} has {src_balance:.2f}, "
                    f"requested {amount:.2f}."
                )

            # Debit Node A (local UPDATE).
            cur.execute(
                "UPDATE account SET balance = balance - :1 WHERE id = :2",
                [amount, src_id],
            )
            # Credit Node B through the database link (remote UPDATE).
            # This opens a distributed transaction: Oracle must now use 2PC
            # when conn.commit() is called below.
            cur.execute(
                "UPDATE account@node_b_link SET balance = balance + :1 WHERE id = :2",
                [amount, dst_id],
            )

            # Triggers 2PC: PREPARE both nodes, then COMMIT both nodes.
            conn.commit()

        after_a = fetch_accounts(conn)
        conn_b = get_connection("node_b")
        after_b = fetch_accounts(conn_b)
        total_after_a = get_total_balance(conn)
        total_after_b = get_total_balance(conn_b)
        conn_b.close()

        return {
            "before_a": before_a,
            "after_a": after_a,
            "after_b": after_b,
            "total_before": total_before,
            "total_after": total_after_a + total_after_b,
            "amount": amount,
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def render() -> None:
    """Render the Scenario 1 page in the Streamlit application."""
    lang = st.session_state.get("lang", "VI")

    st.header(T("s1_header", lang))
    st.write(T("s1_intro", lang))

    col1, col2 = st.columns(2)

    conn_a = get_connection("node_a")
    conn_b = get_connection("node_b")
    accounts_a = fetch_accounts(conn_a)
    accounts_b = fetch_accounts(conn_b)
    conn_a.close()
    conn_b.close()

    a_options = {f"[A] {r['name']} (id={r['id']}, balance={r['balance']:.2f})": r["id"] for r in accounts_a}
    b_options = {f"[B] {r['name']} (id={r['id']}, balance={r['balance']:.2f})": r["id"] for r in accounts_b}

    with col1:
        src_label = st.selectbox(T("s1_debit_acct", lang), list(a_options.keys()))
        src_id = a_options[src_label]
    with col2:
        dst_label = st.selectbox(T("s1_credit_acct", lang), list(b_options.keys()))
        dst_id = b_options[dst_label]

    amount = st.number_input(T("s1_amount", lang), min_value=1.0, max_value=50000.0, value=500.0, step=100.0)

    if st.button(T("s1_btn_transfer", lang), type="primary"):
        with st.spinner(T("s1_spinner", lang)):
            try:
                result = _do_transfer(src_id, dst_id, amount)
                st.success(T("s1_success", lang))

                st.subheader(T("s1_phase_header", lang))
                phase_col = T("s1_phase_col", lang)
                phases = pd.DataFrame([
                    {phase_col: T("s1_phase_1", lang), "Node A": "READY",     "Node B": "READY"},
                    {phase_col: T("s1_phase_2", lang), "Node A": "COMMITTED", "Node B": "COMMITTED"},
                ])
                st.dataframe(phases, use_container_width=True, hide_index=True)

                st.subheader(T("s1_balance_a_header", lang))
                df_before = pd.DataFrame(result["before_a"]).rename(columns={"balance": "balance_before"})
                df_after  = pd.DataFrame(result["after_a"]).rename(columns={"balance": "balance_after"})
                df_a = df_before.merge(df_after[["id", "balance_after"]], on="id")
                df_a["delta"] = df_a["balance_after"] - df_a["balance_before"]
                st.dataframe(df_a, use_container_width=True, hide_index=True)

                st.subheader(T("s1_balance_b_header", lang))
                st.dataframe(pd.DataFrame(result["after_b"]), use_container_width=True, hide_index=True)

                st.subheader(T("s1_consistency_header", lang))
                total_before = result["total_before"]
                total_after  = result["total_after"]
                metric_col = T("s1_metric_col", lang)
                value_col  = T("s1_value_col", lang)
                consistent = T("s1_consistent_yes", lang) if abs(total_before - total_after) < 0.01 else T("s1_consistent_no", lang)
                check_df = pd.DataFrame([
                    {metric_col: T("s1_metric_sum_before", lang), value_col: f"{total_before:.2f}"},
                    {metric_col: T("s1_metric_sum_after", lang),  value_col: f"{total_after:.2f}"},
                    {metric_col: T("s1_metric_consistent", lang), value_col: consistent},
                ])
                st.dataframe(check_df, use_container_width=True, hide_index=True)

            except ValueError as exc:
                st.error(T("s1_error_val", lang, exc=exc))
            except Exception as exc:
                st.error(T("s1_error_tx", lang, exc=exc))
