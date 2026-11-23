"""Plantillas de correo transaccional (español, trato de tú) con la marca LabDigital GIDEAM.

Funciones puras: devuelven un `EmailMessage` (texto + HTML) que el servicio registra en el
outbox. El HTML está pensado para Gmail, Outlook y el correo institucional: maquetación con
tablas, ancho máximo 600 px, estilos en línea (el `<style>` sólo añade modo oscuro y móvil
donde el cliente lo soporta), botón "a prueba de balas" y texto de previsualización oculto.
Los colores salen de los tokens del design system (`frontend/src/styles/tokens.css`).
Todo valor interpolado pasa por `html.escape`."""

import dataclasses
import datetime
import html

from backend.commons.domain import mail
from backend.identity.users.domain.model import aggregate

# ---- Tokens del design system (primitivas Unimagdalena + acentos de laboratorio) ----
_BLUE = "#004B87"
_BLUE_400 = "#005CAB"
_BLUE_600 = "#003A6B"
_BLUE_800 = "#00294B"
_ORANGE = "#D17900"
_ORANGE_300 = "#FF9400"
_PCB = "#0b6b3a"
_LED_GREEN = "#00A50B"
_N0 = "#FFFFFF"
_N50 = "#F5F7FA"
_N100 = "#EAEEF3"
_N200 = "#D5DCE5"
_N600 = "#4D5968"
_N800 = "#232B36"
_INFO_BG = "#E6F1FB"

_FONT_HEADING = "'Open Sans', Arial, Helvetica, sans-serif"
_FONT_BODY = "Roboto, Arial, Helvetica, sans-serif"
_FONT_MONO = "'Roboto Mono', Consolas, 'Courier New', monospace"

_ESCUDO_URL = "https://cdn.unimagdalena.edu.co/images/escudo/bg_dark/128.png"
_SITE_URL = "https://gideam.unimagdalena.edu.co/labdigital/"
_DATA_POLICY_URL = "https://www.unimagdalena.edu.co/Content/Public/Docs/ManualProteccionDeDatos.pdf"
_BRAND = "LabDigital GIDEAM"
_FOOTER_LINE = "LabDigital GIDEAM · Ingeniería Electrónica, Universidad del Magdalena · Santa Marta"
_NO_REPLY = "Correo automático, no respondas a este mensaje."
_IGNORE = "Si no solicitaste este correo, puedes ignorarlo."

# Los 16 LED de la Basys 3, con el mismo patrón encendido que la ilustración de la landing.
_LEDS_ON = frozenset({1, 3, 4, 7, 9, 12, 14})


@dataclasses.dataclass(frozen=True)
class _Action:
    label: str
    url: str


def _ttl_text(ttl: datetime.timedelta) -> str:
    minutes = int(ttl.total_seconds() // 60)
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hora" if hours == 1 else f"{hours} horas"
    return f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos"


# ---------------------------------------------------------------------------------------
# Piezas HTML
# ---------------------------------------------------------------------------------------


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def _preheader(text: str) -> str:
    # El relleno de &zwnj;&nbsp; evita que el cliente complete la vista previa con el cuerpo.
    filler = "&zwnj;&nbsp;" * 60
    return (
        '<div class="ld-preheader" style="display:none;font-size:1px;line-height:1px;'
        "max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;"
        f'color:{_N50}">{_e(text)}{filler}</div>'
    )


def _led_strip() -> str:
    cells = []
    for i in range(16):
        on = i in _LEDS_ON
        color = (_ORANGE_300 if i % 2 else _LED_GREEN) if on else _BLUE_800
        if i:
            cells.append('<td width="10" style="font-size:0;line-height:0">&nbsp;</td>')
        cells.append(
            f'<td width="8" height="8" bgcolor="{color}" style="width:8px;height:8px;'
            f'font-size:0;line-height:0;background-color:{color};border-radius:50%">&nbsp;</td>'
        )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="right">'
        f"<tr>{''.join(cells)}</tr></table>"
    )


