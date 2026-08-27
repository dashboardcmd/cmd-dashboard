const params = new URLSearchParams(window.location.search);
const token = params.get('token');

const fmtBRL = (v) => (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

let oneTimeData = [];
let recorrenciaData = [];
let costsData = [];
let oneTimeSort = { key: null, dir: 1 };
let recorrenciaSort = { key: null, dir: 1 };

const MESES_PT = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];

function statusLabel(status) {
  const map = {
    ACTIVE: 'Ativo',
    OVERDUE: 'Atrasado',
    CANCELLED_BY_CUSTOMER: 'Cancelado (cliente)',
    CANCELLED_BY_ADMIN: 'Cancelado (admin)',
    CANCELLED_BY_SELLER: 'Cancelado (vendedor)',
    STARTED: 'Iniciado',
  };
  return map[status] || status;
}

const vigenciaLabel = {
  em_dia: 'Em dia',
  vencendo: 'Vencendo',
  vencido: 'Vencido',
  sem_info: 'Definir',
};

function buildQuery() {
  const q = new URLSearchParams();
  if (token) q.set('token', token);
  const start = document.getElementById('startDate').value;
  const end = document.getElementById('endDate').value;
  if (start) q.set('start_date', start);
  if (end) q.set('end_date', end);
  const qs = q.toString();
  return qs ? `?${qs}` : '';
}

function simpleQuery() {
  const q = new URLSearchParams();
  if (token) q.set('token', token);
  const qs = q.toString();
  return qs ? `?${qs}` : '';
}

async function loadMetrics() {
  const qs = buildQuery();
  const res = await fetch(`/api/metrics${qs}`);
  if (!res.ok) {
    alert('Não foi possível carregar os dados. Verifique o token de acesso.');
    return;
  }
  const data = await res.json();

  document.getElementById('kpiFaturamento').textContent = fmtBRL(data.faturamento_total);
  document.getElementById('kpiAtivos').textContent = data.assinantes_ativos;
  document.getElementById('kpiAtrasados').textContent = data.assinantes_atrasados;
  document.getElementById('kpiCancelados').textContent = data.assinantes_cancelados;

  const deltaEl = document.getElementById('kpiVariacao');
  if (data.faturamento_variacao_pct === null || data.faturamento_variacao_pct === undefined) {
    deltaEl.textContent = '';
  } else {
    const v = data.faturamento_variacao_pct;
    const arrow = v >= 0 ? '▲' : '▼';
    deltaEl.textContent = `${arrow} ${Math.abs(v)}% vs mês anterior`;
    deltaEl.className = 'kpi-delta ' + (v >= 0 ? 'up' : 'down');
  }

  renderGoal(data);

  try { renderBarChart('chartFaturamento', data.faturamento_mensal || [], 'total', fmtBRL, '#C9A227'); }
  catch (e) { console.error('Erro no gráfico de faturamento:', e); }

  try { renderBarChart('chartEntradas', data.entradas_mensal || [], 'n', (v) => String(v), '#5CA97A'); }
  catch (e) { console.error('Erro no gráfico de entradas:', e); }

  try { renderBarChart('chartCancelamentos', data.cancelamentos_mensal || [], 'n', (v) => String(v), '#C06A4C'); }
  catch (e) { console.error('Erro no gráfico de cancelamentos:', e); }

  recorrenciaData = data.recorrencia || [];
  try { renderRecorrencia(); }
  catch (e) { console.error('Erro na tabela de recorrência:', e); }

  try { await loadOneTimeSales(); }
  catch (e) { console.error('Erro na tabela de pagamento único:', e); }

  try { await loadCosts(); }
  catch (e) { console.error('Erro nos custos da agência:', e); }
}

