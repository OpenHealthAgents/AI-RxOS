/** ESLint config for Next.js apps. next/core-web-vitals already pulls in
 * react + react-hooks rules, so this extends the base config only —
 * layering react-library.js on top double-registers the react-hooks
 * plugin and breaks lint with a "Plugin conflicted" error. */
module.exports = {
  extends: ["./index.js", "next/core-web-vitals"],
  env: { browser: true },
};
