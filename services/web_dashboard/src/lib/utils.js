export function cn(...inputs) {
  return inputs
    .flatMap((input) => {
      if (!input) {
        return [];
      }
      if (typeof input === "string") {
        return input.split(" ");
      }
      if (Array.isArray(input)) {
        return input;
      }
      if (typeof input === "object") {
        return Object.entries(input)
          .filter(([, value]) => Boolean(value))
          .map(([key]) => key);
      }
      return String(input).split(" ");
    })
    .filter(Boolean)
    .join(" ");
}
