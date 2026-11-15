// Small fetch client for the portal's own endpoints. No browser globals are touched at import time,
// so the same file runs in Node tests (a fake fetch is injected).

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

const GENERIC = 'Something went wrong. Please try again.';
const OFFLINE = 'We could not reach the server. Check your connection and try again.';

/**
 * @param {{ fetch?: typeof fetch, onUnauthorized?: () => void, onPasswordChangeRequired?: () => void }} opts
 */
export function createApi({ fetch: fetchImpl = globalThis.fetch?.bind(globalThis), onUnauthorized = () => {}, onPasswordChangeRequired = () => {} } = {}) {
  async function call(path, { session = true, ...init } = {}) {
    let res;
    try {
      res = await fetchImpl(path, { credentials: 'same-origin', ...init, headers: { Accept: 'application/json', ...(init.headers ?? {}) } });
    } catch {
      throw new ApiError(0, 'network', OFFLINE);
    }
    let data = null;
    try { data = await res.json(); } catch { /* non-JSON body: handled below */ }
    if (res.ok) {
      if (data === null || typeof data !== 'object') throw new ApiError(res.status, 'bad_response', GENERIC);
      return data;
    }
    const err = new ApiError(
      res.status,
      typeof data?.error?.code === 'string' ? data.error.code : 'error',
      typeof data?.error?.message === 'string' ? data.error.message : GENERIC,
    );
    // 401 on a data call means the session is gone. Sign-in form 401s ("wrong password") are handled by the caller.
    if (session && res.status === 401) onUnauthorized();
    if (session && err.code === 'password_change_required') onPasswordChangeRequired();
    throw err;
  }

  // Every change carries a header that a form on another site cannot send.
  const send = (method, path, body, extra = {}) =>
    call(path, { method, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'taxcart' }, body: JSON.stringify(body ?? {}), ...extra });

  const qs = (params) => {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) u.set(k, String(v));
    return u.toString();
  };
  const enc = encodeURIComponent;

  return {
    login: (email, password) => send('POST', '/api/auth/login', { email, password }, { session: false }),
    logout: () => send('POST', '/api/auth/logout', {}, { session: false }),
    changePassword: (current_password, new_password) => send('POST', '/api/auth/change-password', { current_password, new_password }, { session: false }),
    session: () => call('/api/session'),
    salesTax: ({ tenant, from, to }) => call(`/api/reports/sales-tax?${qs({ tenant, date_from: from, date_to: to })}`),
    admin: {
      tenants: () => call('/api/admin/tenants'),
      createTenant: (name) => send('POST', '/api/admin/tenants', { name }),
      updateTenant: (id, changes) => send('PUT', `/api/admin/tenants/${enc(id)}`, changes),
      addUser: (id, email) => send('POST', `/api/admin/tenants/${enc(id)}/users`, { email }),
      removeUser: (id, userId) => send('DELETE', `/api/admin/tenants/${enc(id)}/users/${enc(userId)}`),
      resetPassword: (userId) => send('POST', `/api/admin/users/${enc(userId)}/reset-password`),
      setDisabled: (userId, disabled) => send('PUT', `/api/admin/users/${enc(userId)}`, { disabled }),
    },
  };
}
