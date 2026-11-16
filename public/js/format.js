// Display helpers: pure functions that turn data into text or HTML. No browser globals at import time.
import { ICONS } from './icons.js';
import { COUNTRY_CODES, REGIONS } from './countries.js';

/** Escape text for HTML. Everything from the server or the person goes through this. */
export function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let names = null;
export function countryName(code) {
  try {
    names ??= new Intl.DisplayNames(['en-AU'], { type: 'region' });
    const name = names.of(code);
    return name && name !== code ? name : code;
  } catch { return code; }
}

export function regionName(country, region) {
  if (!region) return 'State not provided';
  return REGIONS[country]?.[region] ?? region;
}

let currencies = null;
/** ISO currency codes the browser knows, with the common ones first. */
export function currencyOptions() {
  if (currencies) return currencies;
  const common = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'NZD', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'RON', 'JPY', 'SGD'];
  let all = [];
  try { all = Intl.supportedValuesOf('currency'); } catch { /* older browser: common list only */ }
  currencies = [...common, ...all.filter((c) => !common.includes(c))];
  return currencies;
}

const EURO = ['AT', 'BE', 'BG', 'HR', 'CY', 'EE', 'FI', 'FR', 'DE', 'GR', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PT', 'SK', 'SI', 'ES'];
const LOCAL = { US: 'USD', GB: 'GBP', CA: 'CAD', AU: 'AUD', NZ: 'NZD', CH: 'CHF', NO: 'NOK', SE: 'SEK', DK: 'DKK', PL: 'PLN', CZ: 'CZK', HU: 'HUF', RO: 'RON', JP: 'JPY', SG: 'SGD' };
/** A sensible starting filing currency for a country. Staff can change it. Null means the store's currency. */
export const defaultFilingCurrency = (country) => (EURO.includes(country) ? 'EUR' : LOCAL[country] ?? null);

export const countryOptions = () => COUNTRY_CODES.map((code) => ({ code, name: countryName(code) })).sort((a, b) => a.name.localeCompare(b.name));

/** "1234.5000" with currency "USD" becomes "USD 1,234.50". Unknown currency shows a plain number. */
export function formatMoney(value, currency) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '–';
  if (currency) {
    try { return new Intl.NumberFormat('en-AU', { style: 'currency', currency, currencyDisplay: 'code' }).format(n); } catch { /* fall through */ }
  }
  return new Intl.NumberFormat('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);
}

/** "0.062500" becomes "6.25%". */
export function formatRate(rate) {
  const n = Number(rate);
  if (!Number.isFinite(n)) return '';
  return `${new Intl.NumberFormat('en-AU', { maximumFractionDigits: 4 }).format(n * 100)}%`;
}

export function formatDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '');
  if (!m) return '';
  return new Intl.DateTimeFormat('en-AU', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])));
}

/* ---------------------------------------------------------------- periods (UTC days) */
const iso = (d) => d.toISOString().slice(0, 10);
const utc = (y, m, d) => new Date(Date.UTC(y, m, d));

export const PERIODS = [
  ['this_month', 'This month'], ['last_month', 'Last month'], ['this_quarter', 'This quarter'],
  ['last_quarter', 'Last quarter'], ['this_year', 'This year'], ['custom', 'Custom dates'],
];

/** The first and last day of a named period, as YYYY-MM-DD. */
export function periodRange(key, today = new Date()) {
  const y = today.getUTCFullYear(), m = today.getUTCMonth(), q = Math.floor(m / 3) * 3;
  switch (key) {
    case 'this_month': return { from: iso(utc(y, m, 1)), to: iso(utc(y, m + 1, 0)) };
    case 'last_month': return { from: iso(utc(y, m - 1, 1)), to: iso(utc(y, m, 0)) };
    case 'this_quarter': return { from: iso(utc(y, q, 1)), to: iso(utc(y, q + 3, 0)) };
    case 'last_quarter': return { from: iso(utc(y, q - 3, 1)), to: iso(utc(y, q, 0)) };
    case 'this_year': return { from: iso(utc(y, 0, 1)), to: iso(utc(y, 11, 31)) };
    default: return null;
  }
}

/* ---------------------------------------------------------------- shared pieces */
export const emptyState = (text) => `<div class="empty-state">${esc(text)}</div>`;
export const errorState = (message) => `<div class="error-state" role="alert"><p>${esc(message)}</p><button class="btn-inline" data-action="retry">Try again</button></div>`;
const cardHead = (icon, title, sub, right = '') => `<div class="card-head"><div class="card-head-left"><div class="card-icon">${icon}</div><div><div class="card-title">${esc(title)}</div><div class="card-sub">${esc(sub)}</div></div></div>${right}</div>`;
const td = (label, html, cls = '') => `<td data-label="${esc(label)}"${cls ? ` class="${cls}"` : ''}>${html}</td>`;

