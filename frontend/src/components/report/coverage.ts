// 09-ui-ux.md §5.5.3 — coverage block: how many turns were scored in full vs critical-only
// vs not at all, plus which error categories weren't assessed this session.
import { t } from '../../i18n';
import type { CoverageBlock } from '../../types/api';

export function renderCoverage(c: CoverageBlock): HTMLElement {
  const section = document.createElement('section');
  const h = document.createElement('h2');
  h.textContent = t('report.coverage.title');
  const ul = document.createElement('ul');
  for (const text of [
    t('report.coverage.scoredFull', { n: c.turnsScoredFull }),
    t('report.coverage.extractorOnly', { n: c.turnsScoredExtractorOnly }),
    t('report.coverage.unscored', { n: c.turnsUnscored }),
  ]) {
    const li = document.createElement('li');
    li.textContent = text;
    ul.appendChild(li);
  }
  section.append(h, ul);
  if (c.notAssessedCategories.length > 0) {
    const p = document.createElement('p');
    const list = c.notAssessedCategories.map((k) => t(`finding.kind.${k}`)).join(', ');
    p.textContent = t('report.coverage.notAssessed', { list });
    section.appendChild(p);
  }
  return section;
}
