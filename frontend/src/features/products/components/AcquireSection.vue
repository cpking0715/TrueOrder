<script setup lang="ts">
import { ref, watch } from "vue";
import type { CompanyDetail } from "@/api/products";
import type { Opportunity } from "@/api/opportunities";
import type { Contact } from "@/api/contacts";
import { fetchContacts } from "@/api/contacts";
import FollowUpSection from "../../pipeline/components/FollowUpSection.vue";
import SendEmailSection from "../../outreach/components/SendEmailSection.vue";
import ContactsPanel from "./ContactsPanel.vue";
import WebsiteField from "./WebsiteField.vue";

const props = defineProps<{
  company: CompanyDetail["company"];
  opportunity?: Opportunity | null;
  productId?: number;
}>();
const emit = defineEmits<{ confirmed: []; changed: [] }>();

const contacts = ref<Contact[]>([]);

async function loadContacts() {
  try {
    contacts.value = await fetchContacts(props.company.company_id);
  } catch {
    contacts.value = [];
  }
}

watch(() => props.company.company_id, () => void loadContacts(), { immediate: true });
</script>

<template>
  <section id="drawer-website">
    <WebsiteField
      :company-id="company.company_id"
      :website="company.website"
      :confirmed="company.website_confirmed"
      :confidence="company.website_confidence"
      @confirmed="emit('confirmed')"
    />
  </section>
  <section id="drawer-contacts">
    <ContactsPanel
      :company-id="company.company_id"
      :product-id="productId"
    />
  </section>
  <FollowUpSection
    v-if="opportunity"
    :opportunity="opportunity"
    @changed="emit('changed')"
  />
  <SendEmailSection
    v-if="opportunity"
    :opportunity="opportunity"
    :contacts="contacts"
  />
</template>
