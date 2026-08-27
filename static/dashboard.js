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

let chartFaturamento, chartEntradas;

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

  // Cada bloco roda isolado: se um falhar, os outros continuam carregando normalmente.
  try { renderFaturamentoChart(data.faturamento_mensal || []); }
  catch (e) { console.error('Erro no gráfico de faturamento:', e); }

  try { renderEntradasChart(data.entradas_mensal || []); }
  catch (e) { console.error('Erro no gráfico de entradas:', e); }

  try { renderSemestrais(data.semestrais || []); }
  catch (e) { console.error('Erro na tabela de semestrais:', e); }

  try { renderRecorrencia(data.recorrencia || []); }
  catch (e) { console.error('Erro na tabela de recorrência:', e); }
}

function renderFaturamentoChart(rows) {
  if (typeof Chart === 'undefined') { console.error('Chart.js não carregou.'); return; }
  const ctx = document.getElementById('chartFaturamento');
  const labels = rows.map(r => r.mes);
  const values = rows.map(r => r.total);
  if (chartFaturamento) chartFaturamento.destroy();
  chartFaturamento = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Faturamento', data: values, backgroundColor: '#C9A227' }] },
    options: baseChartOptions((v) => fmtBRL(v)),
  });
}

function renderEntradasChart(rows) {
  if (typeof Chart === 'undefined') { console.error('Chart.js não carregou.'); return; }
  const ctx = document.getElementById('chartEntradas');
  const labels = rows.map(r => r.mes);
  const values = rows.map(r => r.n);
  if (chartEntradas) chartEntradas.destroy();
  chartEntradas = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Novas assinaturas', data: values,
        borderColor: '#5CA97A', backgroundColor: 'rgba(92,169,122,0.15)',
        fill: true, tension: 0.25,
      }],
    },
    options: baseChartOptions((v) => v),
  });
}

function baseChartOptions(tickFormatter) {
  return {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: '#9A9790' }, grid: { color: '#2b2d32' } },
      y: { ticks: { color: '#9A9790', callback: tickFormatter }, grid: { color: '#2b2d32' } },
    },
  };
}

function renderSemestrais(rows) {
  document.getElementById('countSemestrais').textContent = rows.length;
  const tbody = document.getElementById('tableSemestrais');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">Nenhum assinante semestral encontrado.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>${r.subscriber_name || '—'}<br><span class="empty">${r.subscriber_email || ''}</span></td>
      <td>${r.product_name || '—'}</td>
      <td><span class="status-tag status-${r.status}">${statusLabel(r.status)}</span></td>
      <td>${r.proxima_cobranca || '—'}</td>
    </tr>
  `).join('');
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
      <td>${r.product_name || '—'} ${r.plan_name ? '· ' + r.plan_name : ''}</td>
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
