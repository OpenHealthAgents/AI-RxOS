/** ESLint config for React component packages. */
module.exports = {
  extends: ["./index.js", "plugin:react/recommended", "plugin:react-hooks/recommended"],
  settings: { react: { version: "detect" } },
  env: { browser: true },
};
