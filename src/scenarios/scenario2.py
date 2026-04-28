"""
Scenario 2: Concurrency Conflict and Row-Level Locking.

Demonstrates Oracle's row-level locking behaviour when two transactions
compete for the same row.

A background thread acquires an exclusive row lock using SELECT ... FOR UPDATE.
While the lock is held the Streamlit user can trigger a competing UPDATE on the
same row.  Oracle blocks the competing UPDATE at the database level until the
first transaction either commits or rolls back and releases the lock.

Key Oracle behaviours illustrated:
  - SELECT ... FOR UPDATE acquires an exclusive row lock immediately.
  - A concurrent UPDATE on the locked row blocks inside the Oracle kernel;
    the Python client call does not return until the lock is available.
  - FOR UPDATE WAIT n causes Oracle to raise ORA-30006 if the lock cannot
    be acquired within n seconds, rather than blocking indefinitely.
  - A rolled-back transaction releases its locks atomically; any blocked
    UPDATE proceeds as soon as the rollback is complete.
"""

import threading
import time

import oracledb
import streamlit as st
import pandas as pd

from src.db import get_connection, fetch_accounts
from src.strings import T


def _lock_holder(
    account_id: int,
    hold_seconds: int,
    status_list: list,
    release_event: threading.Event,
    lang: str = "VI",
) -> None:
    """
    Acquire an exclusive row lock on the given account and hold it.

    Runs in a daemon thread so that the Streamlit process can exit cleanly
    even if the lock is never explicitly released.  Appends status strings
    to status_list so the main thread can read them without shared mutable
    state requiring a lock of its own.

    The lock is released by rolling back the transaction, which is the
    correct way to release a SELECT ... FOR UPDATE lock when no actual
    data change was intended.

    Parameters
    ----------
    account_id:
        The account row to lock on Node A.
    hold_seconds:
        Maximum seconds to hold the lock before automatically releasing.
        release_event.wait() will block for up to this many seconds.
    status_list:
        Shared list to which status messages are appended.
    release_event:
        When this event is set the lock is released immediately.
    lang:
        Language code for log messages ("VI" or "EN").
    """
    conn = None
    try:
        conn = get_connection("node_a", autocommit=False)
        with conn.cursor() as cur:
            # FOR UPDATE acquires an exclusive row lock.  The SELECT also
            # fetches the current values so we can log them for the UI.
            cur.execute(
                "SELECT id, name, balance FROM account WHERE id = :1 FOR UPDATE",
                [account_id],
            )
            row = cur.fetchone()
            status_list.append(
                T("s2_lock_acquired_msg", lang,
                  account_id=account_id, name=row[1], balance=float(row[2]))
            )
            release_event.wait(timeout=hold_seconds)
        # Rolling back releases the row lock and discards any uncommitted
        # changes.  No actual UPDATE was issued, so the balance is unchanged.
        conn.rollback()
        status_list.append(T("s2_lock_released_msg", lang))
    except Exception as exc:
        status_list.append(T("s2_lock_error_msg", lang, exc=exc))
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _competing_update(account_id: int, increment: float, wait_timeout_s: int) -> dict:
    """
    Attempt to UPDATE the same account row that the lock holder has locked.

    Uses FOR UPDATE WAIT n so that the call blocks inside Oracle for up to
    wait_timeout_s seconds.  If the lock holder releases before the timeout,
    the update proceeds and commits normally.  If the timeout expires first,
    Oracle raises ORA-30006 and the function returns a blocked/timeout result
    without raising an exception, allowing the UI to display the outcome.

    Parameters
    ----------
    account_id:
        The account to update.
    increment:
        Amount to add to the balance.
    wait_timeout_s:
        Seconds to wait for the row lock before timing out.

    Returns
    -------
    A dict with keys: status ("success" or "blocked_or_timeout"),
    elapsed (seconds), and either increment or message.
    """
    conn = None
    start = time.time()
    try:
        conn = get_connection("node_a", autocommit=False)
        with conn.cursor() as cur:
            # FOR UPDATE WAIT n blocks until the row lock is released or the
            # timeout expires.  This surfaces the blocking behaviour directly
            # in the Python call rather than hanging indefinitely.
            cur.execute(
                f"SELECT id FROM account WHERE id = :1 FOR UPDATE WAIT {wait_timeout_s}",
                [account_id],
            )
            cur.execute(
                "UPDATE account SET balance = balance + :1 WHERE id = :2",
                [increment, account_id],
            )
            conn.commit()
        elapsed = time.time() - start
        return {"status": "success", "elapsed": elapsed, "increment": increment}
    except oracledb.DatabaseError as exc:
        elapsed = time.time() - start
        (error,) = exc.args
        return {"status": "blocked_or_timeout", "elapsed": elapsed, "message": str(error)}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def render() -> None:
    """Render the Scenario 2 page in the Streamlit application."""
    lang = st.session_state.get("lang", "VI")

    st.header(T("s2_header", lang))
    st.write(T("s2_intro", lang))

    if "lock_status" not in st.session_state:
        st.session_state.lock_status = []
    if "lock_thread" not in st.session_state:
        st.session_state.lock_thread = None
    if "release_event" not in st.session_state:
        st.session_state.release_event = None
    if "competing_result" not in st.session_state:
        st.session_state.competing_result = None

    conn_a = get_connection("node_a")
    accounts = fetch_accounts(conn_a)
    conn_a.close()
    a_opts = {f"{r['name']} (id={r['id']}, balance={r['balance']:.2f})": r["id"] for r in accounts}

    col1, col2 = st.columns(2)
    with col1:
        lock_label = st.selectbox(T("s2_acct_select", lang), list(a_opts.keys()), key="lock_acct")
        lock_id = a_opts[lock_label]
    with col2:
        hold_seconds = st.slider(T("s2_hold_slider", lang), min_value=5, max_value=60, value=20)

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        lock_btn_disabled = (
            st.session_state.lock_thread is not None
            and st.session_state.lock_thread.is_alive()
        )
        if st.button(T("s2_btn_acquire", lang), disabled=lock_btn_disabled):
            st.session_state.lock_status = []
            st.session_state.competing_result = None
            event = threading.Event()
            st.session_state.release_event = event
            # Capture lang at thread-start time; session_state is not thread-safe.
            t = threading.Thread(
                target=_lock_holder,
                args=(lock_id, hold_seconds, st.session_state.lock_status, event, lang),
                daemon=True,
            )
            st.session_state.lock_thread = t
            t.start()
            # Brief pause to let the background thread acquire the lock before
            # the page re-renders and displays the "lock active" status.
            time.sleep(0.5)
            st.rerun()

    with col_b:
        lock_active = (
            st.session_state.lock_thread is not None
            and st.session_state.lock_thread.is_alive()
        )
        if st.button(T("s2_btn_compete", lang), disabled=not lock_active):
            with st.spinner(T("s2_spinner_compete", lang)):
                result = _competing_update(lock_id, increment=1.0, wait_timeout_s=hold_seconds + 10)
                st.session_state.competing_result = result
                st.rerun()

    with col_c:
        release_active = (
            st.session_state.release_event is not None
            and st.session_state.lock_thread is not None
            and st.session_state.lock_thread.is_alive()
        )
        if st.button(T("s2_btn_release", lang), disabled=not release_active):
            if st.session_state.release_event:
                st.session_state.release_event.set()
            time.sleep(0.5)
            st.rerun()

    st.divider()
    st.subheader(T("s2_log_header", lang))

    thread = st.session_state.lock_thread
    if thread is not None:
        is_alive = thread.is_alive()
        if is_alive:
            st.info(T("s2_lock_active", lang))
        else:
            st.success(T("s2_lock_finished", lang))

    for msg in st.session_state.lock_status:
        st.write(f"  {msg}")

    result = st.session_state.competing_result
    if result:
        st.subheader(T("s2_compete_header", lang))
        if result["status"] == "success":
            st.success(T("s2_compete_success", lang, elapsed=result["elapsed"], increment=result["increment"]))
        else:
            st.warning(T("s2_compete_blocked", lang, elapsed=result["elapsed"], message=result["message"]))

    st.divider()
    st.subheader(T("s2_balances_header", lang))
    conn_a = get_connection("node_a")
    current = fetch_accounts(conn_a)
    conn_a.close()
    st.dataframe(pd.DataFrame(current), use_container_width=True, hide_index=True)
