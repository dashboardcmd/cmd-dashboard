import os
import datetime as dt
from flask import Flask, jsonify, render_template, request

from database import (
    init_db, get_conn, upsert_manual_term, update_sale_value,
    get_setting, set_setting, add_cost_item, update_cost_item, delete_cost_item,
)
from sync import run_sync, is_subscription_product

app = Flask(__name__)
init_db()

DASH_TOKEN = os.environ.get("DASHBOARD_ACCESS_TOKEN")
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


def _date_to_ms(date_str, end_of_day=False):
    if not date_str:
        return None
    try:
        d = dt.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    if end_of_day:
        d = d + dt.timedelta(days=1) - dt.timedelta(milliseconds=1)
    return int(d.timestamp() * 1000)


def _get_date_range():
    start_ms = _date_to_ms(request.args.get("start_date"))
    end_ms = _date_to_ms(request.args.get("end_date"), end_of_day=True)
    return start_ms, end_ms


def _current_month_revenue(conn):
    now = dt.datetime.utcnow()
    inicio_mes = dt.datetime(now.year, now.month, 1)
    fim_mes = dt.datetime(now.year + 1, 1, 1) if now.month == 12 else dt.datetime(now.year, now.month + 1, 1)
    inicio_ms = int(inicio_mes.timestamp() * 1000)
    fim_ms = int(fim_mes.timestamp() * 1000)
    total = conn.execute(
        """SELECT COALESCE(SUM(payment_value),0) AS total FROM sales
           WHERE status IN ('APPROVED','COMPLETE') AND purchase_date >= ? AND purchase_date < ?""",
        (inicio_ms, fim_ms),
    ).fetchone()["total"]
    return total, now.strftime("%Y-%m")


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
    start_ms, end_ms = _get_date_range()
    conn = get_conn()

    sale_where = ["status IN ('APPROVED','COMPLETE')"]
    sale_params = []
    if start_ms is not None:
        sale_where.append("purchase_date >= ?")
        sale_params.append(start_ms)
    if end_ms is not None:
        sale_where.append("purchase_date <= ?")
        sale_params.append(end_ms)
    sale_where_sql = " AND ".join(sale_where)

    faturamento_total = conn.execute(
        f"SELECT COALESCE(SUM(payment_value),0) AS total FROM sales WHERE {sale_where_sql}",
        sale_params,
    ).fetchone()["total"]

    faturamento_mensal = conn.execute(
        f"""
        SELECT strftime('%Y-%m', datetime(purchase_date/1000, 'unixepoch')) AS mes,
               SUM(payment_value) AS total
        FROM sales
        WHERE {sale_where_sql} AND purchase_date IS NOT NULL
        GROUP BY mes ORDER BY mes DESC LIMIT 12
        """,
        sale_params,
    ).fetchall()
    faturamento_mensal = [dict(r) for r in reversed(faturamento_mensal)]

    variacao_pct = None
    if len(faturamento_mensal) >= 2:
        atual = faturamento_mensal[-1]["total"] or 0
        anterior = faturamento_mensal[-2]["total"] or 0
        if anterior > 0:
            variacao_pct = round(((atual - anterior) / anterior) * 100, 1)

    faturamento_mes_atual, mes_atual_str = _current_month_revenue(conn)

    meta_raw = get_setting("meta_mensal")
    meta_mensal = float(meta_raw) if meta_raw else None
    meta_progresso_pct = None
    if meta_mensal and meta_mensal > 0:
        meta_progresso_pct = round((faturamento_mes_atual / meta_mensal) * 100, 1)

    sub_where = []
    sub_params = []
    if start_ms is not None:
        sub_where.append("accession_date >= ?")
        sub_params.append(start_ms)
    if end_ms is not None:
        sub_where.append("accession_date <= ?")
        sub_params.append(end_ms)
    sub_extra = (" AND " + " AND ".join(sub_where)) if sub_where else ""

    ativos = conn.execute(
        f"SELECT COUNT(*) AS n FROM subscriptions WHERE status = 'ACTIVE'{sub_extra}",
        sub_params,
    ).fetchone()["n"]

    cancelados = conn.execute(
        f"""SELECT COUNT(*) AS n FROM subscriptions
           WHERE status IN ('CANCELLED_BY_CUSTOMER','CANCELLED_BY_ADMIN','CANCELLED_BY_SELLER'){sub_extra}""",
        sub_params,
    ).fetchone()["n"]

    atrasados = conn.execute(
        f"SELECT COUNT(*) AS n FROM subscriptions WHERE status = 'OVERDUE'{sub_extra}",
        sub_params,
    ).fetchone()["n"]

    entradas_mensal = conn.execute(
        f"""
        SELECT strftime('%Y-%m', datetime(accession_date/1000, 'unixepoch')) AS mes,
               COUNT(*) AS n
        FROM subscriptions
        WHERE accession_date IS NOT NULL{sub_extra}
        GROUP BY mes ORDER BY mes DESC LIMIT 12
        """,
        sub_params,
    ).fetchall()

    churn_where = []
    churn_params = []
    if start_ms is not None:
        churn_where.append("cancelled_at >= ?")
        churn_params.append(dt.datetime.utcfromtimestamp(start_ms / 1000).isoformat())
    if end_ms is not None:
        churn_where.append("cancelled_at <= ?")
        churn_params.append(dt.datetime.utcfromtimestamp(end_ms / 1000).isoformat())
    churn_extra = (" WHERE " + " AND ".join(churn_where)) if churn_where else ""

    cancelamentos_mensal = conn.execute(
        f"""
        SELECT strftime('%Y-%m', cancelled_at) AS mes, COUNT(*) AS n
        FROM cancellation_events
        {churn_extra}
        GROUP BY mes ORDER BY mes DESC LIMIT 12
        """,
        churn_params,
    ).fetchall()

    recorrencia_where = "status IN ('ACTIVE','OVERDUE')" + sub_extra
    todos = conn.execute(
        f"""SELECT subscriber_name, subscriber_email, product_name, plan_name, status,
                  recurrency_period_days, date_next_charge
           FROM subscriptions WHERE {recorrencia_where}""",
        sub_params,
    ).fetchall()

    now_ms = int(dt.datetime.utcnow().timestamp() * 1000)
    recorrencia = []
    for row in todos:
        item = dict(row)
        if row["date_next_charge"]:
            item["proxima_cobranca"] = dt.datetime.utcfromtimestamp(
                row["date_next_charge"] / 1000
            ).strftime("%d/%m/%Y")
            dias_restantes = (row["date_next_charge"] - now_ms) / DIA_MS
            item["vence_em_breve"] = 0 <= dias_restantes <= 7
        else:
            item["proxima_cobranca"] = None
            item["vence_em_breve"] = False
        recorrencia.append(item)

    conn.close()

    return jsonify(
        {
            "faturamento_total": faturamento_total,
            "faturamento_mensal": faturamento_mensal,
            "faturamento_variacao_pct": variacao_pct,
            "faturamento_mes_atual": faturamento_mes_atual,
            "mes_atual": mes_atual_str,
            "meta_mensal": meta_mensal,
            "meta_progresso_pct": meta_progresso_pct,
            "assinantes_ativos": ativos,
            "assinantes_cancelados": cancelados,
            "assinantes_atrasados": atrasados,
            "entradas_mensal": [dict(r) for r in reversed(entradas_mensal)],
            "cancelamentos_mensal": [dict(r) for r in reversed(cancelamentos_mensal)],
            "recorrencia": recorrencia,
        }
    )


