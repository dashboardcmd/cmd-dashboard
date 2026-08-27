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

PRODUCT_FILTER = [
    "consultoria médico digital",
]


def is_subscription_product(name):
    return "assinatura" in (name or "").lower()


def _product_allowed(name):
    n = (name or "").strip().lower()
    return any(p in n for p in PRODUCT_FILTER)


def _first(*values):
    for v in values:
        if v:
            return v
    return None


def _numeric(field):
    """Alguns campos da Hotmart vêm como número puro, outros como
    {"value": ..., "currency_value": ...}. Essa função extrai o número
    de qualquer um dos dois formatos."""
    if isinstance(field, dict):
        return field.get("value")
    return field


def sync_sales(client):
    count = 0
    for item in client.iter_sales_history():
        purchase = item.get("purchase", {}) or {}
        buyer = item.get("buyer", {}) or {}
        product = item.get("product", {}) or {}
        price = purchase.get("price", {}) or {}

        product_name = product.get("name")
        if not _product_allowed(product_name):
            continue

        purchase_date = _first(
            purchase.get("order_date"),
            purchase.get("approved_date"),
            purchase.get("date"),
            purchase.get("request_date"),
            item.get("order_date"),
            item.get("purchase_date"),
        )

        hotmart_fee = _numeric(purchase.get("hotmart_fee")) or 0

        row = {
            "transaction_id": purchase.get("transaction") or item.get("transaction"),
            "buyer_name": buyer.get("name"),
            "buyer_email": buyer.get("email"),
            "product_name": product_name,
            "status": purchase.get("status") or item.get("status"),
            "payment_value": price.get("value") or purchase.get("price_value"),
            "hotmart_fee": hotmart_fee,
            "currency": price.get("currency_value"),
            "purchase_date": purchase_date,
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
        subscriber = item.get("subscriber", {}) or {}
        product = item.get("product", {}) or {}
        plan = item.get("plan", {}) or {}

        product_name = product.get("name")
        if not _product_allowed(product_name):
            continue

        recurrency_days = plan.get("recurrency_period") or plan.get("recurrency_period_days")

        accession_date = _first(
            item.get("accession_date"),
            item.get("date_accession"),
            item.get("request_date"),
            subscriber.get("accession_date"),
            item.get("subscription_date"),
        )
        date_next_charge = _first(
            item.get("date_next_charge"),
            item.get("next_charge_date"),
        )

        row = {
            "subscriber_code": item.get("subscriber_code") or subscriber.get("code"),
            "subscriber_name": subscriber.get("name"),
            "subscriber_email": subscriber.get("email"),
            "product_name": product_name,
            "plan_name": plan.get("name"),
            "status": item.get("status"),
            "recurrency_period_days": recurrency_days,
            "accession_date": accession_date,
            "date_next_charge": date_next_charge,
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
