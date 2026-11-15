import { createApi } from './api.js';
import { ICONS } from './icons.js';
import { esc, PERIODS, periodRange, emptyState, errorState, salesTaxReport, salesTaxCsv, csvFileName, clientCard, countryOptions } from './format.js';

const root = document.getElementById('app');
const freshLogin = (info = '') => ({ busy: false, error: '', info, email: '' });
const freshPassword = () => ({ busy: false, error: '' });

const state = {
  screen: 'boot', // boot | login | password | app
  login: freshLogin(),
  password: freshPassword(),
  session: null,
  tenantId: null,
  view: 'sales', // sales | clients | account
  period: { key: 'last_month', ...periodRange('last_month') },
  report: { status: 'idle', data: null, error: '' },
  admin: { status: 'idle', tenants: [], drafts: {}, notice: null, error: '' },
};
let token = 0; // guards against an older response overwriting a newer screen
const OPTIONS = countryOptions();

const api = createApi({
  onUnauthorized: () => {
    // Only someone who was signed in is told their session ended; a first visit just shows the form.
    if (state.screen === 'app' || state.screen === 'password') { state.session = null; state.login = freshLogin('Your session has ended. Please sign in again.'); setScreen('login'); }
  },
  onPasswordChangeRequired: () => { if (state.screen !== 'password') { state.password = freshPassword(); setScreen('password'); } },
});

function setScreen(screen) { state.screen = screen; render(); }
const brand = (dark = false) => `<div class="brand"><div class="brand-mark${dark ? ' dark' : ''}">${ICONS.mark}</div><span class="brand-name">Taxcart</span></div>`;
const isStaff = () => !!state.session?.user.is_staff;
const currentTenant = () => state.session?.tenants.find((t) => t.id === state.tenantId) ?? null;

/* ---------------------------------------------------------------- sign-in */
function loginShell(title, sub, form) {
  const stat = (n, label) => `<div><div class="side-stat-num">${esc(n)}</div><div class="side-stat-label">${esc(label)}</div></div>`;
  return `<div class="login-wrap">
    <div class="login-side">
      <div class="login-side-top">${brand()}</div>
      <div class="login-hero-figure"><div class="login-hero-num">Sales tax,<br>handled.</div><div class="login-hero-label">Your sales and the tax collected on them, country by country, kept up to date for you.</div></div>
      <div class="login-side-bottom">${stat('By country', 'And by state in the US')}${stat('By rate', 'Each tax shown separately')}${stat('After refunds', 'Refunds counted when they happen')}</div>
    </div>
    <main class="login-form-side"><div class="login-form">
      <div class="login-form-brand">${brand(true)}</div>
      <h1>${esc(title)}</h1><div class="sub">${esc(sub)}</div>${form}
    </div></main>
  </div>`;
}

function renderLogin() {
  const l = state.login;
  const err = l.error ? `<div class="form-error" role="alert">${esc(l.error)}</div>` : '';
  const info = l.info ? `<div class="form-info" role="status">${esc(l.info)}</div>` : '';
  return loginShell('Sign in', 'Use the email and password for your Taxcart account.', `<form id="login-form" novalidate>
    <label class="field-label" for="email">Email</label>
    <div class="field-box">${ICONS.mail}<input id="email" name="email" type="email" inputmode="email" autocomplete="username" placeholder="you@company.com" value="${esc(l.email)}" required autofocus></div>
    <label class="field-label" for="password">Password</label>
    <div class="field-box">${ICONS.key}<input id="password" name="password" type="password" autocomplete="current-password" required></div>
    ${err}${info}
    <button class="btn btn-primary" type="submit" ${l.busy ? 'disabled' : ''}>${l.busy ? 'Signing in…' : 'Sign in'}</button>
    <p class="otp-note">Access is by invitation. If you have forgotten your password, ask your Taxcart representative to reset it.</p>
  </form>`);
}