function renderGoal(data) {
  const [year, month] = (data.mes_atual || '').split('-');
  const monthLabel = month ? `— ${MESES_PT[parseInt(month, 10) - 1]}/${year}` : '';
  document.getElementById('goalMonthLabel').textContent = monthLabel;

  const valuesEl = document.getElementById('goalValues');
  const fillEl = document.getElementById('goalBarFill');

  if (!data.meta_mensal) {
    valuesEl.textContent = `Faturado no mês: ${fmtBRL(data.faturamento_mes_atual)} · nenhuma meta definida ainda.`;
    fillEl.style.width = '0%';
    fillEl.className = 'goal-bar-fill';
    return;
  }

  const pct = Math.min(data.meta_progresso_pct || 0, 100);
  valuesEl.textContent = `${fmtBRL(data.faturamento_mes_atual)} de ${fmtBRL(data.meta_mensal)} (${data.meta_progresso_pct}%)`;
  fillEl.style.width = `${pct}%`;
  fillEl.className = 'goal-bar-fill' + (data.meta_progresso_pct >= 100 ? ' complete' : '');
}

async function loadOneTimeSales() {
  const qs = buildQuery();
  const res = await fetch(`/api/one-time-sales${qs}`);
  if (!res.ok) return;
  oneTimeData = await res.json();
  renderOneTime();
}

async function loadCosts() {
  const qs = simpleQuery();
  const res = await fetch(`/api/costs${qs}`);
  if (!res.ok) return;
  const data = await res.json();
  costsData = data.items || [];
  renderCosts(data);
}

function renderCosts(data) {
  document.getElementById('custoMensal').textContent = fmtBRL(data.custo_mensal_total);
  document.getElementById('custoAnual').textContent = fmtBRL(data.custo_anual_total);
  document.getElementById('impostoValor').textContent = `${fmtBRL(data.imposto_mensal)} (${data.imposto_pct}%)`;

  const dnbMensalEl = document.getElementById('dnbMensal');
  const dnbAnualEl = document.getElementById('dnbAnual');
  dnbMensalEl.textContent = fmtBRL(data.dnb_mensal);
  dnbAnualEl.textContent = fmtBRL(data.dnb_anual);
  dnbMensalEl.className = 'kpi-value dnb-value ' + (data.dnb_mensal >= 0 ? 'positive-text' : 'negative-text');
  dnbAnualEl.className = 'kpi-value dnb-value ' + (data.dnb_anual >= 0 ? 'positive-text' : 'negative-text');

  document.getElementById('countCosts').textContent = costsData.length;
  const tbody = document.getElementById('tableCosts');
  if (!costsData.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">Nenhum custo cadastrado ainda.</td></tr>';
    return;
  }
  tbody.innerHTML = costsData.map(c => `
    <tr>
      <td>
        <span class="cost-field" data-id="${c.id}" data-field="name">${c.name}</span>
      </td>
      <td>
        <span class="cost-field" data-id="${c.id}" data-field="monthly_value">${fmtBRL(c.monthly_value)}</span>
      </td>
      <td>
        <span class="cost-field" data-id="${c.id}" data-field="contract_months">${c.contract_months || 12}</span>
      </td>
      <td>${fmtBRL((c.monthly_value || 0) * (c.contract_months || 12))}</td>
      <td>
        <span class="cost-field" data-id="${c.id}" data-field="payment_info">${c.payment_info || '—'}</span>
      </td>
      <td><button class="btn-link delete-cost-btn" data-id="${c.id}">excluir</button></td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.cost-field').forEach(el => {
    el.addEventListener('click', () => startCostFieldEdit(el));
  });

  tbody.querySelectorAll('.delete-cost-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('Excluir este custo?')) return;
      const qs = simpleQuery();
      await fetch(`/api/cost-item/${btn.dataset.id}/delete${qs}`, { method: 'POST' });
      await loadCosts();
    });
  });
}

function startCostFieldEdit(el) {
  const id = el.dataset.id;
  const field = el.dataset.field;
  const item = costsData.find(c => String(c.id) === String(id));
  if (!item) return;

  const isNumber = field === 'monthly_value' || field === 'contract_months';
  const currentValue = field === 'monthly_value' ? item.monthly_value
    : field === 'contract_months' ? item.contract_months
    : item[field] || '';

  el.innerHTML = `
    <input type="${isNumber ? 'number' : 'text'}" class="cost-input" value="${currentValue}">
    <button class="save-value-btn">Salvar</button>
  `;
  const input = el.querySelector('.cost-input');
  const btn = el.querySelector('.save-value-btn');
  input.focus();
  btn.addEventListener('click', async () => {
    const updated = { ...item };
    updated[field] = isNumber ? parseFloat(input.value) || 0 : input.value;
    try {
      const qs = simpleQuery();
      const res = await fetch(`/api/cost-item/${id}${qs}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: updated.name,
          monthly_value: updated.monthly_value,
          contract_months: updated.contract_months,
          payment_info: updated.payment_info,
        }),
      });
      const respData = await res.json();
      if (!respData.ok) throw new Error(respData.error || 'erro ao salvar');
      await loadCosts();
    } catch (err) {
      alert('Erro ao salvar: ' + err.message);
    }
  });
}

