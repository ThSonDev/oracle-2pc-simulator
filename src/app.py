"""
Oracle 2PC Distributed Transaction Simulator — Streamlit application entry point.

Provides a four-page interactive GUI:
  - Cluster Health: live connectivity and balance overview for both Oracle nodes.
  - Scenario 1: successful distributed Two-Phase Commit transfer via DB link.
  - Scenario 2: row-level locking and competing update demonstration.
  - Scenario 3: network failure simulation and in-doubt transaction recovery.

Navigation is handled by a sidebar radio widget.  Each page delegates to the
render() function in its corresponding scenario module.
"""

import streamlit as st
import pandas as pd

from src.db import get_connection, fetch_accounts, get_total_balance
from src.scenarios import scenario1, scenario2, scenario3


st.set_page_config(
    page_title="Oracle 2PC Simulator",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _cluster_health_page() -> None:
    """
    Render the Cluster Health dashboard.

    Connects to both Oracle nodes and reports their online/offline status,
    current account balances, and the operational state of the DB link
    between Node A and Node B.  Any connection failure is displayed as an
    error rather than raising an exception, so a partial outage still renders
    the available node's data.
    """
    st.header("Cluster Health")
    st.write("Live status of both Oracle nodes and the DB link.")

    for node, label in [("node_a", "Node A (Global Coordinator)"), ("node_b", "Node B (Local Site)")]:
        try:
            conn = get_connection(node)
            accounts = fetch_accounts(conn)
            total = get_total_balance(conn)
            conn.close()
            st.success(f"{label}: ONLINE")
            st.dataframe(
                pd.DataFrame(accounts),
                use_container_width=True,
                hide_index=True,
            )
            st.write(f"Total balance on {label}: {total:.2f}")
        except Exception as exc:
            st.error(f"{label}: OFFLINE — {exc}")

    st.subheader("DB Link Verification")
    try:
        conn = get_connection("node_a")
        with conn.cursor() as cur:
            # A successful SELECT via node_b_link confirms that Node A can
            # open an authenticated session on Node B through the DB link,
            # which is a prerequisite for the distributed transactions in
            # Scenario 1 and Scenario 3.
            cur.execute("SELECT COUNT(*) FROM account@node_b_link")
            count = cur.fetchone()[0]
        conn.close()
        st.success(f"DB link 'node_b_link' is working — {count} row(s) visible on Node B.")
    except Exception as exc:
        st.error(f"DB link check failed: {exc}")


PAGE_MAP = {
    "Cluster Health": _cluster_health_page,
    "Scenario 1: Successful 2PC Transfer": scenario1.render,
    "Scenario 2: Concurrency Conflict": scenario2.render,
    "Scenario 3: Network Failure / In-Doubt": scenario3.render,
}

with st.sidebar:
    st.title("Oracle 2PC Simulator")
    st.caption("Two-Phase Commit and Concurrency Control Demo")
    st.divider()
    page = st.radio("Navigate", list(PAGE_MAP.keys()), label_visibility="collapsed")

PAGE_MAP[page]()
