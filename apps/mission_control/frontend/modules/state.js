import { preferences } from './storage.js';
class AppState extends EventTarget {
  constructor() {
    super();
    this.currentView = preferences.get('netlab.view') || 'overview';
    this.health = null;
    this.readiness = null;
    this.runtime = null;
    this.config = null;
    this.configHash = null;
    this.telemetry = null;
    this.jobs = [];
    this.events = [];
    this.polling = false;
  }

  set(key, value) {
    this[key] = value;
    this.dispatchEvent(new CustomEvent('change', { detail: { key, value } }));
    this.dispatchEvent(new CustomEvent(`change:${key}`, { detail: value }));
  }

  patch(values) {
    for (const [key, value] of Object.entries(values)) this[key] = value;
    this.dispatchEvent(new CustomEvent('change', { detail: { values } }));
  }

  navigate(view) {
    this.currentView = view;
    preferences.set('netlab.view', view);
    location.hash = view;
    this.dispatchEvent(new CustomEvent('navigate', { detail: view }));
  }
}

export const state = new AppState();
