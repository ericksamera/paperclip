/* eslint config for browser + webextensions JS */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, webextensions: true },
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  extends: ["eslint:recommended", "plugin:import/recommended"],
  plugins: ["import"],
  ignorePatterns: ["node_modules/", "data/", "staticfiles/"],
  rules: {
    "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    "import/no-unresolved": "off" // we load d3 via <script> CDN, not imports
  },
  settings: {
    "import/resolver": { node: { extensions: [".js"] } }
  },
  overrides: [
    {
      files: ["extensions/chrome/**/*.js"],
      globals: { chrome: "readonly" }
    }
  ]
};
