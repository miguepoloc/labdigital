<script setup lang="ts">
/**
 * Landing pública (LD-12), prerenderizada por vite-ssg. Port fiel del diseño aprobado
 * (`/labdigital/preview/`): mismas secciones, textos e ilustración de la Basys 3.
 * Sin scripts en línea (CSP `script-src 'self'`): el tema lo aplica `theme-init.js` y `LdThemeToggle`.
 * Con sesión iniciada, el botón superior lleva al área privada (se consulta `/me` sólo en el cliente).
 */
import { useHead } from '@unhead/vue'
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import LdThemeToggle from '@/components/LdThemeToggle.vue'
import { config } from '@/config'
import { messages, t } from '@/i18n'
import { useSessionStore } from '@/stores/session'

const L = messages.landing
const session = useSessionStore()
const loggedIn = computed(() => session.isAuthenticated)

/** Descargas del agente JG FPGA (versión 1.1.0, publicadas por el equipo del módulo). */
const AGENT = {
  windows: 'https://www.mediafire.com/file/bd235hkg1itg4rw/JGFPGA-Agente-1.1.0-win64.zip/file',
  mac: 'https://www.mediafire.com/file/2z2427goqqt0img/JGFPGA-Agente-1.1.0-mac.zip/file',
}
const ESCUDO_96 = 'https://cdn.unimagdalena.edu.co/images/escudo/bg_dark/96.png'
const GIDEAM_URL = 'https://gideam.unimagdalena.edu.co/'
const DESIGN_SYSTEM_URL = '/labdigital/design-system/'

/* Ilustración: posiciones de la placa (mismas coordenadas que el diseño). */
const pinsX = Array.from({ length: 10 }, (_, i) => 204 + i * 12)
const ledsOn = [1, 3, 4, 7, 9, 12, 14]
const LED_TICK = 7
const knobsUp = [1, 3, 4, 9, 12, 14]
const sixteen = Array.from({ length: 16 }, (_, i) => i)

useHead({ meta: [{ name: 'description', content: L.meta.description }] })

onMounted(() => {
  // Página pública: si no hay sesión, `ensureLoaded` devuelve null sin redirigir.
  void session.ensureLoaded({ optional: true })
})
</script>

