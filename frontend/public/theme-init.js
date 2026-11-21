// Aplica el tema guardado antes del primer pintado (evita parpadeo). Ver src/lib/theme.ts.
try {
  var th = localStorage.getItem('ld-theme')
  if (th === 'light' || th === 'dark') document.documentElement.setAttribute('data-theme', th)
} catch {
  /* sin almacenamiento */
}
