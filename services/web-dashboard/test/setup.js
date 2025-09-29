import "@testing-library/jest-dom/vitest";

class ResizeObserver {
  constructor(callback) {
    this.callback = callback;
  }

  observe(target) {
    if (typeof this.callback === "function") {
      const width = target?.clientWidth || 800;
      const height = target?.clientHeight || 320;
      this.callback([
        {
          target,
          contentRect: { width, height, top: 0, left: 0, bottom: height, right: width },
        },
      ]);
    }
  }

  unobserve() {}

  disconnect() {}
}

if (!global.ResizeObserver) {
  global.ResizeObserver = ResizeObserver;
}

if (!window.ResizeObserver) {
  window.ResizeObserver = ResizeObserver;
}
