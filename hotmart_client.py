"""
Cliente para a API do Hotmart (Payments API v1).

Documentação oficial: https://developers.hotmart.com/docs/en/
Autenticação: OAuth2 client_credentials
  POST https://api-sec-vlc.hotmart.com/security/oauth/token

Endpoints usados:
  GET /payments/api/v1/sales/history        -> vendas (faturamento)
  GET /payments/api/v1/subscriptions        -> assinaturas/recorrência

IMPORTANTE: a Hotmart pagina resultados com um campo `page_info.next_page_token`.
Este cliente já trata a paginação automaticamente.

ATENÇÃO: os nomes exatos de alguns campos de resposta (ex.: período de
recorrência do plano) podem variar/mudar. Depois do primeiro sync real,
vale conferir um payload de exemplo (salvo em debug_last_response.json)
e ajustar o mapeamento em sync.py se necessário.
"""
import os
import time
import base64
import requests

TOKEN_URL = "https://api-sec-vlc.hotmart.com/security/oauth/token"
BASE_URL = "https://developers.hotmart.com/payments/api/v1"


class HotmartClient:
    def __init__(self, client_id=None, client_secret=None, basic=None):
        self.client_id = client_id or os.environ["HOTMART_CLIENT_ID"]
        self.client_secret = client_secret or os.environ["HOTMART_CLIENT_SECRET"]
        # "basic" é o token Base64 fornecido pela própria Hotmart junto do client_id/secret.
        # Se não vier configurado, geramos um (algumas contas aceitam, mas o ideal é usar
        # exatamente o que a Hotmart entregou na tela de criação de credenciais).
        self.basic = basic or os.environ.get("HOTMART_BASIC")
        if not self.basic:
            raw = f"{self.client_id}:{self.client_secret}".encode()
            self.basic = base64.b64encode(raw).decode()

        self._token = None
        self._token_expires_at = 0

    def _get_token(self):
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        resp = requests.post(
            TOKEN_URL,
            params={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {self.basic}",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        return self._token

    def _get(self, path, params=None):
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        resp = requests.get(f"{BASE_URL}{path}", headers=headers, params=params or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def iter_sales_history(self, start_date=None, end_date=None, extra_params=None):
        """Itera todas as páginas do histórico de vendas.
        start_date / end_date: timestamps em milissegundos (opcional).
        """
        params = dict(extra_params or {})
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        params["max_results"] = 500

        next_token = None
        while True:
            if next_token:
                params["page_token"] = next_token
            data = self._get("/sales/history", params=params)
            for item in data.get("items", []):
                yield item
            next_token = data.get("page_info", {}).get("next_page_token")
            if not next_token:
                break

    def iter_subscriptions(self, status=None, extra_params=None):
        """Itera todas as páginas de assinaturas.
        status: ACTIVE | INACTIVE | CANCELLED_BY_CUSTOMER | CANCELLED_BY_ADMIN |
                CANCELLED_BY_SELLER | OVERDUE | STARTED (opcional, senão traz todas)
        """
        params = dict(extra_params or {})
        if status:
            params["status"] = status
        params["max_results"] = 500

        next_token = None
        while True:
            if next_token:
                params["page_token"] = next_token
            data = self._get("/subscriptions", params=params)
            for item in data.get("items", []):
                yield item
            next_token = data.get("page_info", {}).get("next_page_token")
            if not next_token:
                break
