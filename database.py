import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "dashboard.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sales (
            transaction_id TEXT PRIMARY KEY,
            buyer_name TEXT,
            buyer_email TEXT,
            product_name TEXT,
            status TEXT,
            payment_value REAL,
            payment_value_edited INTEGER DEFAULT 0,
            currency TEXT,
            purchase_date INTEGER,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            subscriber_code TEXT PRIMARY KEY,
            subscriber_name TEXT,
            subscriber_email TEXT,
            product_name TEXT,
            plan_name TEXT,
            status TEXT,
            recurrency_period_days INTEGER,
            accession_date INTEGER,
            date_next_charge INTEGER,
            last_seen_sync TEXT,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            sales_synced INTEGER,
            subscriptions_synced INTEGER,
            status TEXT,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS manual_terms (
            transaction_id TEXT PRIMARY KEY,
            term_months INTEGER,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS cancellation_events (
            subscriber_code TEXT PRIMARY KEY,
            cancelled_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        -- Custos fixos da agência (equipe, tráfego, etc.)
        CREATE TABLE IF NOT EXISTS cost_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            monthly_value REAL,
            contract_months INTEGER,
            payment_info TEXT,
            sort_order INTEGER
        );
        """
    )
    conn.commit()
    conn.close()


def upsert_sale(row):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO sales (transaction_id, buyer_name, buyer_email, product_name,
                            status, payment_value, currency, purchase_date, raw_json)
        VALUES (:transaction_id, :buyer_name, :buyer_email, :product_name,
                :status, :payment_value, :currency, :purchase_date, :raw_json)
        ON CONFLICT(transaction_id) DO UPDATE SET
            status=excluded.status,
            payment_value=CASE WHEN sales.payment_value_edited=1
                                THEN sales.payment_value
                                ELSE excluded.payment_value END,
            raw_json=excluded.raw_json
        """,
        row,
    )
    conn.commit()
    conn.close()


def upsert_subscription(row):
    conn = get_conn()

    CANCELLED = {"CANCELLED_BY_CUSTOMER", "CANCELLED_BY_ADMIN", "CANCELLED_BY_SELLER"}
    prev = conn.execute(
        "SELECT status FROM subscriptions WHERE subscriber_code = ?",
        (row["subscriber_code"],),
    ).fetchone()
    if prev and prev["status"] not in CANCELLED and row["status"] in CANCELLED:
        conn.execute(
            "INSERT OR IGNORE INTO cancellation_events (subscriber_code, cancelled_at) VALUES (?, ?)",
            (row["subscriber_code"], row["last_seen_sync"]),
        )

    conn.execute(
        """
        INSERT INTO subscriptions (subscriber_code, subscriber_name, subscriber_email,
                                    product_name, plan_name, status, recurrency_period_days,
                                    accession_date, date_next_charge, last_seen_sync, raw_json)
        VALUES (:subscriber_code, :subscriber_name, :subscriber_email, :product_name,
                :plan_name, :status, :recurrency_period_days, :accession_date,
                :date_next_charge, :last_seen_sync, :raw_json)
        ON CONFLICT(subscriber_code) DO UPDATE SET
            status=excluded.status,
            plan_name=excluded.plan_name,
            recurrency_period_days=excluded.recurrency_period_days,
            date_next_charge=excluded.date_next_charge,
            last_seen_sync=excluded.last_seen_sync,
            raw_json=excluded.raw_json
        """,
        row,
    )
    conn.commit()
    conn.close()


def log_sync(started_at, finished_at, sales_synced, subscriptions_synced, status, error=None):
    conn = get_conn()
    conn.execute(
        """INSERT INTO sync_log (started_at, finished_at, sales_synced, subscriptions_synced, status, error)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (started_at, finished_at, sales_synced, subscriptions_synced, status, error),
    )
    conn.commit()
    conn.close()


def upsert_manual_term(transaction_id, term_months, updated_at):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO manual_terms (transaction_id, term_months, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(transaction_id) DO UPDATE SET
            term_months=excluded.term_months,
            updated_at=excluded.updated_at
        """,
        (transaction_id, term_months, updated_at),
    )
    conn.commit()
    conn.close()


def update_sale_value(transaction_id, new_value):
    conn = get_conn()
    conn.execute(
        "UPDATE sales SET payment_value = ?, payment_value_edited = 1 WHERE transaction_id = ?",
        (new_value, transaction_id),
    )
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def add_cost_item(name, monthly_value, contract_months, payment_info):
    conn = get_conn()
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM cost_items").fetchone()["m"]
    cur = conn.execute(
        """INSERT INTO cost_items (name, monthly_value, contract_months, payment_info, sort_order)
           VALUES (?, ?, ?, ?, ?)""",
        (name, monthly_value, contract_months, payment_info, max_order + 1),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def update_cost_item(item_id, name, monthly_value, contract_months, payment_info):
    conn = get_conn()
    conn.execute(
        """UPDATE cost_items SET name=?, monthly_value=?, contract_months=?, payment_info=?
           WHERE id=?""",
        (name, monthly_value, contract_months, payment_info, item_id),
    )
    conn.commit()
    conn.close()


def delete_cost_item(item_id):
    conn = get_conn()
    conn.execute("DELETE FROM cost_items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