@app.route("/api/goal", methods=["POST"])
def set_goal():
    data = request.get_json(force=True, silent=True) or {}
    value = data.get("meta_mensal")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "valor inválido"}), 400
    if value < 0:
        return jsonify({"ok": False, "error": "valor inválido"}), 400
    set_setting("meta_mensal", str(value))
    return jsonify({"ok": True})


@app.route("/api/one-time-sales")
def one_time_sales():
    start_ms, end_ms = _get_date_range()
    conn = get_conn()

    where = ["s.status IN ('APPROVED','COMPLETE')"]
    params = []
    if start_ms is not None:
        where.append("s.purchase_date >= ?")
        params.append(start_ms)
    if end_ms is not None:
        where.append("s.purchase_date <= ?")
        params.append(end_ms)
    where_sql = " AND ".join(where)

    rows = conn.execute(
        f"""
        SELECT s.transaction_id, s.buyer_name, s.buyer_email, s.product_name,
               s.purchase_date, s.payment_value, s.payment_value_edited, m.term_months
        FROM sales s
        LEFT JOIN manual_terms m ON m.transaction_id = s.transaction_id
        WHERE {where_sql}
        ORDER BY s.purchase_date DESC
        """,
        params,
    ).fetchall()
    conn.close()

    now_ms = int(dt.datetime.utcnow().timestamp() * 1000)
    result = []
    for r in rows:
        row = dict(r)
        if is_subscription_product(row["product_name"]):
            continue

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
            row["vence_em_breve"] = 0 <= dias_restantes <= 7
        else:
            row["vencimento"] = None
            row["status_vigencia"] = "sem_info"
            row["vence_em_breve"] = False

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


