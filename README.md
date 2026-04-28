[English Version](README_en.md)

# Trình Mô Phỏng Giao Tác Phân Tán 2PC trên Oracle

Trình mô phỏng tương tác dựa trên Docker, minh họa giao thức Two-Phase Commit (2PC) của Oracle,
cơ chế Row-level locking, và quy trình khôi phục giao tác treo (in-doubt transaction recovery).
Dự án chạy hai phiên bản Oracle Free 23c kết nối qua một Database Link riêng tư trên mạng bridge
nội bộ, đồng thời cung cấp giao diện web Streamlit với ba kịch bản hướng dẫn.

## Tổng quan dự án

Giao thức Two-Phase Commit của Oracle đảm bảo tính atomicity cho các giao tác trải rộng trên nhiều
database instance. Khi một giao tác sửa đổi dữ liệu trên nhiều node, Coordinator sẽ thực thi một
trình tự hai giai đoạn trước khi báo thành công cho client:

- Giai đoạn 1 (PREPARE): Coordinator yêu cầu từng Participant ghi một bản ghi prepare vào redo log
  của nó và phản hồi READY. Khi tất cả Participant đã phản hồi, kết quả giao tác được quyết định
  và trở nên bền vững trên Coordinator.
- Giai đoạn 2 (COMMIT): Coordinator ghi bản ghi commit của chính nó, sau đó gửi COMMIT đến từng
  Participant và chờ xác nhận COMMITTED.

Trình mô phỏng này cho phép quan sát từng giai đoạn, kích hoạt lỗi mạng giữa hai giai đoạn để tạo
trạng thái in-doubt, và thực hiện lệnh khôi phục thủ công (COMMIT FORCE, ROLLBACK FORCE) theo cách
một DBA xử lý trong sự cố thực tế.

## Cấu trúc dự án

```text
oracle-2pc-simulator/
├── .env                          Biến môi trường mặc định cho Docker Compose
├── docker-compose.yml            Stack ba dịch vụ: node_a, node_b, streamlit
├── Dockerfile                    Image Python 3.11-slim cho ứng dụng Streamlit
├── requirements.txt              Thư viện Python: streamlit, oracledb, docker, pandas, pytest
├── scripts/
│   ├── 00_grants_a.sh            Khởi tạo Node A: cấp quyền SYSDBA, bảng account, dữ liệu mẫu, DB link
│   └── 00_grants_b.sh            Khởi tạo Node B: cấp quyền SYSDBA, bảng account, dữ liệu mẫu
└── src/
    ├── app.py                    Điểm vào Streamlit; điều hướng sidebar đến bốn trang
    ├── config.py                 Hằng số kết nối và giá trị số dư khởi tạo (cấu hình qua env)
    ├── db.py                     Khởi tạo kết nối, các hàm truy vấn hỗ trợ, tiện ích reset kiểm thử
    ├── strings.py                Từ điển dịch thuật VI/EN cho toàn bộ giao diện người dùng
    ├── scenarios/
    │   ├── __init__.py
    │   ├── scenario1.py          Giao tác 2PC phân tán thành công qua DB link
    │   ├── scenario2.py          Row-level locking và UPDATE cạnh tranh
    │   └── scenario3.py          Giả lập lỗi mạng và khôi phục giao tác in-doubt
    └── tests/
        ├── __init__.py
        └── test_scenarios.py     Bộ kiểm thử pytest bao phủ cả ba kịch bản
```

## Điều kiện tiên quyết

- Docker Engine 24.0 trở lên
- Docker Compose 2.20 trở lên (có sẵn trong Docker Desktop hoặc cài đặt như một plugin)
- Ít nhất 8 GB RAM trống (Oracle Free 23c sử dụng khoảng 2 GB cho mỗi instance; container ứng dụng
  cần thêm khoảng 200 MB)
