// 10-frontend-spec.md §3.2 — <rehearsal-transcript>. Below 100 items, renders every item
// un-virtualised (§12.4) — the vertical slice does not carry >100-turn sessions.
import { t } from '../../i18n';
import type { TextBlock } from '../../types/api';

export interface TranscriptItem {
  text: TextBlock;
  index: number;
}

export class RehearsalTranscript extends HTMLElement {
  private _items: TranscriptItem[] = [];
  // role="log" belongs on a plain container: ARIA's role-on-<ol> rules forbid it there (it would
  // also strip the <ol>'s implicit "list" role, which axe-core's aria-allowed-role/listitem rules
  // both flag). The log role wraps the list instead.
  private logRegion = document.createElement('div');
  private list = document.createElement('ol');

  connectedCallback() {
    this.logRegion.setAttribute('role', 'log');
    this.list.className = 'rehearsal-transcript__list';
    this.logRegion.appendChild(this.list);
    this.appendChild(this.logRegion);
    this.render();
  }

  set items(v: TranscriptItem[]) {
    this._items = v;
    this.render();
  }

  private render() {
    if (!this.isConnected) return;
    const frag = document.createDocumentFragment();
    if (this._items.length === 0) {
      const empty = document.createElement('li');
      empty.textContent = t('encounter.transcript.empty');
      frag.appendChild(empty);
    }
    for (const item of this._items) {
      const li = document.createElement('li');
      li.lang = item.text.lang;
      li.textContent = item.text.text;
      frag.appendChild(li);
    }
    this.list.textContent = '';
    this.list.appendChild(frag);
  }
}

customElements.define('rehearsal-transcript', RehearsalTranscript);
