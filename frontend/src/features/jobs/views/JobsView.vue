<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { fetchJobs, type Job, type JobStatus } from "@/api/jobs";

const STATUS_FILTERS: Array<{ value: JobStatus | ""; label: string }> = [
  { value: "", label: "全部" },
  { value: "pending", label: "待执行" },
  { value: "running", label: "执行中" },
  { value: "done", label: "已完成" },
  { value: "failed", label: "失败" },
];

const KIND_LABEL: Record<string, string> = {
  find_contacts: "补全联系人",
  crawl_website: "抓取官网",
  verify_email: "邮箱验证",
  send_email: "发送邮件（二期）",
  poll_imap: "收取回复（二期）",
};

const status = ref<JobStatus | "">("");
const jobs = ref<Job[]>([]);
const error = ref("");
const refreshedAt = ref("");
let timer: ReturnType<typeof setInterval> | undefined;

async function reload() {
  try {
    const data = await fetchJobs(status.value || undefined);
    jobs.value = data.items;
    error.value = "";
    refreshedAt.value = new Date().toLocaleTimeString();
  } catch (e) {
    error.value = `加载任务失败：${(e as Error).message}`;
  }
}

function setStatus(next: JobStatus | "") {
  status.value = next;
  void reload();
}

onMounted(() => {
  void reload();
  timer = setInterval(() => void reload(), 10_000);
});
onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
});
</script>

<template>
  <div class="panel">
    <p class="eyebrow">
      Task Queue
    </p>
    <h1>
      任务状态
    </h1>
    <p class="muted small">
      后台任务由 worker 进程执行（uv run python -m app.worker）；本页只读，每 10 秒自动刷新。
    </p>
    <div
      class="tabs"
      role="tablist"
      aria-label="任务状态筛选"
    >
      <button
        v-for="f in STATUS_FILTERS"
        :key="f.value"
        role="tab"
        :aria-selected="status === f.value"
        :class="{ active: status === f.value }"
        :data-testid="`job-filter-${f.value || 'all'}`"
        @click="setStatus(f.value)"
      >
        {{ f.label }}
      </button>
      <span
        v-if="refreshedAt"
        class="muted small"
      >刷新于 {{ refreshedAt }}</span>
    </div>
    <p
      v-if="error"
      class="badge excluded"
      role="alert"
    >
      {{ error }}
    </p>
    <div
      v-if="jobs.length === 0 && !error"
      class="empty"
      data-testid="jobs-empty"
    >
      当前没有任务。补全联系人与抓取官网的任务会出现在这里。
    </div>
    <div
      v-else
      class="table-scroll"
    >
      <table
        class="grid"
        data-testid="jobs-table"
      >
        <thead>
          <tr>
            <th>#</th>
            <th>类型</th>
            <th>状态</th>
            <th>尝试</th>
            <th>下次执行</th>
            <th>最后错误</th>
            <th>创建时间</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="job in jobs"
            :key="job.id"
            :class="job.status === 'failed' ? 'rail-excluded' : undefined"
          >
            <td class="num">
              {{ job.id }}
            </td>
            <td>{{ KIND_LABEL[job.kind] ?? job.kind }}</td>
            <td>
              <span :class="['badge', job.status === 'done' ? 'precise' : job.status === 'failed' ? 'excluded' : job.status === 'running' ? 'importer' : 'potential']">
                {{ STATUS_FILTERS.find((f) => f.value === job.status)?.label ?? job.status }}
              </span>
            </td>
            <td class="num">
              {{ job.attempts }}/{{ job.max_attempts }}
            </td>
            <td class="code">
              {{ job.run_after ?? "—" }}
            </td>
            <td class="small muted">
              {{ job.last_error ?? "—" }}
            </td>
            <td class="code">
              {{ job.created_at ?? "—" }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
