import os
import datetime as dt
from flask import Flask, jsonify, render_template, request

from database import init_db, get_conn
from sync import run_sync, is_semestral

app = Flask(__name__)
init_db()

DASH_TOKEN = os.environ.get("DASHBOARD_ACCESS_TOKEN")  # senha simples opcional


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

    # --- Faturamento total e por mês (vendas aprovadas) ---
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

    # --- Recorrência ativa ---
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

    # --- Entradas por mês (novas assinaturas, pela accession_date) ---
    entradas_mensal = conn.execute(
        """
        SELECT strftime('%Y-%m', datetime(accession_date/1000, 'unixepoch')) AS mes,
               COUNT(*) AS n
        FROM subscriptions
        WHERE accession_date IS NOT NULL
        GROUP BY mes ORDER BY mes DESC LIMIT 12
        """
    ).fetchall()

    # --- Assinantes ativos (lista para tabela) ---
    todos = conn.execute(
        """SELECT subscriber_name, subscriber_email, product_name, plan_name, status,
                  recurrency_period_days, date_next_charge
           FROM subscriptions WHERE status IN ('ACTIVE','OVERDUE')"""
    ).fetchall()

    recorrencia = []
    semestrais = []
    for row in todos:
        item = dict(row)
        item["is_semestral"] = is_semestral(row["plan_name"], row["recurrency_period_days"])
        if row["date_next_charge"]:
            item["proxima_cobranca"] = dt.datetime.utcfromtimestamp(
                row["date_next_charge"] / 1000
            ).strftime("%d/%m/%Y")
        else:
            item["proxima_cobranca"] = None
        recorrencia.append(item)
        if item["is_semestral"]:
            semestrais.append(item)

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
            "semestrais": semestrais,
        }
    )

@app.route("/api/debug-fields")
def debug_fields():
    import json as _json
    conn = get_conn()
    sale = conn.execute("SELECT raw_json FROM sales LIMIT 1").fetchone()
    sub = conn.execute("SELECT raw_json FROM subscriptions LIMIT 1").fetchone()
    conn.close()
    result = {}
    if sale:
        s = _json.loads(sale["raw_json"])
        p = s.get("purchase", {})
        result["sale_date_values"] = {
            "order_date": p.get("order_date"),
            "approved_date": p.get("approved_date"),
        }
    if sub:
        d = _json.loads(sub["raw_json"])
        result["subscription_date_values"] = {
            "accession_date": d.get("accession_date"),
            "request_date": d.get("request_date"),
        }
    return jsonify(result)
@app.route("/api/sync-log")
def sync_log():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