@app.route("/api/sale-value", methods=["POST"])
def set_sale_value():
    data = request.get_json(force=True, silent=True) or {}
    transaction_id = data.get("transaction_id")
    value = data.get("payment_value")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "valor inválido"}), 400
    if not transaction_id or value < 0:
        return jsonify({"ok": False, "error": "dados inválidos"}), 400
    update_sale_value(transaction_id, value)
    return jsonify({"ok": True})


@app.route("/api/costs")
def get_costs():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, monthly_value, contract_months, payment_info FROM cost_items ORDER BY sort_order ASC"
    ).fetchall()
    items = [dict(r) for r in rows]

    custo_mensal_total = sum(i["monthly_value"] or 0 for i in items)
    custo_anual_total = sum((i["monthly_value"] or 0) * (i["contract_months"] or 12) for i in items)

    imposto_pct_raw = get_setting("imposto_pct", "10")
    imposto_pct = float(imposto_pct_raw)

    faturamento_mes_atual, mes_atual_str = _current_month_revenue(conn)
    conn.close()

    imposto_mensal = faturamento_mes_atual * (imposto_pct / 100)
    dnb_mensal = faturamento_mes_atual - custo_mensal_total - imposto_mensal
    dnb_anual = dnb_mensal * 12

    return jsonify({
        "items": items,
        "imposto_pct": imposto_pct,
        "custo_mensal_total": custo_mensal_total,
        "custo_anual_total": custo_anual_total,
        "faturamento_mes_atual": faturamento_mes_atual,
        "mes_atual": mes_atual_str,
        "imposto_mensal": imposto_mensal,
        "dnb_mensal": dnb_mensal,
        "dnb_anual": dnb_anual,
    })


@app.route("/api/cost-item", methods=["POST"])
def create_cost_item():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "nome obrigatório"}), 400
    try:
        monthly_value = float(data.get("monthly_value") or 0)
        contract_months = int(data.get("contract_months") or 12)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "valores inválidos"}), 400
    payment_info = (data.get("payment_info") or "").strip()
    new_id = add_cost_item(name, monthly_value, contract_months, payment_info)
    return jsonify({"ok": True, "id": new_id})


@app.route("/api/cost-item/<int:item_id>", methods=["POST"])
def edit_cost_item(item_id):
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    try:
        monthly_value = float(data.get("monthly_value") or 0)
        contract_months = int(data.get("contract_months") or 12)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "valores inválidos"}), 400
    payment_info = (data.get("payment_info") or "").strip()
    update_cost_item(item_id, name, monthly_value, contract_months, payment_info)
    return jsonify({"ok": True})


@app.route("/api/cost-item/<int:item_id>/delete", methods=["POST"])
def remove_cost_item(item_id):
    delete_cost_item(item_id)
    return jsonify({"ok": True})


@app.route("/api/tax-rate", methods=["POST"])
def set_tax_rate():
    data = request.get_json(force=True, silent=True) or {}
    try:
        value = float(data.get("imposto_pct"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "valor inválido"}), 400
    if value < 0 or value > 100:
        return jsonify({"ok": False, "error": "valor inválido"}), 400
    set_setting("imposto_pct", str(value))
    return jsonify({"ok": True})


@app.route("/api/sync-log")
def sync_log():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
