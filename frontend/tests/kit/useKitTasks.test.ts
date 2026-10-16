/** composable：任务按天分组；勾选失败回滚并给出错误。 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchKitTasks, setKitTaskDone } from "@/api/kit";
import { useKitTasks } from "@/features/kit/composables/useKitTasks";
import { tasks } from "./fixtures";

vi.mock("@/api/kit", () => ({ fetchKitTasks: vi.fn(), setKitTaskDone: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchKitTasks).mockResolvedValue(structuredClone(tasks));
});

describe("useKitTasks", () => {
  it("按天分组", async () => {
    const k = useKitTasks();
    await k.load();
    expect(k.days.value.map((d) => d.day)).toEqual([1, 2, 3]);
  });

  it("勾选成功后重新加载", async () => {
    vi.mocked(setKitTaskDone).mockResolvedValue(undefined);
    const k = useKitTasks();
    await k.load();
    await k.toggle(k.data.value!.tasks[1]);
    expect(setKitTaskDone).toHaveBeenCalledWith("d2_pick_products", true);
    expect(fetchKitTasks).toHaveBeenCalledTimes(2);
  });

  it("勾选失败回滚", async () => {
    vi.mocked(setKitTaskDone).mockRejectedValue(new Error("500"));
    const k = useKitTasks();
    await k.load();
    const t = k.data.value!.tasks[1];
    await k.toggle(t);
    expect(t.done).toBe(false);
    expect(k.error.value).toBe("500");
  });
});