function renderBarChart(containerId, rows, valueKey, formatter, color) {
  const container = document.getElementById(containerId);
  if (!rows.length) {
    container.innerHTML = '<p class="empty" style="padding:20px 0;">Sem dados suficientes ainda.</p>';
    return;
  }

  const width = container.clientWidth || 380;
  const height = 220;
  const padding = { top: 26, right: 8, bottom: 28, left: 8 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const values = rows.map(r => Number(r[valueKey]) || 0);
  const maxVal = Math.max(...values, 1);
  const barGap = 8;
  const barWidth = (chartW / rows.length) - barGap;

  let bars = '';
  rows.forEach((r, i) => {
    const val = values[i];
    const barH = Math.max((val / maxVal) * chartH, 2);
    const x = padding.left + i * (barWidth + barGap);
    const y = padding.top + (chartH - barH);
    const label = formatter(val);
    bars += `
      <text x="${x + barWidth / 2}" y="${y - 6}" text-anchor="middle"
            font-size="9" fill="#E9E6DF" font-family="IBM Plex Mono, monospace">
        ${label}
      </text>
      <rect x="${x}" y="${y}" width="${barWidth}" height="${barH}" rx="3" fill="${color}">
        <title>${r.mes}: ${label}</title>
      </rect>
      <text x="${x + barWidth / 2}" y="${height - 8}" text-anchor="middle"
            font-size="9" fill="#9A9790" font-family="IBM Plex Mono, monospace">
        ${(r.mes || '').slice(2)}
      </text>
    `;
  });

  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" preserveAspectRatio="xMidYMid meet">
      ${bars}
    </svg>
  `;
}

function applySort(rows, sortState) {
  if (!sortState.key) return rows;
  const { key, dir } = sortState;
  return [...rows].sort((a, b) => {
    let av = a[key], bv = b[key];
    if (av === null || av === undefined) av = '';
    if (bv === null || bv === undefined) bv = '';
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });
}

function applySearch(rows, term, fields) {
  if (!term) return rows;
  const t = term.toLowerCase();
  return rows.filter(r => fields.some(f => (r[f] || '').toString().toLowerCase().includes(t)));
}

function renderOneTime() {
  const term = document.getElementById('searchOneTime').value;
  let rows = applySearch(oneTimeData, term, ['buyer_name', 'buyer_email']);
  rows = applySort(rows, oneTimeSort);

  document.getElementById('countOneTime').textContent = rows.length;
  const tbody = document.getElementById('tableOneTime');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">Nenhuma venda de pagamento único encontrada.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr class="${r.vence_em_breve ? 'row-urgent' : ''}">
      <td>${r.buyer_name || '—'}<br><span class="empty">${r.buyer_email || ''}</span></td>
      <td>${r.data_compra || '—'}<br>
        <span class="value-edit" data-tx="${r.transaction_id}" data-value="${r.payment_value || 0}">
          ${fmtBRL(r.payment_value)}${r.payment_value_edited ? ' <span class="edited-tag">editado</span>' : ''}
          <span class="edit-icon" title="Corrigir valor">✎</span>
        </span>
      </td>
      <td>
        <select class="term-select" data-tx="${r.transaction_id}">
          <option value="" ${!r.term_months ? 'selected' : ''}>Selecionar…</option>
          <option value="6" ${r.term_months === 6 ? 'selected' : ''}>6 meses</option>
          <option value="12" ${r.term_months === 12 ? 'selected' : ''}>1 ano</option>
        </select>
      </td>
      <td>
        ${r.vencimento || '—'}
        ${r.status_vigencia && r.status_vigencia !== 'sem_info'
          ? `<br><span class="status-tag status-vig-${r.status_vigencia}">${vigenciaLabel[r.status_vigencia]}</span>`
          : ''}
        ${r.vence_em_breve ? '<span class="urgent-icon" title="Vence em até 7 dias">⚠</span>' : ''}
      </td>
    </tr>
  `).join('');

  tbody.querySelectorAll('.term-select').forEach(sel => {
    sel.addEventListener('change', async (e) => {
      const txId = e.target.dataset.tx;
      const months = parseInt(e.target.value, 10);
      if (!months) return;
      e.target.disabled = true;
      try {
        const qs = buildQuery();
        const res = await fetch(`/api/manual-term${qs}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ transaction_id: txId, term_months: months }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'erro ao salvar');
        await loadOneTimeSales();
      } catch (err) {
        alert('Erro ao salvar vigência: ' + err.message);
        e.target.disabled = false;
      }
    });
  });

  tbody.querySelectorAll('.value-edit').forEach(el => {
    el.addEventListener('click', () => startValueEdit(el));
  });
}

function startValueEdit(el) {
  const txId = el.dataset.tx;
  const current = el.dataset.value;
  el.innerHTML = `
    <input type="number" step="0.01" class="value-input" value="${current}">
    <button class="save-value-btn">Salvar</button>
  `;
  const input = el.querySelector('.value-input');
  const btn = el.querySelector('.save-value-btn');
  input.focus();
  btn.addEventListener('click', async () => {
    const newValue = parseFloat(input.value);
    if (isNaN(newValue) || newValue < 0) { alert('Valor inválido.'); return; }
    try {
      const qs = buildQuery();
      const res = await fetch(`/api/sale-value${qs}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transaction_id: txId, payment_value: newValue }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'erro ao salvar');
      await loadOneTimeSales();
      await loadMetrics();
    } catch (err) {
      alert('Erro ao salvar valor: ' + err.message);
    }
  });
}

function renderRecorrencia() {
  const term = document.getElementById('searchRecorrencia').value;
  let rows = applySearch(recorrenciaData, term, ['subscriber_name', 'subscriber_email']);
  rows = applySort(rows, recorrenciaSort);

  document.getElementById('countRecorrencia').textContent = rows.length;
  const tbody = document.getElementById('tableRecorrencia');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">Nenhum assinante encontrado.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr class="${r.vence_em_breve ? 'row-urgent' : ''}">
      <td>${r.subscriber_name || '—'}<br><span class="empty">${r.subscriber_email || ''}</span></td>
      <td>${r.plan_name || r.product_name || '—'}</td>
      <td><span class="status-tag status-${r.status}">${statusLabel(r.status)}</span></td>
      <td>${r.proxima_cobranca || '—'} ${r.vence_em_breve ? '<span class="urgent-icon" title="Cobra em até 7 dias">⚠</span>' : ''}</td>
    </tr>
  `).join('');
}

function toCsv(rows, columns) {
  const header = columns.map(c => c.label).join(';');
  const lines = rows.map(r => columns.map(c => `"${(r[c.key] ?? '').toString().replace(/"/g, '""')}"`).join(';'));
  return [header, ...lines].join('\n');
}

