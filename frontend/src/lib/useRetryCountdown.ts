import { computed, onBeforeUnmount, ref } from 'vue'

/** Cuenta atrás para `Retry-After`: deshabilita el envío mientras `seconds > 0`. */
export function useRetryCountdown() {
  const seconds = ref(0)
  let timer: ReturnType<typeof setInterval> | undefined

  function stop() {
    if (timer) clearInterval(timer)
    timer = undefined
  }

  function start(s: number | undefined) {
    stop()
    seconds.value = Math.max(0, Math.ceil(s ?? 0))
    if (seconds.value <= 0) return
    timer = setInterval(() => {
      seconds.value--
      if (seconds.value <= 0) stop()
    }, 1000)
  }

  onBeforeUnmount(stop)
  return { seconds, waiting: computed(() => seconds.value > 0), start }
}