function passwordForm(forced) {
  const p = state.password;
  const err = p.error ? `<div class="form-error" role="alert">${esc(p.error)}</div>` : '';
  const ok = p.done ? '<div class="form-info" role="status">Your password has been changed.</div>' : '';
  return `<form id="password-form" class="${forced ? '' : 'narrow-form'}" novalidate>
    <label class="field-label" for="current">${forced ? 'Temporary password' : 'Current password'}</label>
    <div class="field-box">${ICONS.key}<input id="current" name="current" type="password" autocomplete="current-password" required ${forced ? 'autofocus' : ''}></div>
    <label class="field-label" for="new">New password</label>
    <div class="field-box">${ICONS.key}<input id="new" name="new" type="password" autocomplete="new-password" minlength="12" required></div>
    <label class="field-label" for="again">New password again</label>
    <div class="field-box">${ICONS.key}<input id="again" name="again" type="password" autocomplete="new-password" minlength="12" required></div>
    ${err}${ok}
    <button class="btn btn-primary" type="submit" ${p.busy ? 'disabled' : ''}>${p.busy ? 'Saving…' : 'Save new password'}</button>
    <p class="otp-note">Use at least 12 characters. A few unrelated words work well.</p>
    ${forced ? '<button class="btn btn-ghost" type="button" data-action="logout">Sign out</button>' : ''}
  </form>`;
}

/* ---------------------------------------------------------------- app shell */
function renderShell() {
  const s = state.session;
  const tenant = currentTenant();
  const picker = s.tenants.length > 1
    ? `<label class="visually-hidden" for="tenant">Company</label><select id="tenant" class="filter-select side-select">${s.tenants.map((t) => `<option value="${esc(t.id)}" ${t.id === state.tenantId ? 'selected' : ''}>${esc(t.name)}</option>`).join('')}</select>`
    : '';
  const nav = (key, label, icon) => `<button class="nav-item ${state.view === key ? 'active' : ''}" data-action="nav" data-view="${key}">${icon}<span>${label}</span></button>`;
  return `<div class="shell">
    <aside class="sidebar">${brand()}${picker}
      <nav>${nav('sales', 'Sales &amp; tax', ICONS.sales)}${isStaff() ? nav('clients', 'Clients', ICONS.clients) : ''}</nav>
      <div class="sidebar-footer">
        <div class="viewer-company">${esc(isStaff() ? 'Taxcart staff' : tenant?.name ?? '')}</div><div class="viewer-label">${esc(s.user.email)}</div>
        <button class="switch-btn ${state.view === 'account' ? 'on' : ''}" data-action="nav" data-view="account">${ICONS.key}<span>Change password</span></button>
        <button class="switch-btn" data-action="logout">${ICONS.logout}<span>Sign out</span></button>
      </div>
    </aside>
    <main class="main" id="main" tabindex="-1">${renderMain()}</main>
  </div>`;
}

const head = (title, sub, right = '') => `<div class="page-head"><div><h1 class="page-title">${title}</h1><p class="page-sub">${esc(sub)}</p></div>${right}</div>`;

function periodControls() {
  const p = state.period;
  const custom = p.key === 'custom'
    ? `<label class="visually-hidden" for="from">From</label><input class="filter-select" type="date" id="from" value="${esc(p.from)}">
       <label class="visually-hidden" for="to">To</label><input class="filter-select" type="date" id="to" value="${esc(p.to)}">
       <button class="btn-inline" data-action="apply-period">Show</button>`
    : '';
  return `<div class="toolbar period"><label class="visually-hidden" for="period">Period</label>
    <select id="period" class="filter-select">${PERIODS.map(([k, label]) => `<option value="${k}" ${k === p.key ? 'selected' : ''}>${label}</option>`).join('')}</select>${custom}
    ${state.report.status === 'ready' && state.report.data.status === 'ready' ? '<button class="btn-inline" data-action="download-csv">Download all countries</button>' : ''}</div>`;
}

function renderMain() {
  if (state.view === 'account') return head('Change password', 'Changing it signs you out on your other devices.') + passwordForm(false);
  if (state.view === 'clients') return renderClients();
  const tenant = currentTenant();
  if (!tenant) {
    return head('Sales &amp; tax', '') + emptyState(isStaff() ? 'No clients yet. Add your first client under Clients.' : 'No company is linked to this login yet. Please contact your Taxcart representative.');
  }
  const r = state.report;
  const top = head('Sales &amp; tax', `${tenant.name}: sales and the tax collected on them, by country.`, periodControls());
  if (r.status === 'error') return top + errorState(r.error);
  if (r.status !== 'ready') return `${top}<div class="loading" role="status">Loading… the first report of the day can take up to a minute.</div>`;
  return top + salesTaxReport(r.data);
}

