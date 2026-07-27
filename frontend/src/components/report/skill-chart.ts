// 09-ui-ux.md §5.5.3, BUILD.md §6 WS8 — "radar chart with mandatory grouped-bar alternative":
// radar reads shape well and precise values poorly; bars and a table are not optional add-ons.
// Plain inline SVG, no charting dependency: jsdom (the test environment) has no <canvas> 2D
// context, so a canvas-based chart lib would need a native 'canvas' package this repo doesn't
// have — SVG renders and is queryable in jsdom with nothing extra installed.
import { t } from '../../i18n';
import type { ErrorKind, TurnView } from '../../types/api';

export interface SkillCount {
  kind: ErrorKind;
  critical: number;
  nonCritical: number;
}

export type ChartMode = 'radar' | 'bars' | 'table';

const SVG_NS = 'http://www.w3.org/2000/svg';

export function countFindingsByKind(turns: TurnView[]): SkillCount[] {
  const map = new Map<ErrorKind, { critical: number; nonCritical: number }>();
  for (const turn of turns) {
    for (const f of turn.verdict?.findings ?? []) {
      const cur = map.get(f.kind) ?? { critical: 0, nonCritical: 0 };
      if (f.severity === 'critical') cur.critical++;
      else cur.nonCritical++;
      map.set(f.kind, cur);
    }
  }
  return Array.from(map.entries()).map(([kind, v]) => ({ kind, ...v }));
}

export function renderSkillChart(counts: SkillCount[], mode: ChartMode): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'skill-chart';
  if (counts.length === 0) {
    const p = document.createElement('p');
    p.textContent = t('report.skills.empty');
    wrap.appendChild(p);
    return wrap;
  }
  if (mode === 'table') wrap.appendChild(renderTable(counts));
  else if (mode === 'bars') wrap.appendChild(renderBars(counts));
  else wrap.appendChild(renderRadar(counts));
  return wrap;
}

function renderTable(counts: SkillCount[]): HTMLElement {
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  for (const label of [t('report.skills.title'), t('finding.severity.critical'), t('finding.severity.non_critical')]) {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = label;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  const tbody = document.createElement('tbody');
  for (const c of counts) {
    const tr = document.createElement('tr');
    const rowHead = document.createElement('th');
    rowHead.scope = 'row';
    rowHead.textContent = t(`finding.kind.${c.kind}`);
    tr.appendChild(rowHead);
    for (const v of [c.critical, c.nonCritical]) {
      const td = document.createElement('td');
      td.textContent = String(v);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  return table;
}

function renderBars(counts: SkillCount[]): SVGSVGElement {
  const max = Math.max(1, ...counts.map((c) => c.critical + c.nonCritical));
  const barH = 18;
  const gap = 10;
  const width = 420;
  const labelW = 140;
  const height = counts.length * (barH + gap);
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', t('report.skills.title'));
  counts.forEach((c, i) => {
    const y = i * (barH + gap);
    const criticalW = (c.critical / max) * (width - labelW);
    const nonCriticalW = (c.nonCritical / max) * (width - labelW);
    const critRect = document.createElementNS(SVG_NS, 'rect');
    critRect.setAttribute('x', String(labelW));
    critRect.setAttribute('y', String(y));
    critRect.setAttribute('width', String(criticalW));
    critRect.setAttribute('height', String(barH / 2));
    critRect.setAttribute('fill', 'var(--color-destructive)');
    const nonCritRect = document.createElementNS(SVG_NS, 'rect');
    nonCritRect.setAttribute('x', String(labelW));
    nonCritRect.setAttribute('y', String(y + barH / 2));
    nonCritRect.setAttribute('width', String(nonCriticalW));
    nonCritRect.setAttribute('height', String(barH / 2));
    nonCritRect.setAttribute('fill', 'var(--color-warning)');
    const label = document.createElementNS(SVG_NS, 'text');
    label.setAttribute('x', '0');
    label.setAttribute('y', String(y + barH / 2 + 4));
    label.setAttribute('font-size', '11');
    label.textContent = t(`finding.kind.${c.kind}`);
    svg.append(label, critRect, nonCritRect);
  });
  return svg;
}

function renderRadar(counts: SkillCount[]): SVGSVGElement {
  const n = counts.length;
  const size = 320;
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 60;
  const max = Math.max(1, ...counts.map((c) => c.critical + c.nonCritical));
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', t('report.skills.title'));
  const points: string[] = [];
  counts.forEach((c, i) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const value = (c.critical + c.nonCritical) / max;
    points.push(`${cx + Math.cos(angle) * r * value},${cy + Math.sin(angle) * r * value}`);
    const label = document.createElementNS(SVG_NS, 'text');
    label.setAttribute('x', String(cx + Math.cos(angle) * (r + 24)));
    label.setAttribute('y', String(cy + Math.sin(angle) * (r + 24)));
    label.setAttribute('font-size', '9');
    label.setAttribute('text-anchor', 'middle');
    label.textContent = t(`finding.kind.${c.kind}`);
    svg.appendChild(label);
  });
  const polygon = document.createElementNS(SVG_NS, 'polygon');
  polygon.setAttribute('points', points.join(' '));
  polygon.setAttribute('fill', 'var(--color-primary)');
  polygon.setAttribute('fill-opacity', '0.3');
  polygon.setAttribute('stroke', 'var(--color-primary)');
  svg.appendChild(polygon);
  return svg;
}
