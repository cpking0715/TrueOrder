/** 通用异步状态：busy + error + run(fn)。替代组件里重复的 try/catch/finally 样板。 */

import { ref } from "vue";

export function useAsync() {
  const busy = ref(false);
  const error = ref("");

  /** 执行 fn；失败时写入 error 并返回 undefined（不向上抛）。 */
  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    busy.value = true;
    error.value = "";
    try {
      return await fn();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return undefined;
    } finally {
      busy.value = false;
    }
  }

  return { busy, error, run };
}
