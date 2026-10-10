<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  createContact,
  deleteContact,
  fetchContacts,
  requestFindContacts,
  updateContact,
  type Contact,
} from "@/api/contacts";
import ContactsActions from "./ContactsActions.vue";
import ContactForm from "./ContactForm.vue";
import ContactItem from "./ContactItem.vue";

const props = defineProps<{ companyId: number }>();

const contacts = ref<Contact[]>([]);
const error = ref("");
const adding = ref(false);
const enqueued = ref("");
const busy = ref(false);

async function reload() {
  error.value = "";
  try {
    contacts.value = await fetchContacts(props.companyId);
  } catch (e) {
    error.value = (e as Error).message;
  }
}
onMounted(reload);

async function findContacts(method: "finder" | "website") {
  error.value = "";
  enqueued.value = "";
  busy.value = true;
  try {
    const { job_id } = await requestFindContacts(props.companyId, method);
    enqueued.value = `已加入任务队列（#${job_id}），worker 执行后回到这里查看。可在「任务」页跟踪进度。`;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

async function handleAdd(payload: Parameters<typeof createContact>[1]) {
  try {
    await createContact(props.companyId, payload);
    adding.value = false;
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function handleUpdate(contactId: number, payload: Parameters<typeof updateContact>[1]) {
  try {
    await updateContact(contactId, payload);
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function toggleDnc(contact: Contact) {
  try {
    await updateContact(contact.contact_id, { do_not_contact: !contact.do_not_contact });
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function remove(contact: Contact) {
  if (!window.confirm(`删除联系人「${contact.name ?? contact.email ?? contact.contact_id}」？`)) {
    return;
  }
  try {
    await deleteContact(contact.contact_id);
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  }
}
</script>

<template>
  <section
    class="contacts-panel"
    data-testid="contacts-panel"
  >
    <h3>
      联系人（{{ contacts.length }}）
      <ContactsActions
        :busy="busy"
        :adding="adding"
        @find="findContacts('finder')"
        @crawl="findContacts('website')"
        @add="adding = true"
      />
    </h3>
    <p
      v-if="enqueued"
      class="small muted"
      data-testid="enqueued-hint"
    >
      {{ enqueued }}
    </p>
    <p
      v-if="error"
      class="error"
      data-testid="contacts-error"
    >
      {{ error }}
    </p>
    <ContactForm
      v-if="adding"
      submit-label="添加"
      @submit="handleAdd"
      @cancel="adding = false"
    />
    <ul
      v-if="contacts.length"
      class="contact-list"
    >
      <ContactItem
        v-for="c in contacts"
        :key="c.contact_id"
        :contact="c"
        @update="handleUpdate(c.contact_id, $event)"
        @toggle-dnc="toggleDnc(c)"
        @delete="remove(c)"
      />
    </ul>
    <p
      v-else
      class="muted small"
    >
      暂无联系人
    </p>
  </section>
</template>
