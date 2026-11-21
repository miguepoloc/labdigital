<script setup lang="ts">
/**
 * Landing pública (prerenderizada por vite-ssg). Placeholder estructurado: la landing final
 * se diseña en LD-12; aquí sólo se fija la estructura (hero + secciones) y la marca.
 */
import { RouterLink } from 'vue-router'
import LdButton from '@/components/LdButton.vue'
import LdEscudo from '@/components/LdEscudo.vue'
import LdThemeToggle from '@/components/LdThemeToggle.vue'
import { config } from '@/config'
import { messages, t } from '@/i18n'

const sections = [
  { id: 'modulos', ...messages.landing.sections.modules },
  { id: 'que-hace', ...messages.landing.sections.features },
  { id: 'docentes', ...messages.landing.sections.teachers },
  { id: 'agente', ...messages.landing.sections.agent },
  { id: 'equipo', ...messages.landing.sections.team },
]
const year = new Date().getFullYear()
</script>

<template>
  <div class="ld-landing">
    <a class="ld-skip-link" href="#ld-main">{{ t('app.skipToContent') }}</a>
    <header class="ld-landing__top">
      <div class="ld-container ld-landing__bar">
        <RouterLink class="ld-landing__brand" :to="{ name: 'landing' }">
          <LdEscudo background="dark" :size="36" />
          <span>
            <strong>{{ t('app.name') }}</strong>
            <small>GIDEAM</small>
          </span>
        </RouterLink>
        <nav class="ld-landing__nav" :aria-label="t('nav.main')">
          <a v-for="s in sections" :key="s.id" :href="`#${s.id}`">{{ s.title }}</a>
        </nav>
        <div class="ld-row">
          <LdThemeToggle />
          <RouterLink class="ld-landing__login" :to="{ name: 'login' }">{{
            t('nav.login')
          }}</RouterLink>
        </div>
      </div>
    </header>

    <main id="ld-main" tabindex="-1">
      <section class="ld-hero" aria-labelledby="hero-title">
        <div class="ld-container ld-hero__inner">
          <p class="ld-hero__eyebrow">{{ t('landing.heroEyebrow') }}</p>
          <h1 id="hero-title" class="ld-hero__title">{{ t('landing.heroTitle') }}</h1>
          <p class="ld-hero__body">{{ t('landing.heroBody') }}</p>
          <div class="ld-row">
            <LdButton variant="accent" size="lg" :to="{ name: 'register' }">{{
              t('landing.ctaStart')
            }}</LdButton>
            <LdButton variant="ghost" size="lg" class="ld-hero__ghost" :to="{ name: 'login' }">
              {{ t('landing.ctaLogin') }}
            </LdButton>
          </div>
        </div>
        <div class="ld-hero__pcb" aria-hidden="true">
          <span v-for="i in 8" :key="i" class="ld-hero__led" :class="{ 'is-on': i % 3 === 1 }" />
        </div>
      </section>

      <section
        v-for="s in sections"
        :id="s.id"
        :key="s.id"
        class="ld-landing__section"
        :aria-labelledby="`${s.id}-title`"
      >
        <div class="ld-container">
          <h2 :id="`${s.id}-title`">{{ s.title }}</h2>
          <p>{{ s.body }}</p>
          <div class="ld-landing__placeholder">{{ t('landing.placeholder') }}</div>
        </div>
      </section>
    </main>

    <footer class="ld-landing__footer">
      <div class="ld-container ld-row ld-landing__footer-inner">
        <span>{{ t('landing.footerRights', { year }) }}</span>
        <a :href="config.dataPolicyUrl" target="_blank" rel="noopener">{{
          t('landing.footerPolicy')
        }}</a>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.ld-landing__top {
  position: sticky;
  top: 0;
  z-index: var(--ld-z-header);
  background: var(--ld-color-header-bg);
  color: var(--ld-color-header-text);
}

.ld-landing__bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-3);
  min-height: var(--ld-header-h);
}

.ld-landing__brand {
  display: flex;
  align-items: center;
  gap: var(--ld-space-2);
  color: inherit;
  text-decoration: none;
  font-family: var(--ld-font-heading);
}

.ld-landing__brand span {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.ld-landing__brand small {
  font-size: var(--ld-text-xs);
  letter-spacing: 0.08em;
  opacity: 0.8;
}

.ld-landing__nav {
  display: none;
  gap: var(--ld-space-4);
}

.ld-landing__nav a,
.ld-landing__login {
  color: inherit;
  text-decoration: none;
  font-weight: 500;
}

.ld-landing__nav a:hover,
.ld-landing__login:hover {
  text-decoration: underline;
}

.ld-hero {
  position: relative;
  overflow: hidden;
  padding: var(--ld-space-8) 0 var(--ld-space-7);
  background: linear-gradient(160deg, var(--um-blue) 0%, var(--um-blue-800) 100%);
  color: #fff;
}

.ld-hero__inner {
  position: relative;
  z-index: 1;
  max-width: 48rem;
  margin-inline: 0;
}

@media (min-width: 72rem) {
  .ld-hero__inner {
    margin-inline: auto;
    max-width: var(--ld-content-max);
  }
}

.ld-hero__eyebrow {
  font-size: var(--ld-text-sm);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--um-orange-300);
  font-weight: 600;
}

.ld-hero__title {
  font-size: var(--ld-text-3xl);
  max-width: 20ch;
}

.ld-hero__body {
  max-width: 40rem;
  font-size: var(--ld-text-lg);
  opacity: 0.92;
  margin-bottom: var(--ld-space-5);
}

.ld-hero__ghost {
  --btn-fg: #fff;
  --btn-bg-hover: rgb(255 255 255 / 0.12);
}

.ld-hero__pcb {
  position: absolute;
  right: -2rem;
  bottom: -2rem;
  width: 18rem;
  height: 10rem;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  place-items: center;
  border-radius: var(--ld-radius-lg);
  background: var(--lab-pcb);
  opacity: 0.35;
  transform: rotate(-8deg);
}

.ld-hero__led {
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 50%;
  background: #3a1010;
}

.ld-hero__led.is-on {
  background: var(--lab-led);
  box-shadow: 0 0 12px var(--lab-led);
}

.ld-landing__section {
  padding: var(--ld-space-7) 0;
  scroll-margin-top: var(--ld-header-h);
}

.ld-landing__section:nth-of-type(odd) {
  background: var(--ld-color-surface);
}

.ld-landing__placeholder {
  margin-top: var(--ld-space-4);
  padding: var(--ld-space-6);
  border: 2px dashed var(--ld-color-border);
  border-radius: var(--ld-radius-lg);
  text-align: center;
  color: var(--ld-color-text-muted);
  font-size: var(--ld-text-sm);
}

.ld-landing__footer {
  padding: var(--ld-space-5) 0;
  background: var(--um-blue-800);
  color: #dbe6f1;
  font-size: var(--ld-text-sm);
}

.ld-landing__footer a {
  color: #fff;
}

.ld-landing__footer-inner {
  justify-content: space-between;
}

@media (min-width: 900px) {
  .ld-landing__nav {
    display: flex;
  }

  .ld-hero {
    padding: calc(var(--ld-space-8) * 1.5) 0 var(--ld-space-8);
  }

  .ld-hero__pcb {
    right: 4rem;
    bottom: 3rem;
    width: 22rem;
    height: 13rem;
    opacity: 0.6;
  }
}
</style>
