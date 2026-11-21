<script lang="ts">
/**
 * Pinta Markdown limitado SIN `v-html`: el árbol de `parseMarkdown` se convierte en VNodes y todo el
 * texto va en nodos de texto (escapados por Vue). Ver `src/lib/markdown.ts`.
 */
import { defineComponent, h, type VNode, type VNodeArrayChildren } from 'vue'
import { parseMarkdown, type Block, type Inline } from '@/lib/markdown'

function inlines(nodes: Inline[]): VNodeArrayChildren {
  return nodes.map((n): VNode | string => {
    switch (n.t) {
      case 'text':
        return n.v
      case 'code':
        return h('code', n.v)
      case 'strong':
        return h('strong', inlines(n.c))
      case 'em':
        return h('em', inlines(n.c))
      case 'br':
        return h('br')
      case 'link': {
        if (!n.href) return h('span', inlines(n.c))
        const external = /^(https?:|mailto:)/i.test(n.href)
        return h(
          'a',
          external
            ? { href: n.href, target: '_blank', rel: 'noopener noreferrer nofollow' }
            : { href: n.href },
          inlines(n.c),
        )
      }
    }
  })
}

function blocks(list: Block[], baseLevel: number): VNode[] {
  return list.map((b) => {
    switch (b.t) {
      case 'heading':
        return h(`h${Math.min(6, b.level + baseLevel - 1)}`, inlines(b.c))
      case 'p':
        return h('p', inlines(b.c))
      case 'hr':
        return h('hr')
      case 'code':
        return h('pre', h('code', b.lang ? { 'data-lang': b.lang } : null, b.v))
      case 'quote':
        return h('blockquote', blocks(b.c, baseLevel))
      case 'list':
        return h(
          b.ordered ? 'ol' : 'ul',
          b.ordered && b.start !== 1 ? { start: b.start } : null,
          b.items.map((item) => h('li', inlines(item))),
        )
    }
  })
}

export default defineComponent({
  name: 'LdMarkdown',
  props: {
    source: { type: String, default: '' },
    /** Nivel HTML que corresponde a `#` (2 por defecto: la página ya tiene su h1). */
    baseLevel: { type: Number, default: 2 },
  },
  setup(props) {
    return () => h('div', { class: 'ld-md' }, blocks(parseMarkdown(props.source), props.baseLevel))
  },
})
</script>

<style scoped>
.ld-md {
  line-height: var(--ld-leading-normal);
  overflow-wrap: anywhere;
}

.ld-md :deep(h2),
.ld-md :deep(h3),
.ld-md :deep(h4) {
  margin: var(--ld-space-5) 0 var(--ld-space-2);
}

.ld-md :deep(h2) {
  font-size: var(--ld-text-xl);
}

.ld-md :deep(h3) {
  font-size: var(--ld-text-lg);
}

.ld-md :deep(> :first-child) {
  margin-top: 0;
}

.ld-md :deep(code) {
  font-family: var(--ld-font-mono);
  font-size: 0.9em;
  padding: 0.05rem 0.3rem;
  border-radius: var(--ld-radius-sm);
  background: var(--ld-color-surface-2);
}

.ld-md :deep(pre) {
  overflow-x: auto;
  padding: var(--ld-space-3) var(--ld-space-4);
  border-radius: var(--ld-radius-md);
  background: var(--ld-color-surface-2);
  border: 1px solid var(--ld-color-border);
}

.ld-md :deep(pre code) {
  padding: 0;
  background: none;
}

.ld-md :deep(blockquote) {
  margin: var(--ld-space-3) 0;
  padding: var(--ld-space-2) var(--ld-space-4);
  border-left: 4px solid var(--ld-color-border);
  color: var(--ld-color-text-muted);
}

.ld-md :deep(hr) {
  border: 0;
  border-top: 1px solid var(--ld-color-border);
  margin: var(--ld-space-5) 0;
}

.ld-md :deep(a) {
  color: var(--ld-color-link);
}
</style>
