#!/bin/bash
# Node A initialisation script.
#
# Executed by the gvenzl/oracle-free entrypoint on the first container start
# (when the oradata volume is empty).  The gvenzl image runs files placed in
# /docker-entrypoint-initdb.d/ in lexicographic order; the "00_" prefix
# ensures this script runs before any application SQL scripts.
#
# Why two sqlplus sessions:
#   Oracle 23c Free disallows CREATE PUBLIC DATABASE LINK even for SYS/SYSDBA
#   within a PDB context (ORA-01031).  A private database link created by
#   app_user is functionally equivalent for this simulator and avoids the
#   restriction.  SYSDBA cannot create the link directly, so the work is split:
#     Session 1 (SYSDBA): elevate-privilege operations (GRANT, DDL, seed data).
#     Session 2 (app_user): CREATE DATABASE LINK (private, owned by app_user).
#
# The database link creation does not attempt a connection to node_b at this
# point; it only stores the connection descriptor.  Node B may still be
# initialising when this script runs, and that is not a problem.

set -e

ORACLE_PWD="${ORACLE_PASSWORD:-OraclePass1}"
APP="${APP_USER:-app_user}"
APP_PWD="${APP_USER_PASSWORD:-AppPass1}"

# Session 1: SYSDBA grants and schema setup.
# ALTER SESSION SET CURRENT_SCHEMA directs all DDL issued in this session to
# app_user's schema without needing to qualify every object name.
sqlplus -S "sys/${ORACLE_PWD}@//localhost:1521/FREEPDB1 as sysdba" <<EOF
WHENEVER SQLERROR EXIT SQL.SQLCODE

-- Privilege to create a private database link in app_user's own schema.
GRANT CREATE DATABASE LINK TO ${APP};

-- Privileges required for Scenario 3: viewing and recovering in-doubt
-- distributed transactions from DBA_2PC_PENDING without SYSDBA access.
GRANT SELECT ON SYS.DBA_2PC_PENDING TO ${APP};
GRANT SELECT ON SYS.DBA_2PC_NEIGHBORS TO ${APP};
GRANT FORCE ANY TRANSACTION TO ${APP};

-- Redirect DDL to app_user's schema so the table and constraint are owned
-- by app_user and accessible with the application credentials.
ALTER SESSION SET CURRENT_SCHEMA = ${APP};

CREATE TABLE account (
    id      NUMBER PRIMARY KEY,
    name    VARCHAR2(50)  NOT NULL,
    balance NUMBER(15, 2) NOT NULL,
    CONSTRAINT chk_balance_a CHECK (balance >= 0)
);

INSERT INTO account VALUES (1, 'Alice',   10000);
INSERT INTO account VALUES (2, 'Charlie',  5000);
COMMIT;

EXIT;
EOF

# Session 2: create the private database link as app_user.
# The link uses EZConnect syntax so no tnsnames.ora is required.
# CONNECT TO specifies fixed credentials, making the link independent of the
# session user that opens it (required behaviour for distributed transactions).
sqlplus -S "${APP}/${APP_PWD}@//localhost:1521/FREEPDB1" <<EOF
WHENEVER SQLERROR EXIT SQL.SQLCODE

CREATE DATABASE LINK node_b_link
    CONNECT TO ${APP} IDENTIFIED BY ${APP_PWD}
    USING '//node_b:1521/FREEPDB1';

EXIT;
EOF

echo "Node A init complete."