function renderClients() {
  const a = state.admin;
  const top = head('Clients', 'Set up each client: where their sales come from, which countries they report, and who can sign in.');
  const add = `<form class="card add-client" id="add-client" novalidate><label class="field-label" for="new-client">Add a client</label>
    <div class="inline-form"><input class="text-input" id="new-client" name="name" placeholder="Company name" maxlength="120" autocomplete="off"><button class="btn-inline" type="submit">Add client</button></div>
    ${a.notice && !a.notice.tenant && a.notice.text ? `<div class="${a.notice.error ? 'form-error' : 'form-info'} spaced" role="status">${esc(a.notice.text)}</div>` : ''}</form>`;
  if (a.status === 'error') return top + errorState(a.error);
  if (a.status !== 'ready') return `${top}<div class="loading" role="status">Loading…</div>`;
  const cards = a.tenants.map((t) => clientCard(t, a.drafts[t.id], OPTIONS, a.notice)).join('');
  return top + add + (cards || emptyState('No clients yet.'));
}

/* ---------------------------------------------------------------- loading */
function paintMain() {
  const main = document.getElementById('main');
  if (main && state.screen === 'app') main.innerHTML = renderMain();
}

async function loadReport() {
  const my = ++token;
  const tenant = currentTenant();
  if (!tenant || state.view !== 'sales') return;
  state.report = { status: 'loading', data: null, error: '' };
  paintMain();
  try {
    const data = await api.salesTax({ tenant: tenant.id, from: state.period.from, to: state.period.to });
    if (my !== token) return;
    state.report = { status: 'ready', data, error: '' };
  } catch (e) {
    if (my !== token || state.screen !== 'app') return;
    state.report = { status: 'error', data: null, error: e.message };
  }
  paintMain();
}

const draftOf = (t) => ({ name: t.name, shop_domain: t.shop_domain ?? '', countries: t.countries.map((c) => ({ ...c })) });

function putTenant(t, keepDraft = false) {
  const a = state.admin;
  const i = a.tenants.findIndex((x) => x.id === t.id);
  if (i >= 0) a.tenants[i] = t; else a.tenants.push(t);
  a.tenants.sort((x, y) => x.name.localeCompare(y.name));
  if (!keepDraft || !a.drafts[t.id]) a.drafts[t.id] = draftOf(t);
}

async function loadClients() {
  const my = ++token;
  state.admin = { ...state.admin, status: 'loading', error: '' };
  paintMain();
  try {
    const { tenants } = await api.admin.tenants();
    if (my !== token) return;
    state.admin = { status: 'ready', tenants: [], drafts: {}, notice: state.admin.notice, error: '' };
    tenants.forEach((t) => putTenant(t));
  } catch (e) {
    if (my !== token || state.screen !== 'app') return;
    state.admin = { ...state.admin, status: 'error', error: e.message };
  }
  paintMain();
}

const load = () => (state.view === 'clients' ? loadClients() : state.view === 'sales' ? loadReport() : undefined);

/** Copy what is typed in a client card into its draft, so a repaint does not lose it. */
function syncDraft(tenantId) {
  const d = state.admin.drafts[tenantId];
  const name = document.getElementById(`name-${tenantId}`), shop = document.getElementById(`shop-${tenantId}`);
  if (d && name && shop) { d.name = name.value; d.shop_domain = shop.value; }
}
const syncAllDrafts = () => Object.keys(state.admin.drafts).forEach(syncDraft);
function notify(tenant, text, extra = {}) { state.admin.notice = { tenant, text, ...extra }; paintMain(); }

/** Refresh the tenant list in the sidebar after staff add or rename a client. */
async function refreshSession() {
  try { state.session = await api.session(); chooseDefaults(); if (state.screen === 'app') { syncAllDrafts(); render(); } } catch { /* handled by the api hooks */ }
}

