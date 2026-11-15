// Inline SVG icons (no external requests). Colours come from the surrounding text colour unless noted.
const s = (size, body, stroke = 'currentColor', w = 2) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="${w}" aria-hidden="true">${body}</svg>`;

export const ICONS = {
  mark: s(15, '<path d="M4 7h16M4 12h16M4 17h10"/>', '#fff', 2.4),
  mail: s(15, '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 6-10 7L2 6"/>'),
  key: s(15, '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6M15.5 7.5 18 10M18.5 4.5 21 7"/>'),
  sales: s(16, '<path d="M3 3v18h18"/><path d="M7 15l4-6 4 3 5-8"/>'),
  clients: s(16, '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>'),
  globe: s(16, '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10Z"/>'),
  flag: s(16, '<path d="M4 22V4a1 1 0 0 1 1-1h14l-3 6 3 6H5"/>'),
  shield: s(16, '<path d="M12 2 4 5v6c0 5.2 3.4 9.5 8 11 4.6-1.5 8-5.8 8-11V5l-8-3Z"/><path d="m9 12 2 2 4-4"/>'),
  store: s(16, '<path d="M3 9l1.5-5h15L21 9"/><path d="M3 9v11h18V9"/><path d="M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/>'),
  logout: s(15, '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>'),
};