- Khuyến nghị 16 GB tổng RAM hệ thống để máy chủ (host OS) hoạt động mượt mà
- Linux host hoặc Docker Desktop trên macOS hoặc Windows

## Kiến trúc

```text
oracle_node_a  (Coordinator toàn cục)           oracle_node_b  (Điểm cục bộ)
Oracle Free 23c                                 Oracle Free 23c
host port 1521                                  host port 1522
     |                                                |
     |  node_b_link (Database Link riêng tư)          |
     +--------------------------------------------------+
                    oracle_net (bridge)
                          |
                   streamlit_app
                   Python 3.11
                   host port 8501
                   /var/run/docker.sock
```

Node A là Coordinator toàn cục. Node A giữ Database Link riêng tư `node_b_link` để định tuyến các
thao tác DML từ xa đến Node B. Khi `conn.commit()` được gọi trên kết nối đến Node A trong khi giao
tác đã chạm vào Node B qua link, Oracle tự động thực hiện toàn bộ giao thức 2PC giữa hai tiến trình
database server, hoàn toàn trong suốt (invisible) với Python client.

Container Streamlit có quyền truy cập Docker socket để Kịch bản 3 có thể ngắt và kết nối lại giao
diện mạng của Node B thông qua Docker SDK, mô phỏng lỗi mạng giữa chừng trong quá trình commit mà
không cần bất kỳ công cụ cấu hình mạng bên ngoài nào.

### Thiết kế khởi tạo

Toàn bộ thiết lập schema (tạo bảng, dữ liệu mẫu, cấp quyền, DB link) được thực hiện bởi hai shell
script đặt trong `/docker-entrypoint-initdb.d/` bên trong mỗi Oracle container. Image
gvenzl/oracle-free thực thi các script này theo thứ tự từ điển (lexicographic) ở lần khởi động đầu
tiên khi data volume còn trống. Không có container setup riêng biệt.

Node A yêu cầu hai phiên sqlplus trong `00_grants_a.sh`:
- Phiên 1 kết nối với tư cách SYSDBA, thực thi các lệnh GRANT, tạo bảng account và chèn dữ liệu
  mẫu, sử dụng `ALTER SESSION SET CURRENT_SCHEMA` để đặt các đối tượng vào schema của app_user.
- Phiên 2 kết nối với tư cách app_user và tạo Database Link riêng tư. Oracle 23c Free không cho
  phép `CREATE PUBLIC DATABASE LINK` bên trong PDB kể cả với SYS/SYSDBA (ORA-01031), do đó link
  phải được tạo bởi user sở hữu.

Node B chỉ yêu cầu một phiên SYSDBA trong `00_grants_b.sh` vì không cần Database Link ở phía
Participant.

Toàn bộ mã Python vận hành (kịch bản, kiểm thử) chỉ kết nối với tư cách app_user. Không sử dụng
thông tin đăng nhập SYSTEM hoặc SYSDBA trong thời gian chạy.

## Khởi động nhanh

### Cài đặt lần đầu

```bash
git clone <repo_url> oracle-2pc-simulator
cd oracle-2pc-simulator
docker compose up -d
```

Oracle Free 23c sử dụng biến thể image `faststart` bao gồm một template DBCA dựng sẵn và thường
khởi tạo trong 2-3 phút trên phần cứng có ổ cứng tốc độ cao. Theo dõi tiến trình khởi tạo:

```bash
docker compose logs -f node_a node_b
```

Đợi cho đến khi cả hai node in ra:

```text
DATABASE IS READY TO USE!
```

Theo sau là thông báo hoàn tất script khởi tạo:

```text
oracle_node_a  | Node A init complete.
oracle_node_b  | Node B init complete.
```

Kiểm tra xem cả ba dịch vụ đều đang chạy và healthy:

```bash
docker compose ps
```

Đầu ra dự kiến:

