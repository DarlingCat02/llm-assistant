let currentLang = 'en';
let translations = {};

export async function initI18n() {
  // Priority: localStorage -> backend config -> default en
  const saved = localStorage.getItem('lang');
  if (saved && ['en','ru'].includes(saved)) {
    currentLang = saved;
  } else {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/config');
      if (res.ok) {
        const cfg = await res.json();
        if (cfg.language && ['en','ru'].includes(cfg.language)) {
          currentLang = cfg.language;
          localStorage.setItem('lang', currentLang);
        } else {
          // default en for first launch
          currentLang = 'en';
          localStorage.setItem('lang', 'en');
        }
      }
    } catch {}
  }
  await loadTranslations(currentLang);
  document.documentElement.lang = currentLang;
  applyTranslations();
}

async function loadTranslations(lang) {
  try {
    const res = await fetch(`/src/locales/${lang}.json`);
    if (res.ok) translations = await res.json();
    else {
      const r = await fetch(`./src/locales/${lang}.json`);
      translations = await r.json();
    }
  } catch {
    // fallback inline fetch via vite import
    try {
      const mod = await import(`./locales/${lang}.json`);
      translations = mod.default || mod;
    } catch {}
  }
}

export function t(key, params = {}) {
  let str = translations[key] ?? key;
  for (const [k,v] of Object.entries(params)) {
    str = str.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
  }
  return str;
}

export function getLang() { return currentLang; }

export async function setLanguage(lang) {
  if (!['en','ru'].includes(lang)) return;
  currentLang = lang;
  localStorage.setItem('lang', lang);
  document.documentElement.lang = lang;
  await loadTranslations(lang);
  applyTranslations();
  // Language is persisted via Settings -> Save (PUT /api/config with full config)
  // No immediate PUT here to avoid partial-update bug on old backend
  // Re-apply dynamic parts
  try {
    // Update placeholders that were set via JS
    const input = document.getElementById('message-input');
    if (input) input.placeholder = t('chat.input.placeholder');
    const memSearch = document.getElementById('memory-search-input');
    if (memSearch) memSearch.placeholder = t('memory.search.placeholder');
    const memAdd = document.getElementById('memory-add-input');
    if (memAdd) memAdd.placeholder = t('memory.add.placeholder');
    const apiKey = document.getElementById('api-key-input');
    if (apiKey) apiKey.placeholder = t('settings.apiKey.placeholder');
  } catch {}
}

function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    const attr = el.getAttribute('data-i18n-attr');
    const val = t(key);
    if (attr) el.setAttribute(attr, val);
    else el.textContent = val;
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.getAttribute('data-i18n-title'));
  });
}
