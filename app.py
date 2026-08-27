import os
import datetime as dt
from flask import Flask, jsonify, render_template, request

from database import init_db, get_conn, upsert_manual_term
from sync import run_sync, is_subscription_product

app = Flask(__name__)
init_db()

DASH_TOKEN = os.environ.get("DASHBOARD_ACCESS_TOKEN")  # senha simples opcional
DIA_MS = 24 * 60 * 60 * 1000


def check_auth():
    if not DASH_TOKEN:
        return True
    return request.args.get("token") == DASH_TOKEN or request.headers.get("X-Dashboard-Token") == DASH_TOKEN


@app.before_request
def guard():
    if request.path.startswith("/api") or request.path == "/":
        if not check_auth():
            return jsonify({"error": "acesso negado, token inválido"}), 401


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/sync", methods=["POST"])
def trigger_sync():
    try:
        run_sync()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/metrics")
def metrics():
    conn = get_conn()

    faturamento_total = conn.execute(
        "SELECT COALESCE(SUM(payment_value),0) AS total FROM sales WHERE status IN ('APPROVED','COMPLETE')"
    ).fetchone()["total"]

    faturamento_mensal = conn.execute(
        """
        SELECT strftime('%Y-%m', datetime(purchase_date/1000, 'unixepoch')) AS mes,
               SUM(payment_value) AS total
        FROM sales
        WHERE status IN ('APPROVED','COMPLETE') AND purchase_date IS NOT NULL
        GROUP BY mes ORDER BY mes DESC LIMIT 12
        """
    ).fetchall()

    ativos = conn.execute(
        "SELECT COUNT(*) AS n FROM subscriptions WHERE status = 'ACTIVE'"
    ).fetchone()["n"]

    cancelados = conn.execute(
        """SELECT COUNT(*) AS n FROM subscriptions
           WHERE status IN ('CANCELLED_BY_CUSTOMER','CANCELLED_BY_ADMIN','CANCELLED_BY_SELLER')"""
    ).fetchone()["n"]

    atrasados = conn.execute(
        "SELECT COUNT(*) AS n FROM subscriptions WHERE status = 'OVERDUE'"
    ).fetchone()["n"]

    entradas_mensal = conn.execute(
        """
        SELECT strftime('%Y-%m', datetime(accession_date/1000, 'unixepoch')) AS mes,
               COUNT(*) AS n
        FROM subscriptions
        WHERE accession_date IS NOT NULL
        GROUP BY mes ORDER BY mes DESC LIMIT 12
        """
    ).fetchall()

    todos = conn.execute(
        """SELECT subscriber_name, subscriber_email, product_name, plan_name, status,
                  recurrency_period_days, date_next_charge
           FROM subscriptions WHERE status IN ('ACTIVE','OVERDUE')"""
    ).fetchall()

    recorrencia = []
    for row in todos:
        item = dict(row)
        if row["date_next_charge"]:
            item["proxima_cobranca"] = dt.datetime.utcfromtimestamp(
                row["date_next_charge"] / 1000
            ).strftime("%d/%m/%Y")
        else:
            item["proxima_cobranca"] = None
        recorrencia.append(item)

    conn.close()

    return jsonify(
        {
            "faturamento_total": faturamento_total,
            "faturamento_mensal": [dict(r) for r in reversed(faturamento_mensal)],
            "assinantes_ativos": ativos,
            "assinantes_cancelados": cancelados,
            "assinantes_atrasados": atrasados,
            "entradas_mensal": [dict(r) for r in reversed(entradas_mensal)],
            "recorrencia": recorrencia,
        }
    )


@app.route("/api/one-time-sales")
def one_time_sales():
    """Vendas de pagamento único (produto CMD) com vigência controlada manualmente."""
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.transaction_id, s.buyer_name, s.buyer_email, s.product_name,
               s.purchase_date, s.payment_value, m.term_months
        FROM sales s
        LEFT JOIN manual_terms m ON m.transaction_id = s.transaction_id
        WHERE s.status IN ('APPROVED','COMPLETE')
        ORDER BY s.purchase_date DESC
        """
    ).fetchall()
    conn.close()

    now_ms = int(dt.datetime.utcnow().timestamp() * 1000)
    result = []
    for r in rows:
        row = dict(r)
        if is_subscription_product(row["product_name"]):
            continue  # essa é a assinatura recorrente, já aparece em outra tabela

        row["data_compra"] = (
            dt.datetime.utcfromtimestamp(row["purchase_date"] / 1000).strftime("%d/%m/%Y")
            if row["purchase_date"] else None
        )

        if row["purchase_date"] and row["term_months"]:
            due_ms = row["purchase_date"] + row["term_months"] * 30 * DIA_MS
            row["vencimento"] = dt.datetime.utcfromtimestamp(due_ms / 1000).strftime("%d/%m/%Y")
            dias_restantes = (due_ms - now_ms) / DIA_MS
            if dias_restantes < 0:
                row["status_vigencia"] = "vencido"
            elif dias_restantes <= 15:
                row["status_vigencia"] = "vencendo"
            else:
                row["status_vigencia"] = "em_dia"
        else:
            row["vencimento"] = None
            row["status_vigencia"] = "sem_info"

        result.append(row)

    return jsonify(result)


@app.route("/api/manual-term", methods=["POST"])
def set_manual_term():
    data = request.get_json(force=True, silent=True) or {}
    transaction_id = data.get("transaction_id")
    term_months = data.get("term_months")
    if not transaction_id or term_months not in (6, 12):
        return jsonify({"ok": False, "error": "dados inválidos"}), 400
    upsert_manual_term(transaction_id, term_months, dt.datetime.utcnow().isoformat())
    return jsonify({"ok": True})


@app.route("/api/sync-log")
def sync_log():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
