/**
 * XMLHttpRequest mínimo sobre `fetch` para los tests: el XHR de jsdom no pasa por MSW, y `uploadFile`
 * usa XHR para tener progreso de subida. Emite un evento de progreso al 50 % y otro al 100 %.
 */
export class FakeXhr {
  static progressEvents: { loaded: number; total: number }[] = []
  status = 0
  responseText = ''
  withCredentials = false
  upload: {
    onprogress: ((ev: { lengthComputable: boolean; loaded: number; total: number }) => void) | null
  } = {
    onprogress: null,
  }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  private method = 'GET'
  private url = ''
  private headers: Record<string, string> = {}
  private response: Response | null = null

  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }
  getResponseHeader(name: string) {
    return this.response?.headers.get(name) ?? null
  }
  abort() {
    this.onabort?.()
  }
  send(body: FormData | null) {
    const total = (body?.get('file') as File | null)?.size ?? 0
    for (const loaded of [total / 2, total]) {
      FakeXhr.progressEvents.push({ loaded, total })
      this.upload.onprogress?.({ lengthComputable: true, loaded, total })
    }
    // El FormData de jsdom no lo serializa el `fetch` de Node: se arma el multipart a mano.
    toMultipart(body)
      .then(([payload, type]) =>
        fetch(this.url, {
          method: this.method,
          headers: type ? { ...this.headers, 'Content-Type': type } : this.headers,
          body: payload,
        }),
      )
      .then(async (res) => {
        this.response = res
        this.status = res.status
        this.responseText = await res.text()
        this.onload?.()
      })
      .catch(() => this.onerror?.())
  }
}

function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

async function toMultipart(body: FormData | null): Promise<[string | null, string | null]> {
  if (!body) return [null, null]
  const boundary = '----ldtest' + Math.random().toString(16).slice(2)
  let out = ''
  for (const [name, value] of body.entries()) {
    out += `--${boundary}\r\n`
    if (typeof value === 'string') {
      out += `Content-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`
    } else {
      out += `Content-Disposition: form-data; name="${name}"; filename="${value.name}"\r\n`
      out += `Content-Type: ${value.type || 'application/octet-stream'}\r\n\r\n`
      out += `${await readBlob(value)}\r\n`
    }
  }
  out += `--${boundary}--\r\n`
  return [out, `multipart/form-data; boundary=${boundary}`]
}