def _header() -> str:
    return f"""
<tr><td class="ld-header" bgcolor="{_BLUE}" style="background-color:{_BLUE};padding:24px 32px 20px;border-radius:14px 14px 0 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td width="52" valign="middle" style="width:52px;padding-right:14px">
      <a href="{_SITE_URL}" style="text-decoration:none"><img src="{_ESCUDO_URL}" width="44" height="44" alt="Escudo de la Universidad del Magdalena" style="display:block;width:44px;height:44px;border:0;outline:none;color:{_N0};font-size:10px"></a>
    </td>
    <td valign="middle" style="font-family:{_FONT_HEADING};color:{_N0}">
      <a href="{_SITE_URL}" style="text-decoration:none;color:{_N0}"><span style="font-size:24px;line-height:28px;font-weight:800;letter-spacing:-0.3px;color:{_N0}">Lab<span style="color:{_ORANGE_300}">Digital</span></span></a><br>
      <span style="font-family:{_FONT_BODY};font-size:12px;line-height:18px;letter-spacing:1.2px;text-transform:uppercase;color:#BFD9F2">GIDEAM · Universidad del Magdalena</span>
    </td>
  </tr></table>
</td></tr>
<tr><td class="ld-strip" bgcolor="{_BLUE_600}" style="background-color:{_BLUE_600};padding:10px 32px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td class="ld-hide-sm" valign="middle" style="font-family:{_FONT_MONO};font-size:11px;line-height:14px;letter-spacing:1px;color:#8FB8DD">LD[15:0]</td>
    <td valign="middle" align="right">{_led_strip()}</td>
  </tr></table>
</td></tr>
<tr><td height="4" bgcolor="{_PCB}" style="height:4px;font-size:0;line-height:0;background-color:{_PCB}">&nbsp;</td></tr>"""


def _button(action: _Action, *, primary: bool) -> str:
    url = _e(action.url)
    label = _e(action.label)
    if primary:
        bg, fg, border = _BLUE, _N0, _BLUE
    else:
        bg, fg, border = _N0, _BLUE, _BLUE
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 auto">
  <tr><td class="{"ld-btn" if primary else "ld-btn-2"}" align="center" bgcolor="{bg}" style="background-color:{bg};border:2px solid {border};border-radius:8px;mso-padding-alt:14px 32px">
    <a href="{url}" target="_blank" style="display:inline-block;padding:14px 32px;font-family:{_FONT_HEADING};font-size:16px;line-height:20px;font-weight:700;color:{fg};text-decoration:none;border-radius:8px">{label}</a>
  </td></tr>
</table>"""


def _fallback_link(action: _Action, *, caption: str) -> str:
    url = _e(action.url)
    return (
        f'<p style="margin:0 0 6px;font-family:{_FONT_BODY};font-size:13px;line-height:20px;'
        f'color:{_N600}" class="ld-muted">{_e(caption)}</p>'
        f'<p style="margin:0 0 16px;font-family:{_FONT_MONO};font-size:12px;line-height:18px;'
        f'word-break:break-all;overflow-wrap:anywhere"><a href="{url}" target="_blank" '
        f'class="ld-link" style="color:{_BLUE_400};text-decoration:underline;word-break:break-all">{url}</a></p>'
    )


def _notice(text: str) -> str:
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px">
  <tr><td class="ld-notice" bgcolor="{_INFO_BG}" style="background-color:{_INFO_BG};border-left:4px solid {_ORANGE};border-radius:4px;padding:12px 16px;font-family:{_FONT_BODY};font-size:14px;line-height:21px;color:{_BLUE_800}">{_e(text)}</td></tr>
</table>"""


def _paragraph(text: str) -> str:
    return (
        f'<p class="ld-text" style="margin:0 0 16px;font-family:{_FONT_BODY};font-size:16px;'
        f'line-height:25px;color:{_N800}">{_e(text)}</p>'
    )


def _footer() -> str:
    link_style = f"color:{_BLUE_400};text-decoration:underline"
    return f"""
<tr><td class="ld-footer" style="padding:24px 32px 8px;font-family:{_FONT_BODY};font-size:12px;line-height:19px;color:{_N600};text-align:center">
  <p style="margin:0 0 8px;font-weight:700;color:{_N600}" class="ld-muted">{_e(_FOOTER_LINE)}</p>
  <p style="margin:0 0 8px"><a href="{_SITE_URL}" target="_blank" class="ld-link" style="{link_style}">gideam.unimagdalena.edu.co/labdigital</a>
  &nbsp;·&nbsp; <a href="{_DATA_POLICY_URL}" target="_blank" class="ld-link" style="{link_style}">Política de tratamiento de datos</a></p>
  <p style="margin:0;color:{_N600}" class="ld-muted">{_e(_NO_REPLY)}</p>
</td></tr>"""