/* ---------------------------------------------------------------- sales and tax report */
const marketplaceRow = (amount, currency) => (Number(amount) > 0 ? `<tr class="sub-row">
    ${td('Tax', '<span class="sub-mark">Collected and remitted by a marketplace</span>')}
    ${td('', '')}${td('', '')}
    ${td('Tax collected', esc(formatMoney(amount, currency)), 'right num')}
    ${td('', '')}${td('', '')}</tr>` : '');

function componentRows(components, currency) {
  return components.map((c) => `<tr class="sub-row">
    ${td('Tax', `<span class="sub-mark">${esc(c.title)}</span> <span class="muted">${esc(formatRate(c.rate))}</span>`)}
    ${td('', '')}
    ${td('Taxable sales', `<span class="muted">${esc(formatMoney(c.taxable_sales, currency))} taxable</span>`, 'right num')}
    ${td('Tax collected', esc(formatMoney(c.tax, currency)), 'right num')}
    ${td('', '')}${td('', '')}</tr>`).join('');
}

/** A strip above a part charged in a currency other than the filing currency. */
const otherCurrencyNote = (c, part) => `<div class="currency-note"><span class="status-chip approaching">Not converted</span>
  Orders charged in ${esc(part.currency ?? 'an unknown currency')}, shown as charged. Not included in the ${esc(c.filing_currency ?? 'filing currency')} figures above.</div>`;

function splitPart(c, part) {
  const cur = part.currency;
  const rows = part.regions.map((r) => `<tr>
    ${td('State / region', `<strong>${esc(regionName(c.country, r.region))}</strong>${r.region ? '' : ' <span class="status-chip approaching">Needs review</span>'}`)}
    ${td('Orders', esc(r.orders), 'right num')}
    ${td('Net sales', esc(formatMoney(r.net_sales, cur)), 'right num')}
    ${td('Tax collected', esc(formatMoney(r.tax_charged, cur)), 'right num')}
    ${td('Tax refunded', esc(formatMoney(r.refunded_tax, cur)), 'right num')}
    ${td('Net tax', `<strong>${esc(formatMoney(r.net_tax, cur))}</strong>`, 'right num')}</tr>${componentRows(r.components, cur)}${marketplaceRow(r.marketplace_tax, cur)}`).join('');
  return part.regions.length
    ? `<div class="table-card"><table class="data"><thead><tr><th>State / region</th><th class="right">Orders</th><th class="right">Net sales</th><th class="right">Tax collected</th><th class="right">Tax refunded</th><th class="right">Net tax</th></tr></thead><tbody>${rows}</tbody></table></div>`
    : '<div class="card-body-note">No sales in this period.</div>';
}

function singlePart(c, part) {
  const cur = part.currency;
  const rows = part.components.map((k) => `<tr>
    ${td('Tax type', `<strong>${esc(k.title)}</strong>`)}
    ${td('Rate', esc(formatRate(k.rate)), 'right num')}
    ${td('Taxable sales', esc(formatMoney(k.taxable_sales, cur)), 'right num')}
    ${td('Tax collected', esc(formatMoney(k.tax, cur)), 'right num')}</tr>`).join('');
  const table = part.components.length
    ? `<div class="table-card"><table class="data"><thead><tr><th>Tax type</th><th class="right">Rate</th><th class="right">Taxable sales</th><th class="right">Tax collected</th></tr></thead><tbody>${rows}</tbody></table></div>`
    : `<div class="card-body-note">${part.orders ? 'No tax was collected on these sales.' : 'No sales in this period.'}</div>`;
  const foot = part.orders
    ? `<div class="card-foot">${esc(part.orders)} ${part.orders === 1 ? 'order' : 'orders'} · Net sales ${esc(formatMoney(part.net_sales, cur))} · Tax refunded ${esc(formatMoney(part.refunded_tax, cur))} · Net tax ${esc(formatMoney(part.net_tax, cur))}${Number(part.marketplace_tax) > 0 ? ` · ${esc(formatMoney(part.marketplace_tax, cur))} collected and remitted by a marketplace` : ''}</div>`
    : '';
  return table + foot;
}

