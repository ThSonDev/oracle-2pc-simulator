"""
Oracle 2PC Distributed Transaction Simulator — Streamlit application entry point.

Provides a four-page interactive GUI:
  - Cluster Health: live connectivity and balance overview for both Oracle nodes.
  - Scenario 1: successful distributed Two-Phase Commit transfer via DB link.
  - Scenario 2: row-level locking and competing update demonstration.
  - Scenario 3: network failure simulation and in-doubt transaction recovery.

Navigation and all visible text are available in Vietnamese (VI, default) and
English (EN).  The language is selected via a radio widget at the top of the
sidebar and stored in st.session_state["lang"].
"""

import streamlit as st
import pandas as pd

from src.db import get_connection, fetch_accounts, get_total_balance
from src.scenarios import scenario1, scenario2, scenario3
from src.strings import T


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
    lang = st.session_state.get("lang", "VI")

    st.header(T("health_header", lang))
    st.write(T("health_intro", lang))

    for node, label_key in [("node_a", "node_a_label"), ("node_b", "node_b_label")]:
        label = T(label_key, lang)
        try:
            conn = get_connection(node)
            accounts = fetch_accounts(conn)
            total = get_total_balance(conn)
            conn.close()
            st.success(f"{label}: {T('status_online', lang)}")
            st.dataframe(
                pd.DataFrame(accounts),
                use_container_width=True,
                hide_index=True,
            )
            st.write(T("balance_total", lang, label=label, total=total))
        except Exception as exc:
            st.error(f"{label}: {T('status_offline', lang)} — {exc}")

    st.subheader(T("dblink_header", lang))
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
        st.success(T("dblink_ok", lang, count=count))
    except Exception as exc:
        st.error(T("dblink_fail", lang, exc=exc))


with st.sidebar:
    st.title("Oracle 2PC Simulator")

    # Language selector stored in st.session_state["lang"] so all pages can
    # read the current language from session state without extra parameters.
    lang = st.radio(
        T("lang_label", st.session_state.get("lang", "VI")),
        ["VI", "EN"],
        index=0,
        key="lang",
        horizontal=True,
    )

    st.caption(T("app_caption", lang))
    st.divider()

    page_defs = [
        (T("nav_health", lang), _cluster_health_page),
        (T("nav_s1", lang), scenario1.render),
        (T("nav_s2", lang), scenario2.render),
        (T("nav_s3", lang), scenario3.render),
    ]
    page_names = [p[0] for p in page_defs]
    page_func_map = dict(page_defs)

    page = st.radio(T("nav_label", lang), page_names, label_visibility="collapsed")

page_func_map[page]()
