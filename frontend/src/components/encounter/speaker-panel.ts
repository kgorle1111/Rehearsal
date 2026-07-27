// 10-frontend-spec.md §3.2 — <rehearsal-speaker-panel>. Two mirrored instances. Never reads
// the global store (§3.1): data comes in via properties.
import { t } from '../../i18n';
import type { TextBlock } from '../../types/api';

export interface PanelUtterance {
  text: TextBlock;
  index: number;
}

const NAME_KEY: Record<string, string> = {
  clinician: 'encounter.speaker.clinician',
  patient: 'encounter.speaker.patient',
};

export class RehearsalSpeakerPanel extends HTMLElement {
  private _speaker: 'clinician' | 'patient' = 'clinician';
  private _active = false;
  private _utterances: PanelUtterance[] = [];
  private heading = document.createElement('h2');
  private list = document.createElement('ol');

  static get observedAttributes() {
    return ['speaker', 'lang', 'active'];
  }

  connectedCallback() {
    this.className = 'rehearsal-speaker-panel';
    this.heading.className = 'rehearsal-speaker-panel__name';
    this.list.className = 'rehearsal-speaker-panel__transcript';
    this.list.setAttribute('role', 'log');
    this.appendChild(this.heading);
    this.appendChild(this.list);
    this.render();
  }

  attributeChangedCallback() {
    this._speaker = (this.getAttribute('speaker') as 'clinician' | 'patient') ?? 'clinician';
    this._active = this.getAttribute('active') === 'true';
    this.render();
  }

  set utterances(items: PanelUtterance[]) {
    this._utterances = items;
    this.renderList();
  }

  private render() {
    this.classList.toggle('rehearsal-speaker-panel--active', this._active);
    const key = NAME_KEY[this._speaker];
    this.heading.textContent = key ? t(key) : '';
    this.renderList();
  }

  private renderList() {
    const frag = document.createDocumentFragment();
    if (this._utterances.length === 0) {
      const empty = document.createElement('li');
      empty.className = 'rehearsal-speaker-panel__empty';
      empty.textContent = t('encounter.transcript.waiting');
      frag.appendChild(empty);
    }
    for (const u of this._utterances) {
      const li = document.createElement('li');
      li.lang = u.text.lang;
      li.textContent = u.text.text;
      frag.appendChild(li);
    }
    this.list.textContent = '';
    this.list.appendChild(frag);
  }
}

customElements.define('rehearsal-speaker-panel', RehearsalSpeakerPanel);