```text
NAME             IMAGE                                STATUS
oracle_node_a    gvenzl/oracle-free:23-slim-faststart Up (healthy)
oracle_node_b    gvenzl/oracle-free:23-slim-faststart Up (healthy)
streamlit_app    oracle-2pc-simulator-streamlit        Up
```

### Các lần khởi động sau (khi đã có data volumes)

```bash
docker compose up -d
```

Các script khởi tạo sẽ không chạy lại khi data volumes đã có dữ liệu.

### Khôi phục cài đặt gốc (xóa toàn bộ dữ liệu Oracle)

```bash
docker compose down -v
docker compose up -d
```

Cờ `-v` sẽ xóa các named volume, buộc Oracle phải khởi tạo lại từ đầu vào lần khởi động tiếp theo.

### Xác minh Database Link

Xác nhận DB link từ Node A đến Node B đang hoạt động:

```bash
docker exec oracle_node_a bash -c \
  "sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< 'SELECT COUNT(*) AS node_b_rows FROM account@node_b_link;'"
```

Đầu ra dự kiến:

```text
NODE_B_ROWS
-----------
          2
```

## Truy cập giao diện

Mở trình duyệt và điều hướng tới:

```text
http://localhost:8501
```

Sidebar chứa bốn trang. Giao diện mặc định hiển thị bằng tiếng Việt; chọn EN trên bộ chọn ngôn
ngữ ở đầu sidebar để chuyển sang tiếng Anh.

- **Tình trạng hệ thống (Cluster Health)**: trạng thái kết nối, số dư hiện tại, và kiểm tra DB link.
- **Kịch bản 1: Chuyển khoản 2PC thành công**: giao tác Two-Phase Commit phân tán thành công.
- **Kịch bản 2: Xung đột đồng thời**: Row-level locking và UPDATE cạnh tranh.
- **Kịch bản 3: Lỗi mạng / Giao dịch In-Doubt**: giả lập lỗi mạng và khôi phục thủ công.

## Hướng dẫn các kịch bản

### Tình trạng hệ thống (Cluster Health)

Điều hướng đến "Tình trạng hệ thống (Cluster Health)" trong sidebar. Trang hiển thị bảng account
trực tiếp của cả Node A và Node B, đồng thời thực hiện SELECT qua Database Link để xác nhận link
đang hoạt động. Tất cả tài khoản phải hiển thị đầy đủ và trạng thái link phải báo là đang hoạt động.

### Kịch bản 1: Chuyển khoản 2PC thành công

Minh họa cơ chế Two-Phase Commit tự động của Oracle.

1. Điều hướng đến "Kịch bản 1: Chuyển khoản 2PC thành công".
2. Chọn tài khoản ghi nợ (Node A), ví dụ Alice, id=1, số dư=10000.00.
3. Chọn tài khoản nhận tiền (Node B), ví dụ Bob, id=1, số dư=8000.00.
4. Nhập số tiền chuyển, ví dụ 500.
5. Nhấp nút "Thực hiện chuyển khoản (Execute Transfer)".

Diễn biến nội bộ:

- Ứng dụng lấy khóa `SELECT ... FOR UPDATE` trên hàng nguồn, xác thực số dư, sau đó phát lệnh
  `UPDATE` cục bộ trên Node A và `UPDATE` từ xa qua `node_b_link` trên Node B.
- Lệnh `conn.commit()` kích hoạt quy trình 2PC của Oracle: PREPARE được gửi đến cả hai node, phản
  hồi READY nhận từ cả hai, COMMIT được ghi lại trên Coordinator, sau đó tín hiệu COMMIT được gửi
  đến cả hai Participant.
- Trang kết quả hiển thị Tóm tắt các giai đoạn 2PC, thay đổi số dư từng node, và kiểm tra tính
  nhất quán toàn cục xác nhận tổng số tiền không thay đổi.

Kết quả dự kiến: số dư Node A giảm đúng bằng số tiền chuyển; số dư Node B tăng tương ứng; kiểm
tra nhất quán hiển thị "CÓ".

