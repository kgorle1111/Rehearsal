// 10-frontend-spec.md §3.2 — <rehearsal-turn-state>. Owns the only animation in the encounter
// and writes the turn live region (§10.3). Announces only on genuine transitions.
import { t } from '../../i18n';

const LABEL_KEY: Record<string, string> = {
  clinician: 'encounter.turnState.clinician',
  patient: 'encounter.turnState.patient',
  yours: 'encounter.turnState.yours',
  processing: 'encounter.turnState.processing',
};

export class RehearsalTurnState extends HTMLElement {
  private lastAnnounced: string | null = null;
  private card = document.createElement('div');

  static get observedAttributes() {
    return ['state', 'direction', 'reduced-motion'];
  }

  connectedCallback() {
    this.card.className = 'rehearsal-turn-state__card';
    this.appendChild(this.card);
    this.render();
  }

  attributeChangedCallback() {
    this.render();
  }

  private announcerText(state: string, direction: string | null): string {
    if (state === 'yours') {
      const target =
        direction === 'en->es' ? t('encounter.lang.spanish') : t('encounter.lang.english');
      return t('encounter.turn.announce', { speaker: 'you', target });
    }
    return t('encounter.turn.announce', { speaker: state });
  }

  private render() {
    const state = this.getAttribute('state') ?? '';
    const direction = this.getAttribute('direction');
    const reducedMotion = this.getAttribute('reduced-motion') === 'true';

    const labelKey = LABEL_KEY[state];
    this.card.textContent = labelKey ? t(labelKey) : '';
    this.card.setAttribute('data-state', state);
    this.card.classList.toggle('rehearsal-turn-state__card--animated', !reducedMotion && state === 'yours');

    if (state && state !== this.lastAnnounced) {
      this.lastAnnounced = state;
      this.dispatchEvent(
        new CustomEvent('announce', {
          bubbles: true,
          detail: { text: this.announcerText(state, direction) },
        }),
      );
    }
  }
}

customElements.define('rehearsal-turn-state', RehearsalTurnState);