function countryCard(c) {
  const [main, ...others] = c.parts;
  const body = (part) => (c.split_by_region ? splitPart(c, part) : singlePart(c, part));
  const extra = others.map((p) => otherCurrencyNote(c, p) + body(p)).join('');
  const sub = `${c.split_by_region ? 'By state or region' : 'By tax type and rate'} · Filed in ${c.filing_currency ?? 'store currency'}`;
  const right = `<div class="card-head-right"><button class="btn-inline" data-action="download-csv" data-country="${esc(c.country)}" aria-label="Download ${esc(countryName(c.country))} as CSV">Download CSV</button>
    <div class="card-total"><div class="card-total-num num">${esc(formatMoney(main.net_tax, main.currency))}</div><div class="card-sub">Net tax${others.length ? ` · plus ${others.map((p) => esc(formatMoney(p.net_tax, p.currency))).join(', ')} not converted` : ''}</div></div></div>`;
  return `<section class="card list-card" data-country="${esc(c.country)}">${cardHead(c.split_by_region ? ICONS.flag : ICONS.globe, countryName(c.country), sub, right)}${body(main)}${extra}</section>`;
}

function reviewCard(review) {
  const ex = review.exceptions;
  const list = (title, help, items) => `<div class="review-block"><div class="review-title">${esc(title)} <span class="status-chip ${items.length ? 'approaching' : 'registered'}">${items.length}</span></div><div class="muted">${esc(help)}</div>${
    items.length ? `<div class="review-items">${items.map((o) => `<span class="order-chip">${esc(o.name ?? o.order_id)}${o.country ? ` · ${esc(o.country)}${o.province ? `-${esc(o.province)}` : ''}` : ''}</span>`).join('')}</div>` : ''}</div>`;
  const outside = review.outside_selection.length
    ? `<div class="review-block"><div class="review-title">Sales outside the selected countries</div><div class="muted">Not in this client's report. Add the country if it should be.</div><div class="review-items">${review.outside_selection.map((o) => `<span class="order-chip">${esc(countryName(o.country))}: ${esc(o.orders)} ${o.orders === 1 ? 'order' : 'orders'}, ${esc(formatMoney(o.net_sales, o.currency))}</span>`).join('')}</div></div>`
    : '';
  return `<section class="card list-card review-card">${cardHead(ICONS.shield, 'For review', 'Visible to Taxcart staff only')}
    ${list('No usable destination', 'The order has no country, or no state where one is needed, so it cannot be assigned.', ex.missing_destination)}
    ${list('No tax charged', 'Full destination and not exempt, but no tax. May be correct where the client is not registered.', ex.untaxed)}
    ${list('Refund does not add up', 'The tax reduction Shopify reports is not explained by the refunds on file.', ex.refund_mismatch)}
    ${outside}</section>`;
}

export function salesTaxReport(report) {
  if (report.status === 'not_set_up') {
    const what = report.missing.includes('data_source') ? 'Your sales data is not connected yet.' : 'Your countries have not been chosen yet.';
    return emptyState(`${what} Your Taxcart representative is finishing the setup.`);
  }
  const totals = report.totals_by_currency;
  const period = `${formatDate(report.period.date_from)} to ${formatDate(report.period.date_to)}`;
  const chip = (num, label) => `<div class="hero-chip"><div class="hero-chip-num num">${esc(num)}</div><div class="hero-chip-label">${esc(label)}</div></div>`;
  const orders = totals.reduce((n, t) => n + t.orders, 0);
  let hero;
  if (totals.length <= 1) {
    const t = totals[0] ?? { currency: report.store_currency, net_tax: '0', net_sales: '0', refunded_tax: '0' };
    hero = `<div class="hero-stat"><div class="hero-stat-left"><div class="hero-stat-label">Net tax collected</div>
      <div class="hero-stat-num num">${esc(formatMoney(t.net_tax, t.currency))}</div>
      <div class="hero-stat-sub">${esc(period)}, after refunds</div></div>
      <div class="hero-stat-chips">${chip(formatMoney(t.net_sales, t.currency), 'Net sales')}${chip(orders, orders === 1 ? 'Order' : 'Orders')}${chip(formatMoney(t.refunded_tax, t.currency), 'Tax refunded')}</div></div>`;
  } else {
    // Different currencies are never added together, so each gets its own figure.
    hero = `<div class="hero-stat"><div class="hero-stat-left"><div class="hero-stat-label">Net tax collected, by currency</div>
      <div class="hero-multi">${totals.map((t) => `<div class="hero-multi-num num">${esc(formatMoney(t.net_tax, t.currency))}</div>`).join('')}</div>
      <div class="hero-stat-sub">${esc(period)}, after refunds. Each currency is shown as charged, not converted.</div></div>
      <div class="hero-stat-chips">${chip(orders, orders === 1 ? 'Order' : 'Orders')}</div></div>`;
  }
  const mp = totals.filter((t) => Number(t.marketplace_tax) > 0);
  const marketplace = mp.length ? `<div class="sync-note">${esc(mp.map((t) => formatMoney(t.marketplace_tax, t.currency)).join(' and '))} of the tax shown was collected and remitted by a marketplace on your behalf. It is included in the figures below and marked where it applies.</div>` : '';
  const unconverted = report.countries.some((c) => c.parts.length > 1)
    ? '<div class="sync-note stale">Some orders were charged in a currency other than the country\'s filing currency. They are shown separately as charged and marked "Not converted".</div>' : '';
  const cards = report.countries.map(countryCard).join('');
  const note = `<p class="foot-note">Periods use UTC dates. Sales are counted on the order date and refunds on the refund date. Amounts in a filing currency other than the store's are what the customer was charged, as recorded by Shopify. Taxable sales are worked back from the tax collected, so they can differ from net sales by a few cents.</p>`;
  return hero + marketplace + unconverted + cards + (report.review ? reviewCard(report.review) : '') + note;
}