_HEAD_STYLE = """
<style>
  :root { color-scheme: light dark; supported-color-schemes: light dark; }
  a[x-apple-data-detectors] { color: inherit !important; text-decoration: none !important; }
  @media only screen and (max-width: 620px) {
    .ld-container { width: 100% !important; }
    .ld-header, .ld-strip, .ld-body, .ld-footer { padding-left: 20px !important; padding-right: 20px !important; }
    .ld-title { font-size: 22px !important; line-height: 28px !important; }
    .ld-hide-sm { display: none !important; }
  }
  @media (prefers-color-scheme: dark) {
    .ld-bg { background-color: #0B1017 !important; }
    .ld-card { background-color: #141A22 !important; border-color: #232B36 !important; }
    .ld-title { color: #FFFFFF !important; }
    .ld-text { color: #EAEEF3 !important; }
    .ld-muted, .ld-footer { color: #8A96A6 !important; }
    .ld-notice { background-color: #00294B !important; color: #EAEEF3 !important; }
    .ld-btn-2 { background-color: #141A22 !important; }
    .ld-btn-2 a { color: #FFFFFF !important; }
    .ld-rule { border-color: #232B36 !important; }
    .ld-link { color: #6CB4F5 !important; }
  }
</style>"""


def _layout(
    *,
    subject: str,
    preheader: str,
    title: str,
    greeting: str,
    paragraphs: list[str],
    primary: _Action,
    secondary: _Action | None,
    notice: str,
    security: str,
) -> str:
    body_paragraphs = "".join(_paragraph(p) for p in paragraphs)
    buttons = _button(primary, primary=True)
    fallbacks = _fallback_link(primary, caption="¿El botón no funciona? Copia este enlace:")
    if secondary is not None:
        buttons += (
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
            '<tr><td height="12" style="height:12px;font-size:0;line-height:0">&nbsp;</td></tr>'
            "</table>" + _button(secondary, primary=False)
        )
        fallbacks += _fallback_link(secondary, caption=f"{secondary.label}:")
    return f"""<!DOCTYPE html>
<html lang="es" dir="ltr" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<meta name="format-detection" content="telephone=no, date=no, address=no, email=no, url=no">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{_e(subject)}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->{_HEAD_STYLE}
</head>
<body class="ld-bg" style="margin:0;padding:0;width:100%;background-color:{_N50};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%">
{_preheader(preheader)}
<table role="presentation" class="ld-bg" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{_N50}" style="background-color:{_N50}">
<tr><td align="center" style="padding:24px 12px">
<!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" align="center"><tr><td><![endif]-->
<table role="presentation" class="ld-container" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;margin:0 auto">
{_header()}
<tr><td class="ld-card ld-body" bgcolor="{_N0}" style="background-color:{_N0};padding:32px 32px 28px;border:1px solid {_N200};border-top:0;border-radius:0 0 14px 14px">
  <h1 class="ld-title" style="margin:0 0 20px;font-family:{_FONT_HEADING};font-size:26px;line-height:32px;font-weight:800;color:{_BLUE_800}">{_e(title)}</h1>
  <p class="ld-text" style="margin:0 0 16px;font-family:{_FONT_BODY};font-size:16px;line-height:25px;font-weight:700;color:{_N800}">{_e(greeting)}</p>
  {body_paragraphs}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center" style="padding:12px 0 28px">{buttons}</td></tr></table>
  {_notice(notice)}
  {fallbacks}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td class="ld-rule" style="border-top:1px solid {_N100};font-size:0;line-height:0;height:1px">&nbsp;</td></tr></table>
  <p class="ld-muted" style="margin:16px 0 0;font-family:{_FONT_BODY};font-size:13px;line-height:20px;color:{_N600}">{_e(security)}</p>
</td></tr>
{_footer()}
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr>
</table>
</body>
</html>
"""


# ---------------------------------------------------------------------------------------
# Texto plano
# ---------------------------------------------------------------------------------------


