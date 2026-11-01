import security from "eslint-plugin-security";
import tseslint from "typescript-eslint";
import globals from "globals";

const rules = {
  ...security.configs.recommended.rules,
  "no-eval": "error", "no-implied-eval": "error", "no-new-func": "error",
  "no-unused-vars": "warn", "no-undef": "warn", eqeqeq: "warn", "no-empty": "warn",
};
export default [
  {
    files: ["**/*.js", "**/*.mjs"],
    languageOptions: { ecmaVersion: "latest", sourceType: "module", globals: { ...globals.browser, ...globals.node } },
    plugins: { security },
    rules,
  },
  {
    files: ["**/*.ts"],
    languageOptions: { parser: tseslint.parser, ecmaVersion: "latest", sourceType: "module" },
    plugins: { security },
    rules: { ...rules, "no-unused-vars": "off", "no-undef": "off" },
  },
];
