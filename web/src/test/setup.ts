import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// Pages are lazy-loaded: with every test file running in parallel, a first render can take over the default 1 s
configure({ asyncUtilTimeout: 3000 });

// jsdom lacks the layout APIs Radix popovers and listboxes call
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => {};

afterEach(() => {
  cleanup();
  sessionStorage.clear();
  localStorage.clear();
  document.documentElement.dataset.theme = 'dark';
  vi.unstubAllGlobals();
});
