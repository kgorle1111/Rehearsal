// 10-frontend-spec.md §3.2, §6.5 — <rehearsal-connection-status>.
import { t } from '../../i18n';
import type { ConnectionStatus } from '../../transport/ws';

export class RehearsalConnectionStatus extends HTMLElement {
  private _status: ConnectionStatus = { kind: 'connecting' };

  set status(s: ConnectionStatus) {
    this._status = s;
    this.render();
  }

  connectedCallback() {
    this.render();
  }

  private render() {
    const s = this._status;
    if (s.kind === 'open') {
      this.hidden = true;
      this.textContent = '';
      return;
    }
    this.hidden = false;
    if (s.kind === 'connecting') this.textContent = t('encounter.connection.connecting');
    else if (s.kind === 'resyncing') this.textContent = t('encounter.connection.resyncing', { n: s.to - s.from });
    else if (s.kind === 'reconnecting') this.textContent = t('encounter.connection.reconnecting');
    else this.textContent = s.reason;
  }
}

customElements.define('rehearsal-connection-status', RehearsalConnectionStatus);
