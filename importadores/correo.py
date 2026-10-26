#!/usr/bin/env python3
"""Importa a «Solicitudes» los correos de clientes que llegan al buzón de empresa, sin marcarlos como leídos.

Cada remitente es una solicitud; sus correos se van añadiendo como mensajes. Solo entran los que parecen
una petición (presupuesto, oferta, precio…) y no vienen de un remitente marcado en la app como «ignorar».
Se ejecuta cada 10 minutos desde GitHub Actions (.github/workflows/importar-correo.yml) con secretos:
  IMPORTADOR_CLAVE                          contraseña del usuario importador@shop4fit-stocks.firebaseapp.com
  Microsoft 365 (Outlook):  M365_TENANT, M365_CLIENTE, M365_SECRETO, M365_BUZON
  Otros buzones por IMAP:   IMAP_SERVIDOR, IMAP_USUARIO, IMAP_CLAVE (en Gmail, «contraseña de aplicación»),
                            IMAP_CARPETA opcional (INBOX por defecto)
  CORREO_TODO = "si"        opcional: importar todos los correos, no solo los que parecen peticiones
"""
import datetime, email, email.header, email.policy, email.utils, hashlib, html, imaplib, json, os, re, sys, urllib.parse, urllib.request
from firestore import Firestore, id_documento

MAX_POR_VEZ = 60
DIAS_PRIMERA_VEZ = 3
IGNORAR = re.compile(r"no-?reply|mailer-daemon|postmaster|notificaciones?@|notifications?@|newsletter|bounce", re.I)
PETICION = re.compile(r"presupuest|oferta|cotizaci|precio|tarifa|solicitud|lead|interesad|informaci[oó]n sobre|cu[aá]nto cuesta|me gustar[ií]a|quisiera|necesit", re.I)


def telefono_en(texto):
    for m in re.findall(r"(?:\+|00)?\d[\d\s.\-()]{7,}\d", texto):
        d = re.sub(r"\D", "", m)
        d = d[2:] if d.startswith("00") else d
        if re.fullmatch(r"[6789]\d{8}", d):
            d = "34" + d
        if 9 <= len(d) <= 15:
            return d
    return ""


def es_automatico(cab, remitente, propio):
    """cab(nombre) devuelve la cabecera del correo o ""."""
    if not remitente or remitente == propio or IGNORAR.search(remitente):
        return True
    if remitente.split("@")[-1] == propio.split("@")[-1]:  # correos internos de la propia empresa
        return True
    if cab("List-Unsubscribe") or cab("List-Id") or cab("Precedence").lower() in ("bulk", "list", "junk"):
        return True
    return (cab("Auto-Submitted") or "no").lower() != "no"


class Importador:
    def __init__(self, propio):
        self.propio = propio.strip().lower()
        self.fs = Firestore(os.environ["IMPORTADOR_CLAVE"])
        self.todo = os.environ.get("CORREO_TODO", "").lower() in ("si", "sí", "1", "true")
        lista = (self.fs.leer("importador/ignorados") or {}).get("remitentes") or []
        self.ignorados = {x.strip().lower() for x in lista if x}

    def guardar(self, cab, nombre, remitente, fecha, asunto, texto, mid):
        """Crea o amplía la solicitud del remitente si el correo parece de un cliente. Devuelve True si se guardó."""
        remitente = remitente.strip().lower()
        if es_automatico(cab, remitente, self.propio):
            return False
        if remitente in self.ignorados or "@" + remitente.split("@")[-1] in self.ignorados:
            return False
        if not self.todo and not PETICION.search(asunto + "\n" + texto[:3000]):
            return False
        asunto = asunto.strip()[:200]
        mensaje = {"id": "correo-" + hashlib.sha1(mid.encode()).hexdigest()[:16], "fecha": fecha, "canal": "correo",
                   "de": ("%s <%s>" % (nombre, remitente)) if nombre else remitente, "asunto": asunto, "texto": texto}
        nueva = {"canal": "correo", "nombre": nombre, "empresa": "", "telefono": telefono_en(texto), "email": remitente,
                 "asunto": re.sub(r"^((re|rv|fw|fwd)\s*:\s*)+", "", asunto, flags=re.I), "nota": "", "fecha": fecha, "ultimo": fecha,
                 "estado": "nueva", "sinLeer": True, "pedidosCliente": [], "autor": "importador-correo"}
        r = self.fs.anadir_a_solicitud(id_documento("correo", remitente), nueva, mensaje)
        print("  %s: %s (%s)" % (r, remitente, asunto[:60]))
        return True