/* ---------------------------------------------------------------- boot / render */
function chooseDefaults() {
  const s = state.session;
  state.tenantId = (s.tenants.find((t) => t.id === state.tenantId) ?? s.tenants[0])?.id ?? null;
  if (state.view === 'clients' && !isStaff()) state.view = 'sales';
}

async function boot() {
  try {
    state.session = await api.session();
    if (state.session.user.must_change_password) { state.password = freshPassword(); return setScreen('password'); }
    chooseDefaults();
    if (isStaff() && state.session.tenants.length === 0) state.view = 'clients';
    setScreen('app');
    load();
  } catch (e) {
    if (e.status === 401) return setScreen('login');
    if (e.code === 'password_change_required') return;
    root.innerHTML = loginShell('We are having trouble', e.message, '<button class="btn btn-primary" data-action="reload">Try again</button>');
  }
}

function render() {
  root.innerHTML = state.screen === 'login' ? renderLogin()
    : state.screen === 'password' ? loginShell('Choose your password', 'You signed in with a temporary password. Choose your own to continue.', passwordForm(true))
    : state.screen === 'app' ? renderShell()
    : '<div class="loading" role="status">Loading…</div>';
}

/* ---------------------------------------------------------------- events */
async function submitLogin(form) {
  const l = state.login;
  if (l.busy) return;
  const email = form.elements.email.value.trim(), password = form.elements.password.value;
  if (!email || !password) { Object.assign(l, { email, error: 'Enter your email and password.', info: '' }); return render(); }
  Object.assign(l, { email, busy: true, error: '', info: '' }); render();
  try {
    await api.login(email, password);
    state.login = freshLogin();
    await boot();
  } catch (e) {
    Object.assign(l, { busy: false, error: e.message }); render();
  }
}

async function submitPassword(form) {
  const p = state.password;
  if (p.busy) return;
  const current = form.elements.current.value, next = form.elements.new.value, again = form.elements.again.value;
  const fail = (error) => { Object.assign(p, { busy: false, error, done: false }); state.screen === 'app' ? paintMain() : render(); };
  if (!current || !next) return fail('Fill in all three boxes.');
  if (next !== again) return fail('The two new passwords do not match.');
  Object.assign(p, { busy: true, error: '', done: false }); state.screen === 'app' ? paintMain() : render();
  try {
    await api.changePassword(current, next);
    if (state.screen === 'password') { state.password = freshPassword(); return boot(); }
    state.password = { busy: false, error: '', done: true }; paintMain();
  } catch (e) { fail(e.message); }
}

root.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const form = ev.target;
  syncAllDrafts();
  if (form.id === 'login-form') return submitLogin(form);
  if (form.id === 'password-form') return submitPassword(form);
  if (form.id === 'add-client') {
    const name = form.elements.name.value.trim();
    if (!name) return notify(null, 'Enter the company name.', { error: true });
    try {
      const { tenant } = await api.admin.createTenant(name);
      putTenant(tenant); notify(tenant.id, 'Client added. Connect their store, choose their countries, then add a login.');
      refreshSession();
    } catch (e) { notify(null, e.message, { error: true }); }
  } else if (form.dataset.form === 'add-user') {
    const id = form.dataset.tenant, email = form.elements.email.value.trim();
    if (!email) return notify(id, 'Enter an email address.', { error: true });
    try {
      const r = await api.admin.addUser(id, email);
      putTenant(r.tenant, true);
      notify(id, r.temporary_password ? '' : `${r.email} already has a login, so they keep their existing password.`, r.temporary_password ? { email: r.email, password: r.temporary_password } : {});
    } catch (e) { notify(id, e.message, { error: true }); }
  }
});

root.addEventListener('change', (ev) => {
  const el = ev.target;
  if (el.id === 'tenant') { state.tenantId = el.value; if (state.view !== 'sales') { state.view = 'sales'; render(); } loadReport(); }
  else if (el.id === 'period') {
    const range = periodRange(el.value);
    state.period = range ? { key: el.value, ...range } : { ...state.period, key: 'custom' };
    paintMain();
    if (range) loadReport();
  } else if (el.dataset.action === 'toggle-split') {
    syncDraft(el.dataset.tenant);
    state.admin.drafts[el.dataset.tenant].countries[Number(el.dataset.index)].split_by_region = el.checked;
  }
});