### Kịch bản 2: Xung đột đồng thời

Minh họa Row-level locking và cô lập đọc (read isolation).

1. Điều hướng đến "Kịch bản 2: Xung đột đồng thời".
2. Chọn tài khoản cần khóa, ví dụ Alice, id=1.
3. Đặt thời gian giữ khóa (giây), ví dụ 20.
4. Nhấp nút "Chiếm giữ khóa (Acquire Lock)". Nhật ký trạng thái khóa xác nhận đã chiếm giữ thành
   công.
5. Trong khi khóa đang hoạt động, nhấp nút "Thử cập nhật cạnh tranh (Attempt Competing Update)".
   Spinner cho thấy UPDATE đang bị chặn (blocked) bên trong Oracle.
6. Để quan sát phiên đang bị chặn từ một terminal riêng:

```bash
docker exec oracle_node_a bash -c \
  "sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< \"SELECT sid, state, seconds_in_wait FROM v\\\$session WHERE wait_class = 'Application';\""
```

7. Nhấp nút "Giải phóng khóa (Release Lock)" để Rollback giao tác đang giữ khóa.

Kết quả dự kiến: trạng thái của UPDATE cạnh tranh thay đổi từ bị chặn sang "thành công sau Xs",
với X là thời gian khóa được giữ. Số dư hiển thị mức tăng +1.00 áp dụng bởi UPDATE cạnh tranh.

Mức độ cô lập READ COMMITTED mặc định của Oracle đảm bảo rằng một tác vụ đọc đồng thời chỉ nhìn
thấy số dư đã commit cuối cùng, không thấy sự thay đổi chưa được commit do bên giữ khóa thực hiện.
Hành vi này cũng được kiểm chứng bởi test case
`test_lock_prevents_concurrent_read_write_isolation` trong bộ kiểm thử tự động.

### Kịch bản 3: Lỗi mạng / Giao dịch In-Doubt

Minh họa điều xảy ra khi Node B không thể truy cập được trong giai đoạn commit của 2PC.

**Lưu ý về hành vi dự kiến**: Cửa sổ thời gian 2PC giữa lúc hoàn thành Giai đoạn 1 và phân phối
Giai đoạn 2 chỉ dưới mức mili-giây trong môi trường Docker đơn máy chủ. Ngắt kết nối mạng có thể
xảy ra trước khi Giai đoạn 1 hoàn thành, khi đó Oracle sẽ tự động Rollback (do callTimeout) và
`DBA_2PC_PENDING` vẫn trống. Hãy chạy mô phỏng vài lần; cuối cùng ngắt kết nối sẽ xảy ra đúng
thời điểm Oracle đã commit cục bộ nhưng không thể gửi tín hiệu COMMIT đến Node B, tạo ra trạng
thái in-doubt.

Các bước:

1. Điều hướng đến "Kịch bản 3: Lỗi mạng / Giao dịch In-Doubt".
2. Chọn tài khoản ghi nợ (Node A) và tài khoản nhận tiền (Node B).
3. Nhập một số tiền chuyển nhỏ, ví dụ 200.
4. Nhấp nút "Giả lập lỗi mạng trong lúc Commit (Simulate Network Failure)".

Diễn biến nội bộ:

- Ứng dụng chạy một giao tác phân tán (UPDATE cục bộ trên Node A, UPDATE từ xa trên Node B qua DB
  link), sau đó ngắt kết nối Node B khỏi mạng bridge của Docker bằng Docker SDK ngay trước khi gọi
  `conn.commit()`.
- Oracle nỗ lực thực hiện 2PC. Nếu Giai đoạn 1 (nhận PREPARE READY từ Node B) hoàn thành trước
  khi mạng sập và Oracle ghi bản ghi commit redo, giao tác sẽ rơi vào trạng thái in-doubt: đã
  commit trên Coordinator nhưng chưa được xác nhận trên Participant.