<template>
  <div class="lp">
    <a class="ld-skip-link" href="#ld-main">{{ t('app.skipToContent') }}</a>

    <header class="lp-top">
      <div class="lp-wrap lp-top__bar">
        <img :src="ESCUDO_96" :alt="t('landing.top.escudoAlt')" width="38" height="38" />
        <div class="lp-brand">
          <b>{{ t('app.name') }}</b><span>{{ t('landing.top.tagline') }}</span>
        </div>
        <nav class="lp-top__nav" :aria-label="t('nav.main')">
          <a class="lp-hide-sm" href="#modulos">{{ t('landing.top.nav.modules') }}</a>
          <a class="lp-hide-sm" href="#docentes">{{ t('landing.top.nav.teachers') }}</a>
          <a class="lp-hide-sm" href="#agente">{{ t('landing.top.nav.agent') }}</a>
          <a class="lp-hide-sm" href="#equipo">{{ t('landing.top.nav.team') }}</a>
          <LdThemeToggle class="lp-theme" />
          <RouterLink
            v-if="loggedIn"
            class="lp-btn lp-btn--ghost"
            :to="{ name: 'home' }"
            data-test="landing-app"
            >{{ t('landing.top.app') }}</RouterLink
          >
          <RouterLink
            v-else
            class="lp-btn lp-btn--ghost"
            :to="{ name: 'login' }"
            data-test="landing-login"
            >{{ t('landing.top.login') }}</RouterLink
          >
        </nav>
      </div>
    </header>

    <main id="ld-main" tabindex="-1">
      <div class="lp-hero">
        <div class="lp-wrap lp-hero__grid">
          <div>
            <p class="lp-eyebrow lp-eyebrow--hero">{{ t('landing.hero.eyebrow') }}</p>
            <h1>
              {{ L.hero.titleBefore }}<em>{{ L.hero.titleEm }}</em
              >{{ L.hero.titleAfter }}
            </h1>
            <p class="lp-hero__sub">
              {{ L.hero.subBefore }}<code>{{ L.hero.subCode }}</code
              >{{ L.hero.subAfter }}
            </p>
            <div class="lp-ctas">
              <RouterLink class="lp-btn lp-btn--primary" :to="{ name: 'register' }">{{
                t('landing.hero.ctaRegister')
              }}</RouterLink>
              <a class="lp-btn lp-btn--ghost" href="#modulos">{{ t('landing.hero.ctaMore') }}</a>
            </div>
            <p class="lp-hero__note">
              {{ L.hero.noteBefore }}<code>{{ L.hero.noteCode }}</code
              >{{ L.hero.noteAfter }}
            </p>
          </div>

          <div class="lp-board" aria-hidden="true">
            <svg viewBox="0 0 520 360" focusable="false">
              <rect class="b-pcb" x="10" y="10" width="500" height="340" rx="18" />
              <text class="b-txt" x="34" y="44">BASYS 3 · XC7A35T</text>
              <rect class="b-chip" x="196" y="78" width="128" height="128" rx="6" />
              <g class="b-pin">
                <rect v-for="x in pinsX" :key="`t${x}`" :x="x" y="68" width="4" height="10" />
                <rect v-for="x in pinsX" :key="`b${x}`" :x="x" y="206" width="4" height="10" />
              </g>
              <text class="b-txt b-txt--chip" x="226" y="146">ARTIX-7</text>
              <!-- display de 7 segmentos: "LAb1" -->
              <g transform="translate(350 70)">
                <rect x="0" y="0" width="140" height="64" rx="6" class="b-display" />
                <g transform="translate(10 8)">
                  <rect class="b-seg on" x="2" y="2" width="3" height="20" />
                  <rect class="b-seg on" x="2" y="26" width="3" height="20" />
                  <rect class="b-seg on" x="5" y="45" width="16" height="3" />
                </g>
                <g transform="translate(43 8)">
                  <rect class="b-seg on" x="5" y="0" width="16" height="3" />
                  <rect class="b-seg on" x="2" y="2" width="3" height="20" />
                  <rect class="b-seg on" x="21" y="2" width="3" height="20" />
                  <rect class="b-seg on" x="5" y="22" width="16" height="3" />
                  <rect class="b-seg on" x="2" y="26" width="3" height="20" />
                  <rect class="b-seg on" x="21" y="26" width="3" height="20" />
                </g>
                <g transform="translate(76 8)">
                  <rect class="b-seg on" x="2" y="2" width="3" height="20" />
                  <rect class="b-seg on" x="5" y="22" width="16" height="3" />
                  <rect class="b-seg on" x="2" y="26" width="3" height="20" />
                  <rect class="b-seg on" x="21" y="26" width="3" height="20" />
                  <rect class="b-seg on" x="5" y="45" width="16" height="3" />
                </g>
                <g transform="translate(109 8)">
                  <rect class="b-seg on" x="21" y="2" width="3" height="20" />
                  <rect class="b-seg on" x="21" y="26" width="3" height="20" />
                </g>
              </g>
              <!-- botones -->
              <g transform="translate(392 160)">
                <circle class="b-btn" cx="28" cy="0" r="9" />
                <circle class="b-btn" cx="0" cy="28" r="9" />
                <circle class="b-btn" cx="28" cy="28" r="9" />
                <circle class="b-btn" cx="56" cy="28" r="9" />
                <circle class="b-btn" cx="28" cy="56" r="9" />
              </g>
              <!-- LEDs -->
              <g transform="translate(40 252)">
                <circle
                  v-for="i in sixteen"
                  :key="`l${i}`"
                  class="b-led"
                  :class="{ on: ledsOn.includes(i), tick: i === LED_TICK }"
                  :cx="i * 28"
                  cy="0"
                  r="6"
                />
              </g>
              <!-- switches -->
              <g transform="translate(32 278)">
                <g class="b-sw">
                  <rect
                    v-for="i in sixteen"
                    :key="`s${i}`"
                    :x="i * 28"
                    y="0"
                    width="16"
                    height="40"
                    rx="3"
                  />
                </g>
                <g class="b-knob">
                  <rect
                    v-for="i in sixteen"
                    :key="`k${i}`"
                    :x="i * 28 + 3"
                    :y="knobsUp.includes(i) ? 4 : 22"
                    width="10"
                    height="14"
                    rx="2"
                  />
                </g>
              </g>
            </svg>
          </div>
        </div>
      </div>

      <section id="modulos" class="lp-section" aria-labelledby="modulos-title">
        <div class="lp-wrap">
          <div class="lp-head">
            <p class="lp-eyebrow">{{ t('landing.modules.eyebrow') }}</p>
            <h2 id="modulos-title">{{ t('landing.modules.title') }}</h2>
            <p class="lp-lead">{{ t('landing.modules.lead') }}</p>
          </div>
          <div class="lp-route">
            <article
              v-for="s in L.modules.steps"
              :key="s.title"
              class="lp-step"
              :class="{ 'lp-step--current': s.current }"
            >
              <span class="lp-step__sem">{{ s.sem }}</span>
              <h3>{{ s.title }}</h3>
              <p>{{ s.body }}</p>
              <span class="lp-tag" :class="s.live ? 'lp-tag--live' : 'lp-tag--soon'">{{
                s.tag
              }}</span>
            </article>
          </div>
        </div>
      </section>

      <section id="funciones" class="lp-section lp-section--alt" aria-labelledby="funciones-title">
        <div class="lp-wrap">
          <div class="lp-head">
            <p class="lp-eyebrow">{{ t('landing.features.eyebrow') }}</p>
            <h2 id="funciones-title">{{ t('landing.features.title') }}</h2>
          </div>
          <div class="lp-feats">
            <div v-for="f in L.features.items" :key="f.icon" class="lp-feat">
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path v-if="f.icon === 'code'" d="M8 6 3 12l5 6M16 6l5 6-5 6M14 4l-4 16" />
                <template v-else-if="f.icon === 'board'">
                  <rect x="3" y="4" width="18" height="14" rx="2" />
                  <circle cx="8" cy="9" r="1.5" />
                  <circle cx="12" cy="9" r="1.5" />
                  <circle cx="16" cy="9" r="1.5" />
                  <path d="M7 14h10M9 21h6" />
                </template>
                <path v-else-if="f.icon === 'wave'" d="M3 12h3V6h4v12h4V9h3v3h4" />
                <template v-else-if="f.icon === 'chip'">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                  <path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" />
                </template>
                <path
                  v-else-if="f.icon === 'bulb'"
                  d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2V17h5v-1.2c.1-.8.5-1.5 1.1-2A6 6 0 0 0 12 3ZM10 21h4"
                />
                <template v-else>
                  <path d="M7 3h7l5 5v13H7z" />
                  <path d="M14 3v5h5M10 13h6M10 17h6" />
                </template>
              </svg>
              <div>
                <h3>{{ f.title }}</h3>
                <p>{{ f.body }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="docentes" class="lp-section" aria-labelledby="docentes-title">
        <div class="lp-wrap lp-teach">
          <div>
            <div class="lp-head">
              <p class="lp-eyebrow">{{ t('landing.teachers.eyebrow') }}</p>
              <h2 id="docentes-title">{{ t('landing.teachers.title') }}</h2>
              <p class="lp-lead">{{ t('landing.teachers.lead') }}</p>
            </div>
            <ol class="lp-flow">
              <li v-for="step in L.teachers.flow" :key="step.title">
                <div>
                  <b>{{ step.title }}</b><span>{{ step.body }}</span>
                </div>
              </li>
            </ol>
          </div>
          <div class="lp-grades" role="group" :aria-label="t('landing.teachers.grades.label')">
            <header>
              <b>{{ t('landing.teachers.grades.title') }}</b><span>{{
                t('landing.teachers.grades.scale')
              }}</span>
            </header>
            <div class="lp-tbl">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{{ t('landing.teachers.grades.cols.who') }}</th>
                    <th scope="col">{{ t('landing.teachers.grades.cols.when') }}</th>
                    <th scope="col">{{ t('landing.teachers.grades.cols.status') }}</th>
                    <th scope="col">{{ t('landing.teachers.grades.cols.grade') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in L.teachers.grades.rows" :key="r.who">
                    <td>{{ r.who }}</td>
                    <td>{{ r.when }}</td>
                    <td>
                      <span class="lp-st" :class="`lp-st--${r.status}`">{{ r.label }}</span>
                    </td>
                    <td>{{ r.grade }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="lp-example">{{ t('landing.teachers.grades.example') }}</p>
          </div>
        </div>
      </section>

      <section id="agente" class="lp-section lp-section--alt" aria-labelledby="agente-title">
        <div class="lp-wrap">
          <div class="lp-agent">
            <div>
              <p class="lp-eyebrow">{{ t('landing.agent.eyebrow') }}</p>
              <h2 id="agente-title" class="lp-agent__title">{{ t('landing.agent.title') }}</h2>
              <p class="lp-lead lp-agent__lead">{{ t('landing.agent.lead') }}</p>
              <div class="lp-agent__dl">
                <a class="lp-btn lp-btn--solid" :href="AGENT.windows" rel="noopener">{{
                  t('landing.agent.windows')
                }}</a>
                <a class="lp-btn lp-btn--line" :href="AGENT.mac" rel="noopener">{{
                  t('landing.agent.mac')
                }}</a>
              </div>
            </div>
            <ul>
              <li>{{ L.agent.notes.versionBefore }}</li>
              <li>
                {{ L.agent.notes.localBefore }}<code>{{ L.agent.notes.localCode }}</code
                >{{ L.agent.notes.localAfter }}
              </li>
              <li>
                {{ L.agent.notes.noAgentBefore }}<code>{{ L.agent.notes.noAgentCode }}</code
                >{{ L.agent.notes.noAgentAfter }}
              </li>
            </ul>
          </div>
        </div>
      </section>

      <section id="equipo" class="lp-section" aria-labelledby="equipo-title">
        <div class="lp-wrap lp-team">
          <div>
            <div class="lp-head">
              <p class="lp-eyebrow">{{ t('landing.team.eyebrow') }}</p>
              <h2 id="equipo-title">{{ t('landing.team.title') }}</h2>
              <p class="lp-lead">{{ t('landing.team.lead') }}</p>
            </div>
            <p>
              {{ t('landing.team.body') }}
              <a :href="GIDEAM_URL">{{ t('landing.team.link') }}</a>.
            </p>
            <div class="lp-credits">
              <h3 class="lp-credits__title">{{ t('landing.team.creditsTitle') }}</h3>
              <ul class="lp-credits__list">
                <li v-for="c in L.team.credits" :key="c.name">
                  <b>{{ c.name }}</b> — {{ c.role }}
                </li>
              </ul>
              <p class="lp-credits__aff">{{ t('landing.team.creditsAffiliation') }}</p>
            </div>
          </div>
          <div class="lp-facts">
            <div v-for="f in L.team.facts" :key="f.value" class="lp-fact">
              <b>{{ f.value }}</b><span>{{ f.label }}</span>
            </div>
          </div>
        </div>
      </section>

      <div class="lp-final">
        <div class="lp-wrap lp-final__inner">
          <h2>{{ t('landing.final.title') }}</h2>
          <div class="lp-ctas">
            <RouterLink class="lp-btn lp-btn--primary" :to="{ name: 'register' }">{{
              t('landing.final.register')
            }}</RouterLink>
            <RouterLink class="lp-btn lp-btn--ghost" :to="{ name: 'login' }">{{
              t('landing.final.login')
            }}</RouterLink>
          </div>
        </div>
      </div>
    </main>

    <footer class="lp-footer">
      <div class="lp-wrap lp-footer__grid">
        <img :src="ESCUDO_96" :alt="t('landing.top.escudoAlt')" width="44" height="44" />
        <div>
          {{ t('landing.footer.line1') }}<br />
          {{ L.footer.line2Before
          }}<a :href="config.dataPolicyUrl" target="_blank" rel="noopener">{{
            L.footer.line2Link
          }}</a
          >{{ L.footer.line2After }}
        </div>
        <a :href="DESIGN_SYSTEM_URL">{{ t('landing.footer.designSystem') }}</a>
      </div>
    </footer>
  </div>
</template>

<style scoped>
/*
 * Port del diseño aprobado. Equivalencias de variables del diseño → tokens (src/styles/tokens.css):
 * surface → --ld-color-bg · surface-raised → --ld-color-surface · surface-sunken → --ld-color-surface-2 ·
 * ink → --ld-color-text · ink-muted → --ld-color-text-muted · line → --ld-color-border ·
 * primary → --ld-color-primary · primary-strong → --ld-color-primary-strong · brand-deep → --ld-color-brand-deep ·
 * accent → --ld-color-accent · accent-ink → --ld-color-accent-text · success → --ld-color-success-strong ·
 * hole → --ld-color-hole. Los colores de la ilustración de la placa son fijos (no dependen del tema).
 */
.lp {
  --lp-board: var(--lab-pcb);
  --lp-board-deep: #084d2a;
  --lp-led-on: var(--lab-led);
  --lp-led-off: #4a2a2a;
  --lp-on-deep: #c9d8e8;
  --lp-on-deep-muted: #9fb7cf;
  --lp-on-deep-link: #dbe7f3;
  --lp-hero-accent: var(--um-orange-300);
  min-height: 100vh;
  background: var(--ld-color-bg);
  color: var(--ld-color-text);
  font-size: 16px;
  line-height: 1.6;
}

.lp :deep(a) {
  color: var(--ld-color-primary);
}

.lp h1,
.lp h2,
.lp h3 {
  font-family: var(--ld-font-heading);
  text-wrap: balance;
  line-height: 1.2;
  margin: 0;
}

.lp code {
  font-family: var(--ld-font-mono);
}

.lp-wrap {
  max-width: 1120px;
  margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
}

.lp-eyebrow {
  font: 500 12px/16px var(--ld-font-body);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ld-color-accent-text);
  margin: 0 0 8px;
}

.lp-eyebrow--hero {
  color: var(--lp-hero-accent);
}

.lp-lead {
  font-size: 18px;
  color: var(--ld-color-text-muted);
  max-width: 62ch;
  margin: 0;
}

/* Barra superior */
.lp-top {
  position: sticky;
  top: env(safe-area-inset-top, 0px);
  z-index: var(--ld-z-header);
  background: var(--ld-color-brand-deep);
  color: #fff;
}

.lp-top__bar {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 64px;
}

.lp-top img {
  height: 38px;
  width: auto;
  display: block;
}

.lp-brand {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.lp-brand b {
  font-family: var(--ld-font-heading);
  font-size: 18px;
}

.lp-brand span {
  font-size: 12px;
  opacity: 0.8;
}

.lp-top__nav {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 20px;
  font-size: 15px;
}

.lp .lp-top__nav a:not(.lp-btn) {
  color: var(--lp-on-deep-link);
  text-decoration: none;
}

.lp .lp-top__nav a:not(.lp-btn):hover {
  color: #fff;
}

.lp-theme {
  color: #fff;
}

@media (max-width: 760px) {
  .lp-hide-sm {
    display: none;
  }

  .lp-brand span {
    display: none;
  }

  .lp-top__nav {
    gap: 12px;
  }
}

/* Botones */
.lp .lp-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 20px;
  border-radius: var(--ld-radius-md);
  font: 500 15px/1 var(--ld-font-body);
  text-decoration: none;
  border: 1px solid transparent;
  cursor: pointer;
  white-space: nowrap;
}

.lp .lp-btn--primary {
  background: var(--ld-color-accent);
  color: #1b1200;
  border-color: var(--ld-color-accent);
}

.lp .lp-btn--primary:hover {
  background: #e58600;
}

.lp .lp-btn--ghost {
  color: #fff;
  border-color: rgb(255 255 255 / 0.45);
}

.lp .lp-btn--ghost:hover {
  border-color: #fff;
}

.lp .lp-btn--solid {
  background: var(--ld-color-primary);
  color: var(--ld-color-primary-contrast);
}

.lp .lp-btn--solid:hover {
  background: var(--ld-color-primary-strong);
}

.lp .lp-btn--line {
  border-color: var(--ld-color-border);
  color: var(--ld-color-text);
  background: var(--ld-color-surface);
}

.lp-ctas {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

/* Hero */
.lp-hero {
  background: var(--ld-color-brand-deep);
  color: #fff;
  overflow: hidden;
}

.lp-hero__grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 40px;
  align-items: center;
  padding-block: 56px 64px;
}

.lp-hero h1 {
  font-size: clamp(34px, 5vw, 54px);
  font-weight: 800;
  letter-spacing: -0.01em;
}

.lp-hero h1 em {
  font-style: normal;
  color: var(--lp-hero-accent);
}

.lp-hero__sub {
  color: var(--lp-on-deep);
  font-size: 18px;
  max-width: 54ch;
  margin: 18px 0 28px;
}

.lp-hero__note {
  margin: 18px 0 0;
  font-size: 13px;
  color: var(--lp-on-deep-muted);
}

.lp-hero__note code {
  color: var(--lp-on-deep-link);
}

@media (max-width: 860px) {
  .lp-hero__grid {
    grid-template-columns: 1fr;
    padding-block: 40px 48px;
  }
}

/* Placa ilustrada */
.lp-board {
  width: 100%;
  max-width: 520px;
  justify-self: end;
  aspect-ratio: 520 / 360;
}

.lp-board svg {
  width: 100%;
  height: 100%;
  display: block;
}

.b-pcb {
  fill: var(--lp-board);
  stroke: var(--lp-board-deep);
  stroke-width: 6;
}

.b-chip {
  fill: #1d2228;
}

.b-pin {
  fill: #c7cdd4;
}

.b-txt {
  fill: #d7e6dc;
  font: 500 11px var(--ld-font-mono);
}

.b-txt--chip {
  fill: #9aa4ad;
}

.b-display {
  fill: #111;
}

.b-led {
  fill: var(--lp-led-off);
}

.b-led.on {
  fill: var(--lp-led-on);
  filter: drop-shadow(0 0 4px rgb(255 59 48 / 0.9));
}

.b-sw {
  fill: #2f3740;
}

.b-knob {
  fill: #e9edf1;
}

.b-seg {
  fill: #2a2f2a;
}

.b-seg.on {
  fill: #ff4040;
  filter: drop-shadow(0 0 3px rgb(255 64 64 / 0.8));
}

.b-btn {
  fill: #22282e;
  stroke: #8d969f;
  stroke-width: 2;
}

@keyframes lp-blink {
  0%,
  49% {
    opacity: 1;
  }

  50%,
  100% {
    opacity: 0.25;
  }
}

.b-led.tick {
  animation: lp-blink 1s steps(1) infinite;
}

@media (prefers-reduced-motion: reduce) {
  .b-led.tick {
    animation: none;
  }
}

/* Secciones */
.lp-section {
  padding-block: 72px;
  scroll-margin-top: 64px;
}

.lp-section--alt {
  background-color: var(--ld-color-surface);
  background-image: radial-gradient(var(--ld-color-hole) 1.5px, transparent 1.6px);
  background-size: 12px 12px;
  border-block: 1px solid var(--ld-color-border);
}

.lp-head {
  display: grid;
  gap: 8px;
  margin-bottom: 32px;
}

.lp-head h2 {
  font-size: clamp(26px, 3.4vw, 36px);
}

/* Ruta de asignaturas */
.lp-route {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.lp-step {
  background: var(--ld-color-surface);
  border: 1px solid var(--ld-color-border);
  border-radius: 16px;
  padding: 24px;
  display: grid;
  gap: 10px;
  align-content: start;
  min-width: 0;
}

.lp-step__sem {
  font: 500 12px/1 var(--ld-font-mono);
  color: var(--ld-color-text-muted);
}

.lp-step h3 {
  font-size: 20px;
}

.lp-step p {
  margin: 0;
  color: var(--ld-color-text-muted);
  font-size: 15px;
}

.lp-step--current {
  border-color: var(--ld-color-primary);
  box-shadow: 0 0 0 1px var(--ld-color-primary);
}

.lp-tag {
  justify-self: start;
  font: 500 12px/1 var(--ld-font-body);
  padding: 6px 10px;
  border-radius: 9999px;
}

.lp-tag--live {
  background: var(--ld-color-success-strong);
  color: #fff;
}

.lp-tag--soon {
  background: var(--ld-color-surface-2);
  color: var(--ld-color-text-muted);
  border: 1px solid var(--ld-color-border);
}

@media (max-width: 820px) {
  .lp-route {
    grid-template-columns: 1fr;
  }
}

/* Funciones */
.lp-feats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 28px 32px;
}

.lp-feat {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: 14px;
}

.lp-feat svg {
  width: 40px;
  height: 40px;
  stroke: var(--ld-color-primary);
  fill: none;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.lp-feat h3 {
  font-size: 17px;
  margin-bottom: 4px;
}

.lp-feat p {
  margin: 0;
  font-size: 15px;
  color: var(--ld-color-text-muted);
}

@media (max-width: 900px) {
  .lp-feats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .lp-feats {
    grid-template-columns: 1fr;
  }
}

/* Docentes */
.lp-teach {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
  gap: 40px;
  align-items: start;
}

.lp-flow {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
  counter-reset: f;
}

.lp-flow li {
  counter-increment: f;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 14px;
  background: var(--ld-color-surface);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  padding: 16px;
}

.lp-flow li::before {
  content: counter(f);
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--ld-color-primary);
  color: var(--ld-color-primary-contrast);
  font: 700 15px var(--ld-font-heading);
}

.lp-flow b {
  display: block;
  font-family: var(--ld-font-heading);
}

.lp-flow span {
  color: var(--ld-color-text-muted);
  font-size: 15px;
}

.lp-grades {
  background: var(--ld-color-surface);
  border: 1px solid var(--ld-color-border);
  border-radius: 16px;
  box-shadow: var(--ld-shadow-md);
  overflow: hidden;
  min-width: 0;
}

.lp-grades header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--ld-color-border);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.lp-grades header b {
  font-family: var(--ld-font-heading);
}

.lp-grades header span {
  font-size: 13px;
  color: var(--ld-color-text-muted);
}

.lp-tbl {
  overflow-x: auto;
}

.lp-tbl table {
  border-collapse: collapse;
  width: 100%;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.lp-tbl th,
.lp-tbl td {
  text-align: left;
  padding: 10px 18px;
  border-bottom: 1px solid var(--ld-color-border);
  white-space: nowrap;
}

.lp-tbl th {
  font: 500 12px var(--ld-font-body);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ld-color-text-muted);
  background: var(--ld-color-surface-2);
}

.lp-st {
  font-size: 12px;
  padding: 4px 9px;
  border-radius: 9999px;
  font-weight: 500;
}

.lp-st--ok {
  background: color-mix(in srgb, var(--ld-color-success-strong) 15%, transparent);
  color: var(--ld-color-success-strong);
}

.lp-st--late {
  background: color-mix(in srgb, var(--ld-color-accent) 18%, transparent);
  color: var(--ld-color-accent-text);
}

.lp-st--ret {
  background: var(--ld-color-surface-2);
  color: var(--ld-color-text-muted);
}

.lp-example {
  font-size: 12px;
  color: var(--ld-color-text-muted);
  padding: 10px 18px;
  margin: 0;
}

@media (max-width: 860px) {
  .lp-teach {
    grid-template-columns: 1fr;
  }
}

/* Agente */
.lp-agent {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 32px;
  align-items: center;
  background: var(--ld-color-surface);
  border: 1px solid var(--ld-color-border);
  border-radius: 16px;
  padding: 32px;
}

.lp-agent__title {
  font-size: 28px;
}

.lp-agent__lead {
  font-size: 16px;
  margin-top: 8px;
}

.lp-agent__dl {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 20px;
}

.lp-agent ul {
  margin: 0;
  padding-left: 18px;
  color: var(--ld-color-text-muted);
  font-size: 15px;
  display: grid;
  gap: 6px;
}

@media (max-width: 820px) {
  .lp-agent {
    grid-template-columns: 1fr;
    padding: 24px;
  }
}

/* Equipo */
.lp-team {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 40px;
  align-items: start;
}

.lp-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.lp-fact {
  border-top: 3px solid var(--ld-color-primary);
  padding-top: 12px;
}

.lp-fact b {
  display: block;
  font: 800 28px var(--ld-font-heading);
  overflow-wrap: anywhere;
}

.lp-fact span {
  color: var(--ld-color-text-muted);
  font-size: 14px;
}

.lp-credits {
  margin-top: 20px;
  background: var(--ld-color-surface-2);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-sm);
  padding: 14px 16px;
}

.lp-credits__title {
  margin: 0 0 8px;
  font: 700 16px var(--ld-font-heading);
}

.lp-credits__list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  font-size: 15px;
}

.lp-credits__aff {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--ld-color-text-muted);
}

@media (max-width: 820px) {
  .lp-team {
    grid-template-columns: 1fr;
  }
}

/* Cierre y pie */
.lp-final {
  background: var(--ld-color-primary-strong);
  color: #fff;
}

.lp-final__inner {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  align-items: center;
  justify-content: space-between;
  padding-block: 48px;
}

.lp-final h2 {
  font-size: 28px;
  max-width: 26ch;
}

.lp-footer {
  background: var(--ld-color-brand-deep);
  color: #b9cbde;
  font-size: 14px;
}

.lp .lp-footer a {
  color: var(--lp-on-deep-link);
}

.lp-footer__grid {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 24px;
  align-items: center;
  padding-block: 28px;
}

.lp-footer img {
  height: 44px;
  width: auto;
}

@media (max-width: 760px) {
  .lp-footer__grid {
    grid-template-columns: 1fr;
  }
}
</style>
