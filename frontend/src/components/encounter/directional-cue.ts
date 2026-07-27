// 10-frontend-spec.md §3.2 — <rehearsal-directional-cue>. Largest text on the encounter screen.
// Text, not icon (09-ui-ux.md §5.3). A wrong cue is worse than none, so unknown direction hides.
import { t } from '../../i18n';

export class RehearsalDirectionalCue extends HTMLElement {
  static get observedAttributes() {
    return ['direction'];
  }

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback() {
    this.render();
  }

  private render() {
    const direction = this.getAttribute('direction');
    if (direction !== 'en->es' && direction !== 'es->en') {
      this.textContent = '';
      this.hidden = true;
      return;
    }
    this.hidden = false;
    this.textContent = direction === 'en->es' ? t('encounter.cue.toSpanish') : t('encounter.cue.toEnglish');
  }
}

customElements.define('rehearsal-directional-cue', RehearsalDirectionalCue);
