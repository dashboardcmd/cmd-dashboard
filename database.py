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

        -- Controle manual de vigência para vendas de pagamento único
        -- (a Hotmart não sabe informar isso sozinha, pois não é assinatura).
        CREATE TABLE IF NOT EXISTS manual_terms (
            transaction_id TEXT PRIMARY KEY,
            term_months INTEGER,
            updated_at TEXT
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
            payment_value=excluded.payment_value,
            raw_json=excluded.raw_json
        """,
        row,
    )
    conn.commit()
    conn.close()


def upsert_subscription(row):
    conn = get_conn()
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
