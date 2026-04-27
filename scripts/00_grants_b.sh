#!/bin/bash
# Node B initialisation script.
#
# Executed by the gvenzl/oracle-free entrypoint on the first container start.
# Node B acts as a participant (remote site) in distributed transactions
# coordinated by Node A.  It requires no database link of its own.
#
# A single SYSDBA session is sufficient here because there is no private
# database link to create; all operations can be performed with elevated
# privileges without the two-session split required on Node A.

set -e

ORACLE_PWD="${ORACLE_PASSWORD:-OraclePass1}"
APP="${APP_USER:-app_user}"

# SYSDBA session: grants, schema setup, and seed data.
# The same DBA_2PC_PENDING and FORCE ANY TRANSACTION grants are applied here
# so that the Python application can query and recover in-doubt transactions
# from either node's perspective if needed.
sqlplus -S "sys/${ORACLE_PWD}@//localhost:1521/FREEPDB1 as sysdba" <<EOF
WHENEVER SQLERROR EXIT SQL.SQLCODE

GRANT SELECT ON SYS.DBA_2PC_PENDING TO ${APP};
GRANT SELECT ON SYS.DBA_2PC_NEIGHBORS TO ${APP};
GRANT FORCE ANY TRANSACTION TO ${APP};

ALTER SESSION SET CURRENT_SCHEMA = ${APP};

CREATE TABLE account (
    id      NUMBER PRIMARY KEY,
    name    VARCHAR2(50)  NOT NULL,
    balance NUMBER(15, 2) NOT NULL,
    CONSTRAINT chk_balance_b CHECK (balance >= 0)
);

INSERT INTO account VALUES (1, 'Bob',    8000);
INSERT INTO account VALUES (2, 'Diana',  3000);
COMMIT;

EXIT;
EOF

echo "Node B init complete."
