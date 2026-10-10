<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  createContact,
  deleteContact,
  fetchContacts,
  updateContact,
  type Contact,
} from "@/api/contacts";
import ContactForm from "./ContactForm.vue";
import ContactItem from "./ContactItem.vue";

const props = defineProps<{ companyId: number }>();

const contacts = ref<Contact[]>([]);
const error = ref("");
const adding = ref(false);

async function reload() {
  error.value = "";
  try {
    contacts.value = await fetchContacts(props.companyId);
  } catch (e) {
    error.value = (e as Error).message;
  }
}
onMounted(reload);

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
      <button
        v-if="!adding"
        class="small"
        data-testid="add-contact"
        @click="adding = true"
      >
        新增联系人
      </button>
    </h3>
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
