// 09-ui-ux.md §5.5 — session report. Static render from a fetched SessionReport: unlike the
// encounter, nothing here is live, so there's no effect() subscription to tear down.
import { t, formatPercent } from '../i18n';
import { settings, updateSettings } from '../store/settings';
import type { SessionReport } from '../types/api';
import { renderCoverage } from '../components/report/coverage';
import { renderTurns } from '../components/report/turns';
import { renderSkillChart, countFindingsByKind, type ChartMode } from '../components/report/skill-chart';

const CHART_MODES: ChartMode[] = ['radar', 'bars', 'table'];

export function mountReportView(container: HTMLElement, report: SessionReport): () => void {
  container.innerHTML = '';
  container.className = 'page stack';

  const header = document.createElement('header');
  const h1 = document.createElement('h1');
  h1.textContent = t('report.title');
  const meta = document.createElement('p');
  meta.textContent = `${t('report.header.turns')}: ${report.coverage.turnsTotal}`;
  header.append(h1, meta);

  const glance = document.createElement('section');
  const glanceH = document.createElement('h2');
  glanceH.textContent = t('report.glance.title');
  const glanceP = document.createElement('p');
  glanceP.textContent = t('report.glance.summary', {
    critical: report.totals.critical,
    turns: report.coverage.turnsTotal,
  });
  glance.append(glanceH, glanceP);

  const coverage = renderCoverage(report.coverage);

  const skillsSection = document.createElement('section');
  const skillsH = document.createElement('h2');
  skillsH.textContent = t('report.skills.title');
  const toggleGroup = document.createElement('div');
  toggleGroup.setAttribute('role', 'group');
  toggleGroup.setAttribute('aria-label', t('report.skills.title'));
  const chartHost = document.createElement('div');
  const counts = countFindingsByKind(report.turns);

  function renderChart() {
    chartHost.innerHTML = '';
    chartHost.appendChild(renderSkillChart(counts, settings.peek().chartMode));
    for (const el of Array.from(toggleGroup.children)) {
      const btn = el as HTMLButtonElement;
      btn.setAttribute('aria-pressed', String(btn.dataset.mode === settings.peek().chartMode));
    }
  }

  for (const mode of CHART_MODES) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = t(`report.skills.mode.${mode}`);
    btn.dataset.mode = mode;
    btn.addEventListener('click', () => {
      updateSettings({ chartMode: mode });
      renderChart();
    });
    toggleGroup.appendChild(btn);
  }
  skillsSection.append(skillsH, toggleGroup, chartHost);
  renderChart();

  const turnsSection = document.createElement('section');
  const turnsH = document.createElement('h2');
  turnsH.textContent = t('report.turns.title');
  turnsSection.append(turnsH, renderTurns(report.turns));

  const confidenceSection = document.createElement('section');
  const confH = document.createElement('h2');
  confH.textContent = t('report.confidence.title');
  const confP = document.createElement('p');
  confP.textContent = report.confidence.measured
    ? t('report.confidence.measured', {
        kappa: report.confidence.kappa ?? 0,
        recall:
          report.confidence.criticalRecall != null ? formatPercent(report.confidence.criticalRecall) : '—',
      })
    : t('report.confidence.notMeasured');
  confidenceSection.append(confH, confP);

  const exportSection = document.createElement('footer');
  for (const key of ['pdf', 'json', 'delete'] as const) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = t(`report.export.${key}`);
    exportSection.appendChild(btn);
  }

  container.append(header, glance, coverage, skillsSection, turnsSection, confidenceSection, exportSection);

  // ponytail: report data is a static snapshot fetched once — no live subscription to tear down.
  return () => {};
}
