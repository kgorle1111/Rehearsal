// 09-ui-ux.md §5.5.4 — turn-by-turn, collapsible per turn. Uses native <details>/<summary> so
// expand/collapse is keyboard-operable with zero extra script (ponytail: native platform feature
// beats a custom disclosure widget). Source and rendering are always both visible per §5.4 —
// never only the error.
import { t } from '../../i18n';
import type { TurnView } from '../../types/api';

export function renderTurns(turns: TurnView[]): HTMLElement {
  const list = document.createElement('div');
  list.className = 'stack';
  if (turns.length === 0) {
    const p = document.createElement('p');
    p.textContent = t('report.turns.empty');
    list.appendChild(p);
    return list;
  }
  for (const turn of turns) {
    const details = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = t('encounter.turn.label', { n: turn.index + 1 });
    details.appendChild(summary);

    if (turn.source) {
      const src = document.createElement('p');
      src.lang = turn.source.lang;
      src.textContent = turn.source.text;
      details.appendChild(src);
    }
    if (turn.rendering) {
      const rend = document.createElement('p');
      rend.lang = turn.rendering.lang;
      rend.textContent = turn.rendering.text;
      details.appendChild(rend);
    }

    const verdict = turn.verdict;
    if (!verdict) {
      const p = document.createElement('p');
      p.textContent = t('verdict.notScored');
      details.appendChild(p);
    } else if (verdict.findings.length === 0) {
      const p = document.createElement('p');
      p.textContent = t('verdict.clean');
      details.appendChild(p);
    } else {
      const ul = document.createElement('ul');
      for (const f of verdict.findings) {
        const li = document.createElement('li');
        li.textContent = `${t(`finding.severity.${f.severity}`)} · ${t(`finding.kind.${f.kind}`)} — ${f.note}`;
        ul.appendChild(li);
      }
      details.appendChild(ul);
      if (verdict.status !== 'complete') {
        const p = document.createElement('p');
        p.textContent = t(verdict.status === 'partial' ? 'verdict.partial' : 'verdict.graderUnavailable');
        details.appendChild(p);
      }
    }
    list.appendChild(details);
  }
  return list;
}
