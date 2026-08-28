"""
Puxa dados da API do Hotmart e grava no banco local (SQLite).

Rodar manualmente:   python sync.py
Rodar agendado:      configurar um Cron Job (ver README.md) chamando este script
                      1x por dia (ex.: todo dia às 6h da manhã).
"""
import json
import datetime as dt

from hotmart_client import HotmartClient
from database import init_db, upsert_sale, upsert_subscription, log_sync, update_net_received

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


def _extract_hotmart_fee(purchase):
    fee_obj = purchase.get("hotmart_fee")
    if isinstance(fee_obj, dict):
        return fee_obj.get("total") or 0
    return fee_obj or 0


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

        hotmart_fee = _extract_hotmart_fee(purchase)

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


def sync_commissions(client):
    """Busca em /sales/commissions o valor líquido real recebido como produtor.

    Formato real da resposta (confirmado em produção):
        {
          "transaction": "HP...",
          "commissions": [
            {"source": "PRODUCER", "commission": {"value": 2374, "currency_code": "BRL"}, "user": {...}}
          ],
          ...
        }
    """
    count = 0
    for item in client.iter_sales_commissions():
        transaction_id = item.get("transaction")
        if not transaction_id:
            continue

        commissions_list = item.get("commissions") or []
        producer_value = None
        for c in commissions_list:
            source = (c.get("source") or "").upper()
            if source == "PRODUCER":
                producer_value = (c.get("commission") or {}).get("value")
                break

        if producer_value is None:
            continue

        update_net_received(transaction_id, producer_value)
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
        try:
            comm_count = sync_commissions(client)
        except Exception as e:
            comm_count = 0
            print(f"Aviso: sync de comissões falhou ({e}). Faturamento bruto/recorrência seguem normais.")
        log_sync(started_at, dt.datetime.utcnow().isoformat(), sales_count, subs_count, "OK")
        print(f"Sync concluído: {sales_count} vendas, {subs_count} assinaturas, {comm_count} comissões.")
    except Exception as e:
        log_sync(started_at, dt.datetime.utcnow().isoformat(), 0, 0, "ERRO", str(e))
        print(f"Erro no sync: {e}")
        raise


if __name__ == "__main__":
    run_sync()
