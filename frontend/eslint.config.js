import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import tseslint from "typescript-eslint";
import globals from "globals";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "src/api/schema.d.ts"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.ts", "**/*.vue"],
    languageOptions: {
      globals: { ...globals.browser },
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
    // 页面（views）比组件宽松：引导重组，不立刻炸既有页（两页已近 260 行）
    files: ["src/features/**/views/**/*.vue"],
    rules: {
      "max-lines": ["warn", { max: 280, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    files: ["**/*.test.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
);
