// 10-frontend-spec.md §3.2 — <rehearsal-degrade-banner>. Hidden only at L0; never dismissible.
import { t } from '../../i18n';

export class RehearsalDegradeBanner extends HTMLElement {
  static get observedAttributes() {
    return ['level', 'reason'];
  }

  connectedCallback() {
    this.setAttribute('role', 'status');
    this.render();
  }

  attributeChangedCallback() {
    this.render();
  }

  private render() {
    const level = Number(this.getAttribute('level') ?? 0);
    const reason = this.getAttribute('reason') ?? '';
    this.hidden = level <= 0;
    this.textContent = this.hidden ? '' : t('encounter.degrade.banner', { reason });
  }
}

customElements.define('rehearsal-degrade-banner', RehearsalDegradeBanner);
