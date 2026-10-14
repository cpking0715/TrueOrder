/** 税号自动推荐：品名变化 → debounce → AI 推荐 → chip 展示 → 点击回填。 */

import { ref, watch, type Ref } from "vue";
import { autoHs as requestAutoHs, type AutoHsResult } from "@/api/hs";

export type { AutoHsResult };

export function useAutoHs(name: Ref<string>, hsCode: Ref<string>) {
  const autoHs = ref<AutoHsResult | null>(null);
  const busy = ref(false);
  let timer: ReturnType<typeof setTimeout> | undefined;

  async function fetchSuggestion() {
    if (!name.value.trim() || hsCode.value.trim()) {
      autoHs.value = null;
      return;
    }
    busy.value = true;
    try {
      autoHs.value = await requestAutoHs(name.value.trim());
    } catch {
      autoHs.value = null;
    } finally {
      busy.value = false;
    }
  }

  function accept() {
    if (autoHs.value) {
      hsCode.value = autoHs.value.hs_code;
      autoHs.value = null;
    }
  }

  watch([name, hsCode], () => {
    clearTimeout(timer);
    timer = setTimeout(() => void fetchSuggestion(), 800);
  });

  return { autoHs, busy, accept };
}
