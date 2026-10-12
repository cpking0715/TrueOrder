<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";
import ContactsPanel from "./ContactsPanel.vue";
import WebsiteField from "./WebsiteField.vue";

defineProps<{ company: CompanyDetail["company"] }>();
const emit = defineEmits<{ confirmed: [] }>();
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
    <ContactsPanel :company-id="company.company_id" />
  </section>
</template>
