# Painel de Faturamento — Hotmart

Dashboard hospedado que puxa dados direto da API do Hotmart (vendas +
assinaturas) e mostra:

- **Faturamento total** e por mês
- **Entradas** (novas assinaturas) por mês
- **Quem está na recorrência** (ativos e atrasados), com produto/plano
- **Quem está no plano semestral** e a situação do próximo pagamento

Isso é um app completo (backend + frontend), pronto pra hospedar. Eu não
consigo hospedar/rodar isso por você a partir do chat — mas em ~15 minutos
você (ou alguém do seu time) coloca no ar seguindo o passo a passo abaixo.
Se preferir, dá pra levar esses arquivos pro **Claude Code** e pedir pra
ele fazer o deploy direto do seu terminal.

---

## 1. Gerar as credenciais no Hotmart

1. Entre na sua conta Hotmart → **Ferramentas** → **Credenciais** (ou
   **Manage my business** → **Products** → **Tools** → **Hotmart Credentials**,
   dependendo do menu da sua conta).
2. Clique em **Criar credencial** → selecione **API Hotmart**.
3. Dê um nome (ex: "Dashboard CMD") e crie.
4. **Baixe/copie na hora**: `Client ID`, `Client Secret` e `Basic`. A Hotmart
   não mostra esses dados de novo depois.

Guarde essas 3 informações — você vai colar nas variáveis de ambiente do
host, nunca no código.

## 2. Escolher onde hospedar

Recomendo **Render.com** (tem plano gratuito para começar, cron job nativo,
e é o mais simples pra quem não é dev). Railway também funciona bem.

### Deploy no Render (passo a passo)

1. Suba esta pasta para um repositório no GitHub (crie um repo privado).
2. No [Render](https://render.com), clique **New +** → **Web Service** →
   conecte o repositório.
3. Configurações:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Em **Environment**, adicione as variáveis (mesmas do `.env.example`):
   `HOTMART_CLIENT_ID`, `HOTMART_CLIENT_SECRET`, `HOTMART_BASIC`,
   `DASHBOARD_ACCESS_TOKEN`.
5. Deploy. Em alguns minutos você recebe uma URL tipo
   `https://cmd-dashboard.onrender.com`.
6. Acesse `https://cmd-dashboard.onrender.com/?token=SUA_SENHA` e clique em
   **"Sincronizar agora"** pra puxar os dados do Hotmart pela primeira vez.

### Sync automático diário

No Render, crie um segundo serviço do tipo **Cron Job** no mesmo repositório:
- **Command**: `python sync.py`
- **Schedule**: `0 9 * * *` (roda todo dia às 9h UTC / 6h em Brasília)
- Mesmas variáveis de ambiente do passo 4 acima.

Se seu host não tiver Cron Job nativo (ex: Railway), suba um segundo serviço
rodando `python worker.py` — ele mesmo se agenda sozinho (ver `SYNC_HOUR_UTC`
no `.env.example`).

## 3. Rodar localmente antes de subir (opcional, recomendado)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edite o .env com suas credenciais reais
export $(cat .env | xargs)   # ou use um pacote tipo python-dotenv
python sync.py               # testa a conexão e puxa os dados
python app.py                # sobe o dashboard em http://localhost:5000
```

## Como o dashboard calcula cada métrica

- **Faturamento**: soma de `sales.payment_value` das vendas com status
  `APPROVED`/`COMPLETE`, vindas do endpoint `/sales/history`.
- **Recorrência ativa / atrasada / cancelada**: status direto do endpoint
  `/subscriptions` (`ACTIVE`, `OVERDUE`, `CANCELLED_*`).
- **Plano semestral**: identificado pelo nome do plano (contém "semestral",
  "semestre" etc.) ou por um período de recorrência entre 170–200 dias.
  Ajuste a lista `SEMESTRAL_HINTS` em `sync.py` se seus planos tiverem
  nomes diferentes.
- **Entradas**: novas assinaturas, pela `accession_date` de cada assinatura.

## ⚠️ Pontos de atenção antes de confiar 100% nos números

1. **Nomes de campo da API**: documentei os endpoints com base na
   documentação pública do Hotmart, mas alguns nomes de campo podem variar
   ligeiramente conforme sua conta/versão da API. Depois do primeiro sync,
   vale abrir o arquivo `dashboard.db` (ou adicionar um `print` temporário em
   `sync.py`) e conferir um item bruto de `/subscriptions` pra garantir que
   `plan.recurrency_period`, `accession_date` e `date_next_charge` estão
   vindo como esperado. Se algum vier vazio, me manda o JSON de exemplo
   (sem dados sensíveis) que eu ajusto o mapeamento.
2. **"Saída de cliente"**: hoje o painel mostra cancelados como contagem
   total (não por mês), porque a API de assinaturas não traz a data do
   cancelamento — só o status atual. Se você quiser um gráfico de churn por
   mês, dá pra integrar também o endpoint de "Subscription Cancellations",
   que traz a data. Posso incluir isso numa próxima versão.
3. **Limite de requisições**: a API do Hotmart tem rate limit. Para uma
   base grande de clientes, o sync pode levar alguns minutos — isso é
   normal e já está tratado com paginação automática.
4. **Segurança**: nunca deixe `HOTMART_CLIENT_SECRET` no código ou em
   repositório público. Sempre como variável de ambiente. Use um repo
   **privado** no GitHub.

## Próximos passos que dá pra evoluir

- Gráfico de churn (saída) por mês usando o endpoint de cancelamentos.
- Filtro por produto (se você vende mais de um produto na Hotmart).
- Exportar a lista de "semestrais a vencer nos próximos 15 dias" em CSV,
  pra facilitar cobrança manual/WhatsApp.
- Autenticação por usuário/senha (hoje é um token único compartilhado).
