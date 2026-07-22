const memory = new Map();

function backingStore() {
  try {
    const probe = '__netlab_storage_probe__';
    window.localStorage.setItem(probe, probe);
    window.localStorage.removeItem(probe);
    return window.localStorage;
  } catch {
    return null;
  }
}

const persistent = backingStore();

export const preferences = {
  get(key, fallback = null) {
    try {
      const value = persistent ? persistent.getItem(key) : memory.get(key);
      return value == null ? fallback : value;
    } catch {
      return memory.has(key) ? memory.get(key) : fallback;
    }
  },
  set(key, value) {
    const text = String(value);
    memory.set(key, text);
    try { persistent?.setItem(key, text); } catch { /* in-memory fallback remains */ }
  },
  remove(key) {
    memory.delete(key);
    try { persistent?.removeItem(key); } catch { /* no-op */ }
  },
  getJson(key, fallback = {}) {
    try { return JSON.parse(this.get(key, '')) || fallback; } catch { return fallback; }
  },
  setJson(key, value) { this.set(key, JSON.stringify(value)); },
};
