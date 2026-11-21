<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { RouterLink, useRoute, type RouteLocationRaw } from 'vue-router'
import { t } from '@/i18n'
import LdEscudo from './LdEscudo.vue'
import LdThemeToggle from './LdThemeToggle.vue'

export interface NavItem {
  label: string
  to?: RouteLocationRaw
  /** Elemento visible pero aún no disponible ("Pronto"). */
  soon?: boolean
}

const props = defineProps<{
  userName?: string
  userEmail?: string
  nav: NavItem[]
}>()

const emit = defineEmits<{ logout: [] }>()

const route = useRoute()
const drawerOpen = ref(false)
const userMenuOpen = ref(false)
const uid = useId()
const drawerId = `nav-${uid}`
const userMenuId = `um-${uid}`
const userMenuRef = ref<HTMLElement | null>(null)
const userButtonRef = ref<HTMLButtonElement | null>(null)

const initials = computed(() =>
  (props.userName ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join(''),
)

watch(
  () => route.fullPath,
  () => {
    drawerOpen.value = false
    userMenuOpen.value = false
  },
)

function onDocClick(e: MouseEvent) {
  if (!userMenuOpen.value) return
  const target = e.target as Node
  if (userMenuRef.value?.contains(target) || userButtonRef.value?.contains(target)) return
  userMenuOpen.value = false
}

function onKey(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  if (userMenuOpen.value) {
    userMenuOpen.value = false
    userButtonRef.value?.focus()
  }
  drawerOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="ld-shell" :class="{ 'ld-shell--drawer': drawerOpen }">
    <a class="ld-skip-link" href="#ld-main">{{ t('app.skipToContent') }}</a>

    <header class="ld-shell__header">
      <button
        type="button"
        class="ld-shell__burger"
        :aria-expanded="drawerOpen ? 'true' : 'false'"
        :aria-controls="drawerId"
        :aria-label="drawerOpen ? t('nav.closeMenu') : t('nav.openMenu')"
        @click="drawerOpen = !drawerOpen"
      >
        <span aria-hidden="true">{{ drawerOpen ? '✕' : '☰' }}</span>
      </button>

      <RouterLink class="ld-shell__brand" :to="{ name: 'home' }">
        <LdEscudo background="dark" :size="32" />
        <span class="ld-shell__brand-text">
          <strong>{{ t('app.name') }}</strong>
          <span class="ld-shell__brand-org">GIDEAM</span>
        </span>
      </RouterLink>

      <div class="ld-shell__spacer" />
      <LdThemeToggle />

      <div v-if="userName" class="ld-shell__user">
        <button
          ref="userButtonRef"
          type="button"
          class="ld-shell__user-btn"
          aria-haspopup="menu"
          :aria-expanded="userMenuOpen ? 'true' : 'false'"
          :aria-controls="userMenuId"
          @click="userMenuOpen = !userMenuOpen"
        >
          <span class="ld-shell__avatar" aria-hidden="true">{{ initials }}</span>
          <span class="ld-shell__user-name">{{ userName }}</span>
          <span class="ld-visually-hidden">{{ t('nav.userMenu') }}</span>
        </button>
        <div
          v-show="userMenuOpen"
          :id="userMenuId"
          ref="userMenuRef"
          class="ld-shell__menu"
          role="menu"
          :aria-label="t('nav.userMenu')"
        >
          <p class="ld-shell__menu-head">
            <strong>{{ userName }}</strong>
            <span v-if="userEmail">{{ userEmail }}</span>
          </p>
          <RouterLink role="menuitem" class="ld-shell__menu-item" :to="{ name: 'profile' }">
            {{ t('nav.profile') }}
          </RouterLink>
          <RouterLink role="menuitem" class="ld-shell__menu-item" :to="{ name: 'sessions' }">
            {{ t('nav.sessions') }}
          </RouterLink>
          <button type="button" role="menuitem" class="ld-shell__menu-item" @click="emit('logout')">
            {{ t('nav.logout') }}
          </button>
        </div>
      </div>
    </header>

    <div class="ld-shell__body">
      <nav :id="drawerId" class="ld-shell__nav" :aria-label="t('nav.main')">
        <ul>
          <li v-for="item in nav" :key="item.label">
            <RouterLink v-if="item.to && !item.soon" class="ld-shell__nav-link" :to="item.to">
              {{ item.label }}
            </RouterLink>
            <span v-else class="ld-shell__nav-link is-soon" aria-disabled="true">
              {{ item.label }} <small class="ld-shell__soon">{{ t('nav.soon') }}</small>
            </span>
          </li>
        </ul>
      </nav>
      <div
        v-if="drawerOpen"
        class="ld-shell__scrim"
        aria-hidden="true"
        @click="drawerOpen = false"
      />
      <main id="ld-main" class="ld-shell__main" tabindex="-1">
        <slot />
      </main>
    </div>
  </div>
</template>

<style scoped>
.ld-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.ld-shell__header {
  position: sticky;
  top: 0;
  z-index: var(--ld-z-header);
  display: flex;
  align-items: center;
  gap: var(--ld-space-3);
  height: var(--ld-header-h);
  padding: 0 var(--ld-space-3);
  background: var(--ld-color-header-bg);
  color: var(--ld-color-header-text);
  box-shadow: var(--ld-shadow-md);
}

.ld-shell__burger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  border: 0;
  border-radius: var(--ld-radius-md);
  background: transparent;
  color: inherit;
  font-size: 1.25rem;
  cursor: pointer;
}

.ld-shell__brand {
  display: flex;
  align-items: center;
  gap: var(--ld-space-2);
  color: inherit;
  text-decoration: none;
}

.ld-shell__brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
  font-family: var(--ld-font-heading);
}