- Node B ngay lập tức được kết nối lại sau nỗ lực commit.
- Bảng `DBA_2PC_PENDING` trên Node A được truy vấn để hiển thị bất kỳ giao tác in-doubt nào.

Nếu một giao tác in-doubt xuất hiện:

5. Bảng "DBA_2PC_PENDING - Giao dịch In-Doubt" hiển thị với `local_tran_id` và trạng thái.
6. Chọn giao tác từ menu thả xuống.
7. Nhấp nút "Thực hiện COMMIT FORCE" để áp dụng quyết định đã commit của Coordinator, hoặc nhấp
   nút "Thực hiện ROLLBACK FORCE" để hoàn tác giao tác trên Node A (Node B chưa bao giờ được
   commit, do đó không cần thêm thao tác ở đó).
8. Nhấp nút "Làm mới DBA_2PC_PENDING" để xác nhận mục nhập đã bị xóa.

Nếu bảng trống sau khi mô phỏng:

- Oracle đã Rollback hoàn toàn trước khi ghi bản ghi commit redo.
- Nhấp lại nút mô phỏng; kết quả định thời (timing) sẽ khác nhau giữa các lần chạy.

Ghi chú về quyền khôi phục: `app_user` giữ quyền `FORCE ANY TRANSACTION` (được cấp trong
`scripts/00_grants_a.sh`), cho phép thực thi COMMIT FORCE và ROLLBACK FORCE mà không yêu cầu kết
nối SYSDBA hay SYSTEM.

## Kiểm thử

Bộ kiểm thử tự động xác minh hành vi được minh họa trong cả ba kịch bản. Chạy bên trong container
`streamlit_app`, nơi đã có sẵn cả hai Oracle node như là các hostname có thể kết nối:

```bash
docker exec streamlit_app python -m pytest src/tests/ -v
```

Đầu ra dự kiến (khoảng 4-5 giây):

```text
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

Các test của Kịch bản 3 tập trung kiểm chứng kiểm soát truy cập (access control) thay vì tạo
toàn bộ vòng đời giao tác treo. Chế độ dedicated-server của Oracle làm cho tất cả DB link
không thể di chuyển (non-migratable) trong ngữ cảnh XA/TPC (ORA-24777), và các giao tác TPC
chỉ-cục-bộ bị từ chối với ORA-24771. Do đó các test xác nhận rằng `app_user` giữ quyền
`SELECT ON SYS.DBA_2PC_PENDING` và `FORCE ANY TRANSACTION`, đây là hai quyền mà giao diện khôi
phục của Kịch bản 3 phụ thuộc vào. Quá trình tạo và xử lý giao tác in-doubt hoàn chỉnh được
thực hiện qua giao diện Streamlit.

## Khắc phục sự cố

**Oracle mất hơn 5 phút để khởi tạo**

Kiểm tra bộ nhớ khả dụng và Disk I/O:

```bash
free -h
docker stats --no-stream
```

Image slim-faststart dựng sẵn cơ sở dữ liệu, vì vậy việc khởi động sẽ hoàn tất trong 2-3 phút
trên phần cứng có 8 GB RAM trống và ổ cứng SSD. Trên phần cứng chậm hơn hoặc tải nặng, hãy tăng
giá trị `start_period` trong phần healthcheck của `docker-compose.yml`.

**Script khởi tạo thất bại (log Node A hoặc Node B báo exit code 7)**

Exit code 7 là mã lỗi Oracle 1031 (ORA-01031: insufficient privileges) modulo 256. Lỗi này thường
xảy ra khi script init chạy trên phiên CDB root thay vì PDB `FREEPDB1`. Hãy xác minh chuỗi kết
nối SYSDBA trỏ rõ ràng tới `//localhost:1521/FREEPDB1`. Xóa volumes và khởi động lại:

