"""
Puxa dados da API do Hotmart e grava no banco local (SQLite).

Rodar manualmente:   python sync.py
Rodar agendado:      configurar um Cron Job (ver README.md) chamando este script
                      1x por dia (ex.: todo dia às 6h da manhã).
"""
import json
import datetime as dt

from hotmart_client import HotmartClient
from database import init_db, upsert_sale, upsert_subscription, log_sync

# Plano é considerado "semestral" se o nome do plano contiver uma destas palavras
# OU se o período de recorrência estiver entre 170 e 200 dias.
SEMESTRAL_HINTS = ["semestral", "semestre", "6 meses", "6x"]


def is_semestral(plan_name, recurrency_days):
    plan_name = (plan_name or "").lower()
    if any(hint in plan_name for hint in SEMESTRAL_HINTS):
        return True
    if recurrency_days and 170 <= recurrency_days <= 200:
        return True
    return False


def sync_sales(client):
    count = 0
    for item in client.iter_sales_history():
        purchase = item.get("purchase", {})
        buyer = item.get("buyer", {})
        product = item.get("product", {})
        price = purchase.get("price", {})

        row = {
            "transaction_id": purchase.get("transaction"),
            "buyer_name": buyer.get("name"),
            "buyer_email": buyer.get("email"),
            "product_name": product.get("name"),
            "status": purchase.get("status"),
            "payment_value": price.get("value"),
            "currency": price.get("currency_value"),
            "purchase_date": purchase.get("order_date") or purchase.get("approved_date"),
            "raw_json": json.dumps(item, ensure_ascii=False),
        }
        if row["transaction_id"]:
            upsert_sale(row)
            count += 1
    return count


def sync_subscriptions(client):
    count = 0
    now_iso = dt.datetime.utcnow().isoformat()
    for item in client.iter_subscriptions():
        subscriber = item.get("subscriber", {})
        product = item.get("product", {})
        plan = item.get("plan", {})
        recurrency_days = plan.get("recurrency_period")

        row = {
            "subscriber_code": item.get("subscriber_code") or subscriber.get("code"),
            "subscriber_name": subscriber.get("name"),
            "subscriber_email": subscriber.get("email"),
            "product_name": product.get("name"),
            "plan_name": plan.get("name"),
            "status": item.get("status"),
            "recurrency_period_days": recurrency_days,
            "accession_date": item.get("accession_date"),
            "date_next_charge": item.get("date_next_charge"),
            "last_seen_sync": now_iso,
            "raw_json": json.dumps(item, ensure_ascii=False),
        }
        if row["subscriber_code"]:
            upsert_subscription(row)
            count += 1
    return count


def run_sync():
    init_db()
    client = HotmartClient()
    started_at = dt.datetime.utcnow().isoformat()
    try:
        sales_count = sync_sales(client)
        subs_count = sync_subscriptions(client)
        log_sync(started_at, dt.datetime.utcnow().isoformat(), sales_count, subs_count, "OK")
        print(f"Sync concluído: {sales_count} vendas, {subs_count} assinaturas.")
    except Exception as e:
        log_sync(started_at, dt.datetime.utcnow().isoformat(), 0, 0, "ERRO", str(e))
        print(f"Erro no sync: {e}")
        raise


if __name__ == "__main__":
    run_sync()