/* ---------------------------------------------------------------- download */
// Text from outside (tax names, region codes) could start with a character a spreadsheet
// would run as a formula. A leading apostrophe makes it plain text.
const safeText = (v) => { const t = String(v ?? ''); return /^[=+\-@\t\r]/.test(t) ? `'${t}` : t; };
const cell = (v) => { const t = String(v ?? ''); return /[",\r\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t; };
// "8729.8000" -> "8729.80"; keeps extra decimals only when they carry value.
const amount = (v) => { const n = Number(v); if (v === '' || v == null || !Number.isFinite(n)) return ''; const t = String(v); const m = /^(-?\d+)(?:\.(\d+))?$/.exec(t); if (!m) return t; const dec = (m[2] ?? '').replace(/0+$/, ''); return `${m[1]}.${dec.padEnd(2, '0')}`; };
const percent = (rate) => { const n = Number(rate); return Number.isFinite(n) ? String(Number((n * 100).toFixed(4))) : ''; };

export const CSV_COLUMNS = ['Country', 'Country code', 'State / region', 'Row type', 'Tax name', 'Tax rate %', 'Orders', 'Net sales', 'Taxable sales', 'Tax collected', 'Tax refunded', 'Net tax', 'Of which collected by a marketplace', 'Currency', 'Filing currency', 'In filing currency', 'Period from', 'Period to'];

/**
 * The report as CSV text, for every country or just one. For each country and currency there is a
 * "Country total" row, a "Region total" row per state for countries reported by region, and a "Tax"
 * row for each tax type and rate. Filter on "Row type", and on "Currency", before adding a column
 * up: totals and their breakdown are both listed, and amounts in different currencies must not be
 * added together.
 */
export function salesTaxCsv(report, country = null) {
  const { date_from: from, date_to: to } = report.period;
  const rows = [CSV_COLUMNS];
  for (const c of report.countries) {
    if (country && c.country !== country) continue;
    for (const part of c.parts) {
      const tail = [part.currency, c.filing_currency, part.in_filing_currency ? 'Yes' : 'No, not converted', from, to];
      const total = (region, type, x) => rows.push([countryName(c.country), c.country, region, type, '', '', x.orders, amount(x.net_sales), '', amount(x.tax_charged), amount(x.refunded_tax), amount(x.net_tax), amount(x.marketplace_tax), ...tail]);
      const taxes = (region, list) => list.forEach((k) => rows.push([countryName(c.country), c.country, region, 'Tax', safeText(k.title), percent(k.rate), '', '', amount(k.taxable_sales), amount(k.tax), '', '', '', ...tail]));
      total('', 'Country total', part);
      if (c.split_by_region) {
        for (const r of part.regions) {
          const name = safeText(regionName(c.country, r.region));
          total(name, 'Region total', r);
          taxes(name, r.components);
        }
      } else taxes('', part.components);
    }
  }
  return rows.map((r) => r.map(cell).join(',')).join('\r\n') + '\r\n';
}

export function csvFileName(report, country = null) {
  const slug = report.tenant.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'client';
  return `taxcart-sales-tax-${slug}-${country ? `${country.toLowerCase()}-` : ''}${report.period.date_from}-to-${report.period.date_to}.csv`;
}

/* ---------------------------------------------------------------- staff: clients */
function userStatus(u) {
  if (u.disabled) return '<span class="status-chip ended">Disabled</span>';
  if (u.must_change_password) return '<span class="status-chip approaching">Awaiting first sign-in</span>';
  return '<span class="status-chip registered">Active</span>';
}

export function tempPasswordNotice(n) {
  return `<div class="temp-note" role="status"><div><strong>Temporary password for ${esc(n.email)}</strong><div class="muted">Shown once. Send it to them securely; they choose their own at first sign-in.</div></div><code class="temp-pass" id="temp-pass">${esc(n.password)}</code><button class="btn-inline" data-action="copy-temp">Copy</button></div>`;
}

export function clientCard(t, draft, options, notice) {
  const id = esc(t.id);
  const countries = draft.countries.map((c, i) => `<div class="country-row">
      <span class="country-name">${esc(countryName(c.country))} <span class="muted">${esc(c.country)}</span></span>
      <label class="check"><input type="checkbox" data-action="toggle-split" data-tenant="${id}" data-index="${i}" ${c.split_by_region ? 'checked' : ''}> By state or region</label>
      <label class="check">Filed in <select class="filter-select small-select" data-action="set-currency" data-tenant="${id}" data-index="${i}" aria-label="Filing currency for ${esc(countryName(c.country))}">
        <option value="" ${c.filing_currency ? '' : 'selected'}>Store currency</option>${currencyOptions().map((code) => `<option value="${esc(code)}" ${c.filing_currency === code ? 'selected' : ''}>${esc(code)}</option>`).join('')}</select></label>
      <button class="link-btn" data-action="remove-country" data-tenant="${id}" data-index="${i}">Remove</button></div>`).join('');
  const taken = new Set(draft.countries.map((c) => c.country));
  const select = `<select class="filter-select" id="add-country-${id}" aria-label="Country to add"><option value="">Choose a country…</option>${options.filter((o) => !taken.has(o.code)).map((o) => `<option value="${esc(o.code)}">${esc(o.name)}</option>`).join('')}</select>`;
  const users = t.users.map((u) => `<div class="user-row"><span class="user-email">${esc(u.email)}</span>${userStatus(u)}
      <span class="user-actions"><button class="link-btn" data-action="reset-user" data-user="${esc(u.id)}" data-email="${esc(u.email)}">Reset password</button>
      <button class="link-btn" data-action="toggle-user" data-user="${esc(u.id)}" data-disabled="${u.disabled ? '1' : '0'}">${u.disabled ? 'Enable' : 'Disable'}</button>
      <button class="link-btn danger" data-action="remove-user" data-tenant="${id}" data-user="${esc(u.id)}">Remove</button></span></div>`).join('');
  const msg = notice?.tenant === t.id && notice.text ? `<div class="${notice.error ? 'form-error' : 'form-info'}" role="status">${esc(notice.text)}</div>` : '';
  const temp = notice?.tenant === t.id && notice.password ? tempPasswordNotice(notice) : '';
  return `<section class="card list-card client-card" data-tenant-card="${id}">
    ${cardHead(ICONS.clients, t.name, `${t.countries.length} ${t.countries.length === 1 ? 'country' : 'countries'} · ${t.users.length} ${t.users.length === 1 ? 'login' : 'logins'}${t.shop_domain ? '' : ' · no sales data connected'}`)}
    <div class="client-body">${msg}${temp}
      <div class="form-grid">
        <div><label class="field-label" for="name-${id}">Company name</label><input class="text-input" id="name-${id}" value="${esc(draft.name)}" maxlength="120"></div>
        <div><label class="field-label" for="shop-${id}">Shopify store</label><input class="text-input" id="shop-${id}" value="${esc(draft.shop_domain)}" placeholder="store-name.myshopify.com" autocomplete="off"></div>
      </div>
      <div class="field-label">Countries in this client's report</div>
      <div class="country-list">${countries || '<div class="muted">No countries chosen yet.</div>'}</div>
      <div class="inline-form">${select}<button class="btn-inline" data-action="add-country" data-tenant="${id}">Add country</button></div>
      <div class="save-row"><button class="btn btn-primary btn-fit" data-action="save-tenant" data-tenant="${id}">Save changes</button></div>
      <div class="field-label logins-label">Logins</div>
      <div class="user-list">${users || '<div class="muted">No one can sign in for this client yet.</div>'}</div>
      <form class="inline-form" data-form="add-user" data-tenant="${id}" novalidate><input class="text-input" name="email" type="email" placeholder="person@company.com" aria-label="Email for a new login" autocomplete="off"><button class="btn-inline" type="submit">Add login</button></form>
    </div></section>`;
}