.ld-shell__brand-org {
  font-size: var(--ld-text-xs);
  opacity: 0.8;
  letter-spacing: 0.08em;
}

.ld-shell__spacer {
  flex: 1;
}

.ld-shell__user {
  position: relative;
}

.ld-shell__user-btn {
  display: flex;
  align-items: center;
  gap: var(--ld-space-2);
  min-height: 2.5rem;
  padding: 0 var(--ld-space-2);
  border: 0;
  border-radius: var(--ld-radius-full);
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.ld-shell__burger:focus-visible,
.ld-shell__user-btn:focus-visible,
.ld-shell__brand:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}

.ld-shell__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: var(--um-orange);
  color: #fff;
  font-weight: 700;
  font-size: var(--ld-text-sm);
}

.ld-shell__user-name {
  display: none;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ld-shell__menu {
  position: absolute;
  right: 0;
  top: calc(100% + var(--ld-space-2));
  z-index: var(--ld-z-menu);
  min-width: 14rem;
  padding: var(--ld-space-2);
  background: var(--ld-color-surface);
  color: var(--ld-color-text);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  box-shadow: var(--ld-shadow-lg);
}

.ld-shell__menu-head {
  display: flex;
  flex-direction: column;
  padding: var(--ld-space-2);
  margin: 0 0 var(--ld-space-1);
  border-bottom: 1px solid var(--ld-color-border);
  font-size: var(--ld-text-sm);
  overflow-wrap: anywhere;
}

.ld-shell__menu-head span {
  color: var(--ld-color-text-muted);
}

.ld-shell__menu-item {
  display: block;
  width: 100%;
  padding: var(--ld-space-2);
  border: 0;
  border-radius: var(--ld-radius-sm);
  background: transparent;
  color: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}

.ld-shell__menu-item:hover,
.ld-shell__menu-item:focus-visible {
  background: var(--ld-color-surface-2);
  outline: none;
}

.ld-shell__body {
  position: relative;
  flex: 1;
  display: flex;
}

.ld-shell__nav {
  position: fixed;
  top: var(--ld-header-h);
  bottom: 0;
  left: 0;
  z-index: var(--ld-z-menu);
  width: min(80vw, var(--ld-sidebar-w));
  padding: var(--ld-space-4) var(--ld-space-2);
  background: var(--ld-color-surface);
  border-right: 1px solid var(--ld-color-border);
  transform: translateX(-100%);
  visibility: hidden;
  transition:
    transform var(--ld-duration) var(--ld-ease),
    visibility var(--ld-duration);
}

.ld-shell--drawer .ld-shell__nav {
  transform: none;
  visibility: visible;
}

.ld-shell__scrim {
  position: fixed;
  inset: var(--ld-header-h) 0 0 0;
  z-index: calc(var(--ld-z-menu) - 1);
  background: rgb(0 0 0 / 0.4);
}

.ld-shell__nav ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-1);
}

.ld-shell__nav-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-2);
  padding: var(--ld-space-2) var(--ld-space-3);
  border-radius: var(--ld-radius-md);
  color: var(--ld-color-text);
  text-decoration: none;
  font-weight: 500;
}

a.ld-shell__nav-link:hover {
  background: var(--ld-color-surface-2);
}

a.ld-shell__nav-link.router-link-exact-active {
  background: color-mix(in srgb, var(--ld-color-primary) 14%, transparent);
  color: var(--ld-color-primary);
  box-shadow: inset 3px 0 0 var(--ld-color-primary);
}

.ld-shell__nav-link.is-soon {
  color: var(--ld-color-text-muted);
}

.ld-shell__soon {
  font-size: var(--ld-text-xs);
  padding: 0 var(--ld-space-2);
  border-radius: var(--ld-radius-full);
  background: var(--ld-color-surface-2);
}

.ld-shell__main {
  flex: 1;
  min-width: 0;
  width: 100%;
  max-width: var(--ld-content-max);
  margin-inline: auto;
  padding: var(--ld-space-5) var(--ld-space-4) var(--ld-space-7);
}

.ld-shell__main:focus {
  outline: none;
}

@media (min-width: 900px) {
  .ld-shell__burger,
  .ld-shell__scrim {
    display: none;
  }

  .ld-shell__user-name {
    display: inline;
  }

  .ld-shell__nav {
    position: sticky;
    top: var(--ld-header-h);
    height: calc(100vh - var(--ld-header-h));
    flex: none;
    width: var(--ld-sidebar-w);
    transform: none;
    visibility: visible;
    transition: none;
  }

  .ld-shell__main {
    padding: var(--ld-space-6);
  }
}
</style>