def _text(
    *,
    title: str,
    greeting: str,
    paragraphs: list[str],
    actions: list[_Action],
    notice: str,
    security: str,
) -> str:
    header = f"{_BRAND} · Universidad del Magdalena"
    lines = [header, "=" * len(header), "", title.upper(), "", greeting, ""]
    for paragraph in paragraphs:
        lines += [paragraph, ""]
    for action in actions:
        lines += [f"{action.label}:", action.url, ""]
    lines += [notice, security, "", "—", _FOOTER_LINE, _SITE_URL]
    lines += [f"Tratamiento de datos: {_DATA_POLICY_URL}", _NO_REPLY]
    return "\n".join(lines) + "\n"


def _message(
    *,
    to: str,
    subject: str,
    preheader: str,
    title: str,
    greeting: str,
    paragraphs: list[str],
    primary: _Action,
    secondary: _Action | None = None,
    notice: str,
    security: str = _IGNORE,
) -> mail.EmailMessage:
    actions = [primary] if secondary is None else [primary, secondary]
    return mail.EmailMessage(
        to=to,
        subject=subject,
        text=_text(
            title=title,
            greeting=greeting,
            paragraphs=paragraphs,
            actions=actions,
            notice=notice,
            security=security,
        ),
        html=_layout(
            subject=subject,
            preheader=preheader,
            title=title,
            greeting=greeting,
            paragraphs=paragraphs,
            primary=primary,
            secondary=secondary,
            notice=notice,
            security=security,
        ),
    )


# ---------------------------------------------------------------------------------------
# Correos
# ---------------------------------------------------------------------------------------


def verification(*, to: str, full_name: str, link: str) -> mail.EmailMessage:
    ttl = _ttl_text(aggregate.VERIFY_EMAIL_TTL)
    return _message(
        to=to,
        subject="Confirma tu correo — LabDigital GIDEAM",
        preheader=f"Un clic y tu cuenta de LabDigital queda activa. El enlace vence en {ttl}.",
        title="Confirma tu correo",
        greeting=f"¡Hola, {full_name}!",
        paragraphs=[
            "Gracias por registrarte en LabDigital GIDEAM, el laboratorio digital de "
            "Ingeniería Electrónica de la Universidad del Magdalena.",
            "Para activar tu cuenta solo falta confirmar que este correo es tuyo:",
        ],
        primary=_Action("Confirmar mi correo", link),
        notice=f"El enlace vence en {ttl}. Si caduca, puedes pedir uno nuevo desde la "
        "página de inicio de sesión.",
    )


def password_reset(*, to: str, full_name: str, link: str) -> mail.EmailMessage:
    ttl = _ttl_text(aggregate.PASSWORD_RESET_TTL)
    return _message(
        to=to,
        subject="Restablece tu contraseña — LabDigital GIDEAM",
        preheader=f"Elige una nueva contraseña para LabDigital. El enlace vence en {ttl}.",
        title="Restablece tu contraseña",
        greeting=f"Hola, {full_name}:",
        paragraphs=[
            "Recibimos una solicitud para restablecer la contraseña de tu cuenta de "
            "LabDigital GIDEAM. Usa el botón para elegir una nueva.",
            "Al cambiarla se cerrarán todas tus sesiones abiertas.",
        ],
        primary=_Action("Elegir nueva contraseña", link),
        notice=f"El enlace vence en {ttl} y solo puede usarse una vez.",
        security="Si no solicitaste este correo, puedes ignorarlo: tu contraseña actual "
        "sigue funcionando.",
    )


def already_registered(
    *, to: str, full_name: str, login_link: str, reset_link: str
) -> mail.EmailMessage:
    return _message(
        to=to,
        subject="Ya tienes una cuenta — LabDigital GIDEAM",
        preheader="Alguien intentó registrarse con tu correo, pero ya tienes una cuenta.",
        title="Ya tienes una cuenta",
        greeting=f"Hola, {full_name}:",
        paragraphs=[
            "Alguien intentó crear una cuenta de LabDigital GIDEAM con este correo, pero "
            "ya tienes una.",
            "Puedes entrar normalmente o, si olvidaste la contraseña, pedir una nueva.",
        ],
        primary=_Action("Entrar", login_link),
        secondary=_Action("Recuperar contraseña", reset_link),
        notice="No se creó ninguna cuenta nueva ni se cambió nada en la tuya.",
        security="Si no fuiste tú, puedes ignorar este correo: nadie puede entrar sin tu "
        "contraseña.",
    )
