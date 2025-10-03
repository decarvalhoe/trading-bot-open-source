import "../app/static/styles.css";

const customViewports = {
  mobile: {
    name: "Mobile",
    styles: {
      width: "360px",
      height: "640px",
    },
  },
  tablet: {
    name: "Tablette",
    styles: {
      width: "768px",
      height: "1024px",
    },
  },
  desktop: {
    name: "Bureau",
    styles: {
      width: "1200px",
      height: "800px",
    },
  },
};

export const parameters = {
  layout: "centered",
  controls: {
    matchers: {
      color: /(background|color)$/i,
      date: /Date$/i,
    },
  },
  backgrounds: {
    default: "Dashboard",
    values: [
      { name: "Dashboard", value: "#0f172a" },
      { name: "Clair", value: "#ffffff" },
    ],
  },
  chromatic: {
    viewports: [360, 768, 1200],
  },
  viewport: {
    viewports: customViewports,
  },
};
