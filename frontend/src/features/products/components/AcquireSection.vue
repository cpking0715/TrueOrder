<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";
import type { Opportunity } from "@/api/opportunities";
import FollowUpSection from "../../pipeline/components/FollowUpSection.vue";
import ContactsPanel from "./ContactsPanel.vue";
import WebsiteField from "./WebsiteField.vue";

defineProps<{ company: CompanyDetail["company"]; opportunity?: Opportunity | null }>();
const emit = defineEmits<{ confirmed: []; changed: [] }>();
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
  <FollowUpSection
    v-if="opportunity"
    :opportunity="opportunity"
    @changed="emit('changed')"
  />
</template>
