import js from "@eslint/js";
import globals from "globals";
import react from "eslint-plugin-react";
import hooks from "eslint-plugin-react-hooks";

export default [
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: { ecmaVersion: "latest", sourceType: "module", globals: { ...globals.browser }, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { react, "react-hooks": hooks },
    settings: { react: { version: "detect" } },
    rules: { ...react.configs.recommended.rules, ...react.configs["jsx-runtime"].rules, ...hooks.configs.recommended.rules, "react/prop-types": "off" },
  },
  { files: ["*.config.js", "e2e/**"], languageOptions: { globals: { ...globals.node } } },
  { files: ["src/**/*.test.{js,jsx}", "src/test/**"], languageOptions: { globals: { ...globals.node, ...globals.vitest } } },
];
