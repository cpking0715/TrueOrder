import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import tseslint from "typescript-eslint";

const browserGlobals = {
  console: "readonly",
  document: "readonly",
  fetch: "readonly",
  window: "readonly",
  Event: "readonly",
  File: "readonly",
  FormData: "readonly",
  HTMLElement: "readonly",
  HTMLInputElement: "readonly",
  HTMLSelectElement: "readonly",
  KeyboardEvent: "readonly",
  setInterval: "readonly",
  clearInterval: "readonly",
  setTimeout: "readonly",
  URL: "readonly",
  URLSearchParams: "readonly",
};

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/schema.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.ts", "**/*.vue"],
    languageOptions: {
      globals: browserGlobals,
    },
  },
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    // 通用组件 ≤150 行；功能域组件同限
    files: ["src/components/**/*.vue", "src/features/**/components/**/*.vue"],
    rules: {
      "max-lines": ["error", { max: 150, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    // composable ≤100 行
    files: ["src/**/composables/**/*.ts"],
    rules: {
      "max-lines": ["error", { max: 100, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    files: ["**/*.test.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