def limpiar(t):
    # Quita la parte citada de respuestas anteriores
    t = re.split(r"\n(?:El .{5,120} escribió:|On .{5,120} wrote:|-{2,} ?Mensaje original|-{2,} ?Original Message|_{10,}|De: .+\n(?:Enviado|Fecha|Date))", "\n" + t)[0]
    t = "\n".join(l for l in t.splitlines() if not l.startswith(">"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()[:8000]


def iso(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _http(url, datos=None, cabeceras=None):
    r = urllib.request.Request(url, data=datos, headers=cabeceras or {})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read())


def desde_m365():
    """Microsoft 365 / Outlook por Microsoft Graph (aplicación registrada en Entra ID con permiso Mail.Read)."""
    buzon = os.environ["M365_BUZON"].strip().lower()
    imp = Importador(buzon)
    tok = _http("https://login.microsoftonline.com/%s/oauth2/v2.0/token" % os.environ["M365_TENANT"].strip(), urllib.parse.urlencode({
        "client_id": os.environ["M365_CLIENTE"].strip(), "client_secret": os.environ["M365_SECRETO"].strip(),
        "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"}).encode())["access_token"]
    estado = imp.fs.leer("importador/correo") or {}
    desde = estado.get("ultimaFecha") or iso(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DIAS_PRIMERA_VEZ))
    url = "https://graph.microsoft.com/v1.0/users/%s/mailFolders/inbox/messages?%s" % (urllib.parse.quote(buzon), urllib.parse.urlencode({
        "$filter": "receivedDateTime gt %s" % desde, "$orderby": "receivedDateTime asc", "$top": str(MAX_POR_VEZ),
        "$select": "subject,from,replyTo,receivedDateTime,internetMessageId,body,inferenceClassification,internetMessageHeaders"}))
    lista = _http(url, cabeceras={"Authorization": "Bearer " + tok, "Prefer": 'outlook.body-content-type="text"'}).get("value", [])
    print("%d correos nuevos en %s" % (len(lista), buzon))
    ultima, n = desde, 0
    for m in lista:
        cabs = {h["name"].lower(): h["value"] for h in m.get("internetMessageHeaders") or []}
        dir_ = ((m.get("replyTo") or [None])[0] or m.get("from") or {}).get("emailAddress", {})
        nombre = dir_.get("name") or (m.get("from") or {}).get("emailAddress", {}).get("name", "")
        remitente = dir_.get("address", "")
        if nombre.lower() == remitente.lower():
            nombre = ""
        fecha = iso(datetime.datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")))
        if m.get("inferenceClassification") == "other" and not imp.todo:
            pass  # bandeja «Otros» de Outlook: publicidad y avisos
        elif imp.guardar(lambda k: cabs.get(k.lower(), ""), nombre, remitente, fecha, m.get("subject") or "",
                         limpiar((m.get("body") or {}).get("content") or ""), m.get("internetMessageId") or m["receivedDateTime"] + remitente):
            n += 1
        ultima = m["receivedDateTime"]
        imp.fs.escribir("importador/correo", {"ultimaFecha": ultima})
    if not lista and not estado.get("ultimaFecha"):
        imp.fs.escribir("importador/correo", {"ultimaFecha": desde})
    print("%d solicitudes creadas o ampliadas" % n)


def texto_imap(msg):
    cuerpo = msg.get_body(preferencelist=("plain", "html"))
    if cuerpo is None:
        return ""
    try:
        t = cuerpo.get_content()
    except Exception:
        t = (cuerpo.get_payload(decode=True) or b"").decode("latin-1", "replace")
    if cuerpo.get_content_type() == "text/html":
        t = re.sub(r"(?is)<(script|style).*?</\1>", "", t)
        t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", t)
        t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return limpiar(t)


def desde_imap():
    usuario = os.environ["IMAP_USUARIO"].strip().lower()
    imp = Importador(usuario)
    estado = imp.fs.leer("importador/correo") or {}
    imap = imaplib.IMAP4_SSL(os.environ["IMAP_SERVIDOR"].strip())
    imap.login(usuario, os.environ["IMAP_CLAVE"])
    carpeta = os.environ.get("IMAP_CARPETA") or "INBOX"
    typ, _ = imap.select('"%s"' % carpeta, readonly=True)
    if typ != "OK":
        sys.exit("No existe la carpeta %s" % carpeta)
    st = imap.status('"%s"' % carpeta, "(UIDVALIDITY UIDNEXT)")[1][0]
    validez = int(re.search(rb"UIDVALIDITY (\d+)", st).group(1))
    siguiente = int(re.search(rb"UIDNEXT (\d+)", st).group(1))
    if estado.get("uidvalidity") == validez and estado.get("ultimoUid"):
        desde = int(estado["ultimoUid"])
        _, d = imap.uid("SEARCH", None, "UID %d:*" % (desde + 1))
    else:
        desde = 0
        fecha = (datetime.date.today() - datetime.timedelta(days=DIAS_PRIMERA_VEZ)).strftime("%d-%b-%Y")
        _, d = imap.uid("SEARCH", None, "SINCE", fecha)
    uids = sorted(u for u in map(int, d[0].split()) if u > desde)[:MAX_POR_VEZ]
    print("%d correos nuevos en %s" % (len(uids), carpeta))
    ultimo = desde
    for uid in uids:
        _, partes = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
        crudo = next((p[1] for p in partes if isinstance(p, tuple)), None)
        ultimo = uid
        if crudo:
            msg = email.message_from_bytes(crudo, policy=email.policy.default)
            nombre, remitente = email.utils.parseaddr(str(msg.get("Reply-To") or msg.get("From") or ""))
            nombre = nombre or email.utils.parseaddr(str(msg.get("From") or ""))[0]
            try:
                fecha = iso(email.utils.parsedate_to_datetime(msg["Date"]))
            except Exception:
                fecha = iso(datetime.datetime.now(datetime.timezone.utc))
            imp.guardar(lambda k: str(msg.get(k) or ""), nombre, remitente, fecha, str(msg.get("Subject") or ""), texto_imap(msg),
                        str(msg.get("Message-ID") or "%s-%s" % (validez, uid)))
        imp.fs.escribir("importador/correo", {"uidvalidity": validez, "ultimoUid": ultimo})
    if not uids and not desde:
        imp.fs.escribir("importador/correo", {"uidvalidity": validez, "ultimoUid": siguiente - 1})  # empezar desde ahora
    imap.logout()


def main():
    if not os.environ.get("IMPORTADOR_CLAVE"):
        print("Importador de correo sin configurar (falta el secreto IMPORTADOR_CLAVE). No se hace nada.")
    elif all(os.environ.get(k) for k in ("M365_TENANT", "M365_CLIENTE", "M365_SECRETO", "M365_BUZON")):
        desde_m365()
    elif all(os.environ.get(k) for k in ("IMAP_SERVIDOR", "IMAP_USUARIO", "IMAP_CLAVE")):
        desde_imap()
    else:
        print("Importador de correo sin configurar (faltan los datos del buzón). No se hace nada.")


if __name__ == "__main__":
    main()