```bash
docker compose down -v
docker compose up -d
```

**Kiểm tra DB link trả về lỗi ORA-12541 hoặc ORA-12154**

Các lỗi này cho thấy Node A không thể phân giải hostname `node_b` qua bridge của Docker. Xác nhận
cả hai container đều nằm trên cùng một mạng:

```bash
docker network inspect oracle-2pc-simulator_oracle_net
```

Cả `oracle_node_a` và `oracle_node_b` đều phải xuất hiện trong phần `Containers`. Nếu thiếu một
trong hai, hãy tắt và khởi động lại stack:

```bash
docker compose down
docker compose up -d
```

**DBA_2PC_PENDING luôn trống trong Kịch bản 3**

Giai đoạn 2PC commit và việc ngắt kết nối mạng chạy đua với nhau. Nếu mạng sập trước khi Giai
đoạn 1 hoàn tất (nhận PREPARE READY từ Node B), Oracle sẽ Rollback sạch sẽ và không tạo ra mục
DBA_2PC_PENDING nào. Hãy chạy lại mô phỏng; kết quả định thời sẽ khác nhau. Nếu không bao giờ
tạo ra giao tác in-doubt sau nhiều lần thử, hãy kiểm tra xem Docker SDK có đang ngắt kết nối
Node B thành công không:

```bash
docker network inspect oracle-2pc-simulator_oracle_net
```

Nếu `oracle_node_b` vẫn còn trong danh sách sau khi nhấp nút, việc ngắt kết nối chưa có hiệu
lực. Xác nhận container streamlit đang chạy dưới quyền root và Docker socket được mount đúng cách:

```bash
docker inspect streamlit_app | grep -A2 '"User"'
docker inspect streamlit_app | grep docker.sock
```

**Lỗi phân quyền Docker socket trong Kịch bản 3**

Dịch vụ streamlit được cấu hình với `user: root` trong `docker-compose.yml` để đảm bảo nó có thể
đọc `/var/run/docker.sock`. Nếu lỗi cấp phép vẫn tiếp diễn, hãy kiểm tra quyền sở hữu socket
trên máy chủ:

```bash
ls -la /var/run/docker.sock
```

Trên Linux, socket thường thuộc sở hữu của `root:docker`. Chạy container dưới quyền root giúp bỏ
qua yêu cầu làm thành viên của nhóm docker.

**Streamlit báo "ModuleNotFoundError: No module named 'src'"**

Script runner của Streamlit thay thế mục rỗng trong `sys.path` (trỏ đến thư mục làm việc `/app`)
bằng thư mục của script (`/app/src`), làm mất `/app` khỏi đường dẫn tìm kiếm module. Biến môi
trường `PYTHONPATH=/app` trong Dockerfile khắc phục điều này vĩnh viễn. Nếu lỗi vẫn xuất hiện
sau khi cập nhật code, hãy rebuild và khởi động lại image:

```bash
docker compose build streamlit
docker compose up -d --no-deps streamlit
```

**Lần chạy kiểm thử trước để lại các giao tác in-doubt**

Nếu `reset_balances` thất bại với ORA-01591 ("transaction branch was already committed"), một bài
test trước đó đã để lại giao tác in-doubt chưa giải quyết và đang giữ row lock. Fixture
`reset_seed_data` gọi hàm `_force_recover_all_pending()` để xử lý tự động. Nếu sự cố vẫn tiếp
diễn bên ngoài bộ kiểm thử, hãy giải quyết thủ công:

```bash
docker exec oracle_node_a bash -c \
  "sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< 'SELECT local_tran_id FROM dba_2pc_pending;'"
```

Sau đó với mỗi ID được trả về:

```bash
docker exec oracle_node_a bash -c \
  "sqlplus -S app_user/AppPass1@//localhost:1521/FREEPDB1 \
  <<< \"ROLLBACK FORCE '<local_tran_id>';\""
```
