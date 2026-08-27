const params = new URLSearchParams(window.location.search);
const token = params.get('token');
const qs = token ? `?token=${encodeURIComponent(token)}` : '';

const fmtBRL = (v) => (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

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

async function loadMetrics() {
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

  try { renderBarChart('chartFaturamento', data.faturamento_mensal || [], 'total', fmtBRL, '#C9A227'); }
  catch (e) { console.error('Erro no gráfico de faturamento:', e); }

  try { renderBarChart('chartEntradas', data.entradas_mensal || [], 'n', (v) => v, '#5CA97A'); }
  catch (e) { console.error('Erro no gráfico de entradas:', e); }

  try { renderRecorrencia(data.recorrencia || []); }
  catch (e) { console.error('Erro na tabela de recorrência:', e); }

  try { await loadOneTimeSales(); }
  catch (e) { console.error('Erro na tabela de pagamento único:', e); }
}

async function loadOneTimeSales() {
  const res = await fetch(`/api/one-time-sales${qs}`);
  if (!res.ok) return;
  const rows = await res.json();
  renderOneTime(rows);
}

function renderBarChart(containerId, rows, valueKey, formatter, color) {
  const container = document.getElementById(containerId);
  if (!rows.length) {
    container.innerHTML = '<p class="empty" style="padding:20px 0;">Sem dados suficientes ainda.</p>';
    return;
  }

  const width = container.clientWidth || 480;
  const height = 220;
  const padding = { top: 10, right: 10, bottom: 30, left: 10 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  const values = rows.map(r => Number(r[valueKey]) || 0);
  const maxVal = Math.max(...values, 1);
  const barGap = 10;
  const barWidth = (chartW / rows.length) - barGap;

  let bars = '';
  rows.forEach((r, i) => {
    const val = values[i];
    const barH = Math.max((val / maxVal) * chartH, 2);
    const x = padding.left + i * (barWidth + barGap);
    const y = padding.top + (chartH - barH);
    bars += `
      <rect x="${x}" y="${y}" width="${barWidth}" height="${barH}" rx="3" fill="${color}">
        <title>${r.mes}: ${formatter(val)}</title>
      </rect>
      <text x="${x + barWidth / 2}" y="${height - 10}" text-anchor="middle"
            font-size="10" fill="#9A9790" font-family="IBM Plex Mono, monospace">
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

function renderOneTime(rows) {
  document.getElementById('countOneTime').textContent = rows.length;
  const tbody = document.getElementById('tableOneTime');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">Nenhuma venda de pagamento único encontrada.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${r.buyer_name || '—'}<br><span class="empty">${r.buyer_email || ''}</span></td>
      <td>${r.data_compra || '—'}<br><span class="empty">${fmtBRL(r.payment_value)}</span></td>
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
}

function renderRecorrencia(rows) {
  document.getElementById('countRecorrencia').textContent = rows.length;
  const tbody = document.getElementById('tableRecorrencia');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">Nenhum assinante encontrado.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${r.subscriber_name || '—'}<br><span class="empty">${r.subscriber_email || ''}</span></td>
      <td>${r.plan_name || r.product_name || '—'}</td>
      <td><span class="status-tag status-${r.status}">${statusLabel(r.status)}</span></td>
      <td>${r.proxima_cobranca || '—'}</td>
    </tr>
  `).join('');
}

document.getElementById('syncBtn').addEventListener('click', async () => {
  const btn = document.getElementById('syncBtn');
  btn.disabled = true;
  btn.textContent = 'Sincronizando…';
  try {
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

loadMetrics();