root.addEventListener('click', async (ev) => {
  const el = ev.target.closest('[data-action]');
  if (!el || el.tagName === 'INPUT') return;
  const a = el.dataset.action, id = el.dataset.tenant, admin = state.admin;
  syncAllDrafts(); // keep anything typed in the client cards before this action repaints them
  if (a === 'reload') location.reload();
  else if (a === 'retry') load();
  else if (a === 'nav') { state.view = el.dataset.view; state.password = freshPassword(); admin.notice = null; render(); load(); }
  else if (a === 'apply-period') {
    const from = document.getElementById('from').value, to = document.getElementById('to').value;
    if (!from || !to || to < from) { state.report = { status: 'error', data: null, error: 'Choose a start date and an end date that is not before it.' }; return paintMain(); }
    state.period = { key: 'custom', from, to }; loadReport();
  } else if (a === 'logout') {
    try { await api.logout(); } catch { /* either way, show the sign-in screen */ }
    state.session = null; token++; state.login = freshLogin(); state.report = { status: 'idle', data: null, error: '' };
    state.admin = { status: 'idle', tenants: [], drafts: {}, notice: null, error: '' }; setScreen('login');
  } else if (a === 'add-country') {
    const code = document.getElementById(`add-country-${id}`).value;
    if (!code) return;
    admin.drafts[id].countries.push({ country: code, split_by_region: code === 'US' });
    admin.notice = null; paintMain();
  } else if (a === 'remove-country') {
    admin.drafts[id].countries.splice(Number(el.dataset.index), 1); admin.notice = null; paintMain();
  } else if (a === 'save-tenant') {
    const d = admin.drafts[id];
    try {
      const { tenant } = await api.admin.updateTenant(id, { name: d.name, shop_domain: d.shop_domain, countries: d.countries });
      putTenant(tenant); notify(id, 'Saved.'); refreshSession();
    } catch (e) { notify(id, e.message, { error: true }); }
  } else if (a === 'reset-user') {
    try {
      const r = await api.admin.resetPassword(el.dataset.user);
      const owner = admin.tenants.find((t) => t.users.some((u) => u.id === el.dataset.user));
      await loadClientsQuietly(); notify(owner?.id ?? null, '', { email: r.email, password: r.temporary_password });
    } catch (e) { notify(el.closest('[data-tenant-card]')?.dataset.tenantCard ?? null, e.message, { error: true }); }
  } else if (a === 'toggle-user') {
    const card = el.closest('[data-tenant-card]')?.dataset.tenantCard ?? null;
    try { await api.admin.setDisabled(el.dataset.user, el.dataset.disabled !== '1'); await loadClientsQuietly(); notify(card, 'Updated.'); }
    catch (e) { notify(card, e.message, { error: true }); }
  } else if (a === 'remove-user') {
    try { const { tenant } = await api.admin.removeUser(id, el.dataset.user); putTenant(tenant, true); notify(id, 'Login removed from this client.'); }
    catch (e) { notify(id, e.message, { error: true }); }
  } else if (a === 'download-csv') {
    const report = state.report.data;
    if (!report || report.status !== 'ready') return;
    // A leading byte-order mark makes Excel read accented names correctly.
    const country = el.dataset.country || null; // set on a country's own button, absent on "all countries"
    const url = URL.createObjectURL(new Blob(['\ufeff', salesTaxCsv(report, country)], { type: 'text/csv;charset=utf-8' }));
    const link = Object.assign(document.createElement('a'), { href: url, download: csvFileName(report, country) });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else if (a === 'copy-temp') {
    const text = document.getElementById('temp-pass')?.textContent ?? '';
    try { await navigator.clipboard.writeText(text); el.textContent = 'Copied'; } catch { el.textContent = 'Select and copy'; }
  }
});

/** Re-read the client list (statuses changed) while keeping unsaved edits. */
async function loadClientsQuietly() {
  const { tenants } = await api.admin.tenants();
  tenants.forEach((t) => putTenant(t, true));
}

boot();
