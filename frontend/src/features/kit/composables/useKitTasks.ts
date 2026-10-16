/** 今日任务台：加载 14 天任务、按天分组、勾选（乐观更新，失败回滚）。 */

import { computed, ref } from "vue";
import { fetchKitTasks, setKitTaskDone, type KitTask, type KitTasks } from "@/api/kit";
import { useAsync } from "@/composables/useAsync";

export const PAGE_ROUTE: Record<string, string | null> = {
  today: null,
  products: "/kit/products",
  buyers: "/kit/buyers",
  drafts: "/kit/drafts",
  inquiries: "/kit/inquiries",
  external: null,
};

export function useKitTasks() {
  const data = ref<KitTasks | null>(null);
  const { busy, error, run } = useAsync();

  const days = computed(() => {
    const map = new Map<number, KitTask[]>();
    for (const t of data.value?.tasks ?? []) {
      map.set(t.day, [...(map.get(t.day) ?? []), t]);
    }
    return [...map.entries()].map(([day, tasks]) => ({ day, tasks }));
  });

  async function load() {
    const got = await run(fetchKitTasks);
    if (got) data.value = got;
  }

  async function toggle(task: KitTask) {
    const next = !task.done;
    task.done = next;
    const ok = await run(() => setKitTaskDone(task.key, next).then(() => true));
    if (!ok) {
      task.done = !next;
      return;
    }
    await load(); // 刷新「今天」与完成计数
  }

  return { data, days, busy, error, load, toggle };
}