function downloadCsv(filename, content) {
  const blob = new Blob(['\ufeff' + content], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

document.getElementById('syncBtn').addEventListener('click', async () => {
  const btn = document.getElementById('syncBtn');
  btn.disabled = true;
  btn.textContent = 'Sincronizando…';
  try {
    const qs = simpleQuery();
    const res = await fetch(`/api/sync${qs}`, { method: 'POST' });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'erro desconhecido');
    document.getElementById('lastSync').textContent = `último sync: ${new Date().toLocaleString('pt-BR')}`;
    await loadMetrics();
  } catch (e) {
    alert('Erro ao sincronizar: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sincronizar agora';
  }
});

document.getElementById('applyFilterBtn').addEventListener('click', () => loadMetrics());

document.getElementById('clearFilterBtn').addEventListener('click', () => {
  document.getElementById('startDate').value = '';
  document.getElementById('endDate').value = '';
  loadMetrics();
});

document.getElementById('editGoalBtn').addEventListener('click', async () => {
  const current = prompt('Qual é a meta de faturamento para este mês? (só números, ex: 50000)');
  if (current === null) return;
  const value = parseFloat(current.replace(',', '.'));
  if (isNaN(value) || value < 0) { alert('Valor inválido.'); return; }
  try {
    const qs = simpleQuery();
    const res = await fetch(`/api/goal${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ meta_mensal: value }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'erro ao salvar');
    await loadMetrics();
  } catch (err) {
    alert('Erro ao salvar meta: ' + err.message);
  }
});

document.getElementById('editTaxBtn').addEventListener('click', async () => {
  const current = prompt('Qual a alíquota de imposto (%) sobre o faturamento?', '10');
  if (current === null) return;
  const value = parseFloat(current.replace(',', '.'));
  if (isNaN(value) || value < 0 || value > 100) { alert('Valor inválido.'); return; }
  try {
    const qs = simpleQuery();
    const res = await fetch(`/api/tax-rate${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ imposto_pct: value }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'erro ao salvar');
    await loadCosts();
  } catch (err) {
    alert('Erro ao salvar imposto: ' + err.message);
  }
});

document.getElementById('addCostBtn').addEventListener('click', async () => {
  const name = document.getElementById('newCostName').value.trim();
  const value = parseFloat(document.getElementById('newCostValue').value);
  const months = parseInt(document.getElementById('newCostMonths').value, 10) || 12;
  const payment = document.getElementById('newCostPayment').value.trim();
  if (!name) { alert('Digite um nome para o custo.'); return; }
  if (isNaN(value) || value < 0) { alert('Valor mensal inválido.'); return; }
  try {
    const qs = simpleQuery();
    const res = await fetch(`/api/cost-item${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, monthly_value: value, contract_months: months, payment_info: payment }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'erro ao salvar');
    document.getElementById('newCostName').value = '';
    document.getElementById('newCostValue').value = '';
    document.getElementById('newCostMonths').value = '12';
    document.getElementById('newCostPayment').value = '';
    await loadCosts();
  } catch (err) {
    alert('Erro ao adicionar custo: ' + err.message);
  }
});

document.getElementById('searchOneTime').addEventListener('input', () => renderOneTime());
document.getElementById('searchRecorrencia').addEventListener('input', () => renderRecorrencia());

document.getElementById('exportOneTime').addEventListener('click', () => {
  const csv = toCsv(oneTimeData, [
    { key: 'buyer_name', label: 'Cliente' },
    { key: 'buyer_email', label: 'E-mail' },
    { key: 'data_compra', label: 'Data da compra' },
    { key: 'payment_value', label: 'Valor' },
    { key: 'term_months', label: 'Vigência (meses)' },
    { key: 'vencimento', label: 'Vence em' },
  ]);
  downloadCsv('pagamento-unico.csv', csv);
});

document.getElementById('exportRecorrencia').addEventListener('click', () => {
  const csv = toCsv(recorrenciaData, [
    { key: 'subscriber_name', label: 'Cliente' },
    { key: 'subscriber_email', label: 'E-mail' },
    { key: 'plan_name', label: 'Plano' },
    { key: 'status', label: 'Status' },
    { key: 'proxima_cobranca', label: 'Próxima cobrança' },
  ]);
  downloadCsv('recorrencia.csv', csv);
});

document.querySelectorAll('th.sortable').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.sort;
    const table = th.closest('table');
    const isOneTime = table.querySelector('#tableOneTime') !== null;
    const sortState = isOneTime ? oneTimeSort : recorrenciaSort;
    if (sortState.key === key) sortState.dir *= -1;
    else { sortState.key = key; sortState.dir = 1; }
    if (isOneTime) renderOneTime(); else renderRecorrencia();
  });
});

loadMetrics();
