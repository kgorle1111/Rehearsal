// Landmark-correct empty shell for screens not built this pass (BUILD.md WS8 priority 8:
// "stub the remaining views minimally"). Real content is out of scope until WS-API lands.
import { t } from '../i18n';

export function mountStubView(titleKey: string): (container: HTMLElement) => () => void {
  return (container: HTMLElement) => {
    container.innerHTML = '';
    container.className = 'page stack';
    const h1 = document.createElement('h1');
    h1.textContent = t(titleKey);
    const p = document.createElement('p');
    p.textContent = t('stub.comingSoon');
    container.append(h1, p);
    return () => {};
  };
}
