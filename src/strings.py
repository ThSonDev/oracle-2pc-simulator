"""
Centralised translation strings for the Oracle 2PC Simulator.

STRINGS is a two-level mapping: STRINGS[lang][key] returns the text template
for the given key in the requested language.  Templates that accept runtime
values use Python str.format() placeholder syntax, e.g. "{amount:.2f}".

Call T(key, lang, **kwargs) to retrieve a translated, optionally formatted
string.  If a key is missing for the requested language, the Vietnamese ("VI")
entry is used as a fallback.  If the key is absent from both, the key itself
is returned so that missing translations are visible rather than silent.

Supported languages: "VI" (Vietnamese, default), "EN" (English).

Technical terms that are left untranslated or parenthetically clarified:
  Commit, Rollback, Two-Phase Commit (2PC), Database Link, In-Doubt,
  Prepare, Coordinator, Participant, Row-level locking, DML, SQL, Docker.
"""

STRINGS: dict[str, dict[str, str]] = {
    "VI": {
        # Sidebar and navigation
        "app_caption": "Demo giao thức Two-Phase Commit và kiểm soát đồng thời",
        "lang_label": "Ngôn ngữ / Language",
        "nav_label": "Điều hướng",
        "nav_health": "Tình trạng hệ thống (Cluster Health)",
        "nav_s1": "Kịch bản 1: Chuyển khoản 2PC thành công",
        "nav_s2": "Kịch bản 2: Xung đột đồng thời",
        "nav_s3": "Kịch bản 3: Lỗi mạng / Giao dịch In-Doubt",

        # Cluster Health page
        "health_header": "Tình trạng hệ thống (Cluster Health)",
        "health_intro": "Trạng thái trực tiếp của hai Oracle node và Database Link.",
        "node_a_label": "Node A (Coordinator toàn cục)",
        "node_b_label": "Node B (Điểm cục bộ)",
        "status_online": "TRỰC TUYẾN",
        "status_offline": "NGOẠI TUYẾN",
        "balance_total": "Tổng số dư trên {label}: {total:.2f}",
        "dblink_header": "Kiểm tra Database Link",
        "dblink_ok": "Database Link 'node_b_link' hoạt động — thấy {count} dòng trên Node B.",
        "dblink_fail": "Kiểm tra Database Link thất bại: {exc}",

        # Scenario 1
        "s1_header": "Kịch bản 1: Giao dịch phân tán thành công",
        "s1_intro": (
            "Kịch bản này chuyển tiền từ một tài khoản trên Node A sang một tài khoản trên Node B. "
            "Oracle tự động thực hiện Two-Phase Commit: gửi PREPARE đến cả hai node, "
            "chờ phản hồi READY, sau đó gửi COMMIT đến cả hai."
        ),
        "s1_debit_acct": "Tài khoản ghi nợ (Node A)",
        "s1_credit_acct": "Tài khoản nhận tiền (Node B)",
        "s1_amount": "Số tiền chuyển",
        "s1_btn_transfer": "Thực hiện chuyển khoản (Execute Transfer)",
        "s1_spinner": "Đang thực hiện giao dịch phân tán...",
        "s1_success": "Giao dịch đã được Commit thành công.",
        "s1_phase_header": "Tóm tắt các giai đoạn 2PC",
        "s1_phase_col": "Giai đoạn",
        "s1_phase_1": "1 - PREPARE",
        "s1_phase_2": "2 - COMMIT",
        "s1_balance_a_header": "Thay đổi số dư trên Node A",
        "s1_balance_b_header": "Số dư trên Node B (sau Commit)",
        "s1_consistency_header": "Kiểm tra tính nhất quán toàn cục",
        "s1_metric_col": "Chỉ số",
        "s1_value_col": "Giá trị",
        "s1_metric_sum_before": "Tổng (Node A + Node B) trước chuyển khoản",
        "s1_metric_sum_after": "Tổng (Node A + Node B) sau chuyển khoản",
        "s1_metric_consistent": "Nhất quán",
        "s1_consistent_yes": "CÓ",
        "s1_consistent_no": "KHÔNG",
        "s1_error_val": "{exc}",
        "s1_error_tx": "Giao dịch thất bại: {exc}",

        # Scenario 2
        "s2_header": "Kịch bản 2: Xung đột đồng thời",
        "s2_intro": (
            "Một background thread chiếm giữ Row-level lock thông qua SELECT ... FOR UPDATE. "
            "Một UPDATE cạnh tranh trên cùng dòng đó sẽ bị chặn cho đến khi giao dịch đầu tiên "
            "giải phóng khóa."
        ),
        "s2_acct_select": "Tài khoản cần khóa",
        "s2_hold_slider": "Thời gian giữ khóa (giây)",
        "s2_btn_acquire": "Chiếm giữ khóa (Acquire Lock)",
        "s2_btn_compete": "Thử cập nhật cạnh tranh (Attempt Competing Update)",
        "s2_btn_release": "Giải phóng khóa (Release Lock)",
        "s2_spinner_compete": "Đang thử UPDATE (sẽ chờ cho đến khi khóa được giải phóng)...",
        "s2_log_header": "Nhật ký trạng thái khóa",
        "s2_lock_active": "Khóa đang HOẠT ĐỘNG (background thread đang giữ Row-level lock).",
        "s2_lock_finished": "Thread giữ khóa đã kết thúc.",
        "s2_compete_header": "Kết quả cập nhật cạnh tranh",
        "s2_compete_success": "UPDATE thành công sau {elapsed:.2f} giây (số dư tăng thêm {increment:.2f}).",
        "s2_compete_blocked": "UPDATE hết thời gian chờ hoặc bị chặn sau {elapsed:.2f} giây. Oracle phản hồi: {message}",
        "s2_balances_header": "Số dư tài khoản hiện tại (Node A)",
        "s2_lock_acquired_msg": "Đã chiếm giữ khóa (Acquire Lock) trên tài khoản id={account_id} (tên={name}, số dư={balance:.2f}).",
        "s2_lock_released_msg": "Đã giải phóng khóa (Rollback giao dịch).",
        "s2_lock_error_msg": "Lỗi thread giữ khóa: {exc}",

        # Scenario 3
        "s3_header": "Kịch bản 3: Lỗi mạng / Giao dịch In-Doubt",
        "s3_intro": (
            "Kịch bản này bắt đầu một giao dịch phân tán và cắt kết nối mạng của Node B "
            "ngay trước giai đoạn Commit. Oracle không thể hoàn thành 2PC và giao dịch được "
            "ghi vào DBA_2PC_PENDING với trạng thái in-doubt. "
            "Bạn có thể buộc Commit hoặc Rollback thủ công."
        ),
        "s3_debit_acct": "Tài khoản ghi nợ (Node A)",
        "s3_credit_acct": "Tài khoản nhận tiền (Node B)",
        "s3_amount": "Số tiền chuyển",
        "s3_btn_simulate": "Giả lập lỗi mạng trong lúc Commit (Simulate Network Failure)",
        "s3_spinner": "Đang giả lập lỗi mạng...",
        "s3_log_header": "Nhật ký thực thi",
        "s3_pending_header": "DBA_2PC_PENDING - Giao dịch In-Doubt",
        "s3_recovery_header": "Khôi phục thủ công",
        "s3_tran_select": "Chọn giao dịch cần xử lý",
        "s3_btn_commit_force": "Thực hiện COMMIT FORCE",
        "s3_btn_rollback_force": "Thực hiện ROLLBACK FORCE",
        "s3_btn_refresh": "Làm mới DBA_2PC_PENDING",
        "s3_balances_header": "Số dư hiện tại",
        "s3_node_a": "Node A",
        "s3_node_b": "Node B",
        "s3_node_a_unreachable": "Không thể kết nối Node A: {exc}",
        "s3_node_b_unreachable": "Không thể kết nối Node B: {exc}",
        "s3_log_start": "Bắt đầu giao dịch phân tán trên Node A...",
        "s3_log_node_a_deducted": "  Node A: đã trừ {amount:.2f} từ tài khoản id={src_id}.",
        "s3_log_node_b_credited": "  Node B (qua Database Link): đã cộng {amount:.2f} vào tài khoản id={dst_id}.",
        "s3_log_disconnecting": "Ngắt kết nối Node B khỏi mạng Docker để giả lập sự cố...",
        "s3_log_disconnected": "  Node B đã không còn kết nối.",
        "s3_log_attempting_commit": "Đang thực hiện COMMIT (Oracle sẽ thử 2PC PREPARE + COMMIT)...",
        "s3_log_commit_ok": "  COMMIT hoàn thành (Oracle có thể đã dùng kết nối được cache).",
        "s3_log_commit_fail": "  COMMIT THẤT BẠI: {msg}",
        "s3_log_unexpected": "  Lỗi không mong muốn: {exc}",
        "s3_log_reconnecting": "Đang kết nối lại Node B vào mạng Docker...",
        "s3_log_reconnected": "  Node B đã được kết nối lại.",
        "s3_log_reconnect_warn": "  Cảnh báo kết nối lại: {exc}",
        "s3_log_querying_pending": "Đang truy vấn DBA_2PC_PENDING trên Node A...",
        "s3_log_found_pending": "  Tìm thấy {n} giao dịch in-doubt.",
        "s3_log_query_fail": "  Không thể truy vấn DBA_2PC_PENDING: {exc}",
        "s3_log_commit_force_ok": "COMMIT FORCE '{tran_id}' thành công.",
        "s3_log_rollback_force_ok": "ROLLBACK FORCE '{tran_id}' thành công.",
        "s3_log_force_error": "Lỗi khôi phục cưỡng bức: {msg}",
    },

    "EN": {
        # Sidebar and navigation
        "app_caption": "Two-Phase Commit and Concurrency Control Demo",
        "lang_label": "Language / Ngôn ngữ",
        "nav_label": "Navigate",
        "nav_health": "Cluster Health",
        "nav_s1": "Scenario 1: Successful 2PC Transfer",
        "nav_s2": "Scenario 2: Concurrency Conflict",
        "nav_s3": "Scenario 3: Network Failure / In-Doubt",

        # Cluster Health page
        "health_header": "Cluster Health",
        "health_intro": "Live status of both Oracle nodes and the DB link.",
        "node_a_label": "Node A (Global Coordinator)",
        "node_b_label": "Node B (Local Site)",
        "status_online": "ONLINE",
        "status_offline": "OFFLINE",
        "balance_total": "Total balance on {label}: {total:.2f}",
        "dblink_header": "DB Link Verification",
        "dblink_ok": "DB link 'node_b_link' is working — {count} row(s) visible on Node B.",
        "dblink_fail": "DB link check failed: {exc}",

        # Scenario 1
        "s1_header": "Scenario 1: Successful Distributed Transaction",
        "s1_intro": (
            "This scenario transfers funds from an account on Node A to an account on Node B. "
            "Oracle executes Two-Phase Commit automatically: it sends PREPARE to both nodes, "
            "waits for READY responses, then issues COMMIT to both."
        ),
        "s1_debit_acct": "Debit account (Node A)",
        "s1_credit_acct": "Credit account (Node B)",
        "s1_amount": "Transfer amount",
        "s1_btn_transfer": "Execute Transfer",
        "s1_spinner": "Executing distributed transaction...",
        "s1_success": "Transaction committed successfully.",
        "s1_phase_header": "2PC Phase Summary",
        "s1_phase_col": "Phase",
        "s1_phase_1": "1 - PREPARE",
        "s1_phase_2": "2 - COMMIT",
        "s1_balance_a_header": "Balance Changes on Node A",
        "s1_balance_b_header": "Balances on Node B (after commit)",
        "s1_consistency_header": "Global Consistency Check",
        "s1_metric_col": "Metric",
        "s1_value_col": "Value",
        "s1_metric_sum_before": "Sum (Node A) before transfer",
        "s1_metric_sum_after": "Sum (Node A + Node B) after transfer",
        "s1_metric_consistent": "Consistent",
        "s1_consistent_yes": "YES",
        "s1_consistent_no": "NO",
        "s1_error_val": "{exc}",
        "s1_error_tx": "Transaction failed: {exc}",

        # Scenario 2
        "s2_header": "Scenario 2: Concurrency Conflict",
        "s2_intro": (
            "A background thread acquires a row-level lock via SELECT ... FOR UPDATE. "
            "A competing UPDATE on the same row will block until the first transaction "
            "releases the lock."
        ),
        "s2_acct_select": "Account to lock",
        "s2_hold_slider": "Hold lock for (seconds)",
        "s2_btn_acquire": "Acquire Lock (background)",
        "s2_btn_compete": "Attempt Competing Update",
        "s2_btn_release": "Release Lock",
        "s2_spinner_compete": "Attempting UPDATE (will block until lock is released)...",
        "s2_log_header": "Lock Status Log",
        "s2_lock_active": "Lock is currently ACTIVE (background thread holds the row lock).",
        "s2_lock_finished": "Lock thread has finished.",
        "s2_compete_header": "Competing Update Result",
        "s2_compete_success": "UPDATE succeeded after {elapsed:.2f}s (balance incremented by {increment:.2f}).",
        "s2_compete_blocked": "UPDATE timed out or was blocked after {elapsed:.2f}s. Oracle response: {message}",
        "s2_balances_header": "Current Account Balances (Node A)",
        "s2_lock_acquired_msg": "Lock acquired on account id={account_id} (name={name}, balance={balance:.2f}).",
        "s2_lock_released_msg": "Lock released (transaction rolled back).",
        "s2_lock_error_msg": "Lock holder error: {exc}",

        # Scenario 3
        "s3_header": "Scenario 3: Network Failure / In-Doubt Transaction",
        "s3_intro": (
            "This scenario starts a distributed transaction and then severs Node B's "
            "network connection just before the commit phase. Oracle cannot complete "
            "2PC and the transaction is recorded in DBA_2PC_PENDING as in-doubt. "
            "You can then manually force a commit or rollback."
        ),
        "s3_debit_acct": "Debit account (Node A)",
        "s3_credit_acct": "Credit account (Node B)",
        "s3_amount": "Transfer amount",
        "s3_btn_simulate": "Simulate Network Failure During Commit",
        "s3_spinner": "Simulating network failure...",
        "s3_log_header": "Execution Log",
        "s3_pending_header": "DBA_2PC_PENDING - In-Doubt Transactions",
        "s3_recovery_header": "Manual Recovery",
        "s3_tran_select": "Select transaction to resolve",
        "s3_btn_commit_force": "Force Commit",
        "s3_btn_rollback_force": "Force Rollback",
        "s3_btn_refresh": "Refresh DBA_2PC_PENDING",
        "s3_balances_header": "Current Balances",
        "s3_node_a": "Node A",
        "s3_node_b": "Node B",
        "s3_node_a_unreachable": "Node A unreachable: {exc}",
        "s3_node_b_unreachable": "Node B unreachable: {exc}",
        "s3_log_start": "Starting distributed transaction on Node A...",
        "s3_log_node_a_deducted": "  Node A: deducted {amount:.2f} from account id={src_id}.",
        "s3_log_node_b_credited": "  Node B (via DB link): credited {amount:.2f} to account id={dst_id}.",
        "s3_log_disconnecting": "Disconnecting Node B from Docker network to simulate crash...",
        "s3_log_disconnected": "  Node B is now unreachable.",
        "s3_log_attempting_commit": "Attempting COMMIT (Oracle will try 2PC PREPARE + COMMIT)...",
        "s3_log_commit_ok": "  COMMIT completed (Oracle may have used a cached connection).",
        "s3_log_commit_fail": "  COMMIT FAILED: {msg}",
        "s3_log_unexpected": "  Unexpected error: {exc}",
        "s3_log_reconnecting": "Reconnecting Node B to Docker network...",
        "s3_log_reconnected": "  Node B reconnected.",
        "s3_log_reconnect_warn": "  Reconnect warning: {exc}",
        "s3_log_querying_pending": "Querying DBA_2PC_PENDING on Node A...",
        "s3_log_found_pending": "  Found {n} in-doubt transaction(s).",
        "s3_log_query_fail": "  Could not query DBA_2PC_PENDING: {exc}",
        "s3_log_commit_force_ok": "COMMIT FORCE '{tran_id}' succeeded.",
        "s3_log_rollback_force_ok": "ROLLBACK FORCE '{tran_id}' succeeded.",
        "s3_log_force_error": "Force recover error: {msg}",
    },
}


def T(key: str, lang: str, **kwargs) -> str:
    """
    Return the translated string for key in lang, formatted with any kwargs.

    Falls back to VI if lang is not recognised or the key is absent in lang.
    Returns the key itself if the key is absent from both languages, making
    missing translations visible rather than silently empty.
    """
    vi = STRINGS["VI"]
    template = STRINGS.get(lang, vi).get(key) or vi.get(key, key)
    return template.format(**kwargs) if kwargs else template
