<script setup lang="ts">
import LdButton from '@/components/LdButton.vue'
import { t } from '@/i18n'
import AuthLayout from '@/layouts/AuthLayout.vue'
</script>

<template>
  <AuthLayout :title="t('notFound.title')" :subtitle="t('notFound.body')">
    <LdButton :to="{ name: 'landing' }" block>{{ t('notFound.back') }}</LdButton>
  </AuthLayout>
</template>
