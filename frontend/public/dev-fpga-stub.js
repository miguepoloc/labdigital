// SÓLO DESARROLLO: window.JGFPGA falso con el mismo comportamiento documentado en JG FPGA docs/EMBED.md:
// getProject / loadProject (lanza si el formato no es válido, no emite change) / readOnly / getReport /
// getReportDocx / getLastBitstream / on("change"|"ready") / off, y postMessage jgfpga:ready al padre.
;(function () {
  'use strict'
  var FORMAT = 'basys3-sim-project'
  var listeners = { change: new Set(), ready: new Set() }
  var state = { ready: false, readOnly: false, timer: 0, last: '', report: null }
  var project = {
    name: 'proyecto',
    top: 'top',
    simTop: '',
    files: [{ name: 'top.vhd', role: 'design', text: '-- caché del módulo (stub)\n' }],
  }
  var $files = document.getElementById('files')
  var $name = document.getElementById('projName')
  var $ro = document.getElementById('ro')
  var $log = document.getElementById('log')

  function log(msg) {
    $log.textContent = new Date().toLocaleTimeString() + ' ' + msg + '\n' + $log.textContent
  }

  function emit(event, arg) {
    listeners[event].forEach(function (fn) {
      try {
        fn(arg)
      } catch (e) {
        console.error(e)
      }
    })
  }

  function snapshot() {
    return JSON.parse(
      JSON.stringify({
        format: FORMAT,
        version: 1,
        name: project.name,
        top: project.top || '',
        simTop: project.simTop || '',
        files: project.files,
        report: state.report,
      }),
    )
  }

  function changed() {
    clearTimeout(state.timer)
    state.timer = setTimeout(function () {
      var p = snapshot()
      var s = JSON.stringify(p)
      if (s === state.last) return
      state.last = s
      log('change')
      emit('change', p)
    }, 1000)
  }

  function render() {
    $name.value = project.name
    $name.readOnly = state.readOnly
    $ro.hidden = !state.readOnly
    document.getElementById('addFile').disabled = state.readOnly
    $files.textContent = ''
    project.files.forEach(function (f) {
      var label = document.createElement('label')
      label.textContent = f.name + ' (' + f.role + ')'
      var ta = document.createElement('textarea')
      ta.value = f.text
      ta.readOnly = state.readOnly
      ta.addEventListener('input', function () {
        f.text = ta.value
        changed()
      })
      label.appendChild(ta)
      $files.appendChild(label)
    })
  }

  $name.addEventListener('input', function () {
    project.name = $name.value.slice(0, 60)
    changed()
  })
  document.getElementById('addFile').addEventListener('click', function () {
    project.files.push({
      name: 'archivo' + (project.files.length + 1) + '.vhd',
      role: 'design',
      text: '',
    })
    render()
    changed()
  })

  window.JGFPGA = Object.freeze({
    version: '1',
    getProject: snapshot,
    loadProject: function (content, opts) {
      if (!content || typeof content !== 'object' || Array.isArray(content))
        throw new TypeError('JGFPGA.loadProject: content debe ser un objeto')
      if (content.format != null && content.format !== FORMAT)
        throw new Error('JGFPGA.loadProject: formato desconocido «' + content.format + '»')
      if (content.version != null && content.version !== 1)
        throw new Error('JGFPGA.loadProject: versión no soportada ' + content.version)
      if (!Array.isArray(content.files))
        throw new TypeError('JGFPGA.loadProject: files debe ser una lista')
      var skipped = []
      project = {
        name: String(content.name || 'proyecto').slice(0, 60),
        top: content.top || '',
        simTop: content.simTop || content.sim_top || '',
        files: content.files
          .filter(function (f) {
            var ok = typeof f.name === 'string' && /^[\w.-]+$/.test(f.name)
            if (!ok) skipped.push(String(f.name) + ': nombre inválido')
            return ok
          })
          .map(function (f) {
            return { name: f.name, role: f.role || 'design', text: String(f.text || '') }
          }),
      }
      state.report = content.report || null
      state.readOnly = !!(opts && opts.readOnly)
      state.last = JSON.stringify(snapshot())
      clearTimeout(state.timer)
      render()
      log('loadProject ' + (state.readOnly ? '(solo lectura)' : ''))
      return skipped
    },
    readOnly: function () {
      return state.readOnly
    },
    getReport: function () {
      return state.report ? JSON.parse(JSON.stringify(state.report)) : null
    },
    getReportDocx: function () {
      return Promise.resolve(
        state.report ? new Blob(['informe (stub)'], { type: 'application/octet-stream' }) : null,
      )
    },
    getLastBitstream: function () {
      return Promise.resolve({ name: 'top.bit', blob: new Blob(['bit (stub)']) })
    },
    on: function (event, fn) {
      if (!listeners[event] || typeof fn !== 'function') return
      listeners[event].add(fn)
      if (event === 'ready' && state.ready)
        setTimeout(function () {
          if (listeners.ready.has(fn)) fn()
        }, 0)
    },
    off: function (event, fn) {
      if (listeners[event]) listeners[event].delete(fn)
    },
  })

  render()
  state.last = JSON.stringify(snapshot())
  state.ready = true
  emit('ready')
  if (window.parent !== window)
    window.parent.postMessage({ type: 'jgfpga:ready', version: '1' }, location.origin)
})()
