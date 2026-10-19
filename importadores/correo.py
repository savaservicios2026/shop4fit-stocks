#!/usr/bin/env python3
"""Importa a «Solicitudes» los correos que llegan al buzón de empresa (IMAP), sin marcarlos como leídos.

Cada remitente es una solicitud; sus correos se van añadiendo como mensajes. Se ejecuta cada 10 minutos
desde GitHub Actions (.github/workflows/importar-correo.yml) con estos secretos del repositorio:
  IMAP_SERVIDOR, IMAP_USUARIO, IMAP_CLAVE   buzón de correo (en Gmail, «contraseña de aplicación»)
  IMPORTADOR_CLAVE                          contraseña del usuario importador@shop4fit-stocks.firebaseapp.com
  IMAP_CARPETA (opcional)                   carpeta a leer; por defecto INBOX
"""
import datetime, email, email.header, email.policy, email.utils, hashlib, html, imaplib, os, re, sys
from firestore import Firestore, id_documento

MAX_POR_VEZ = 60
DIAS_PRIMERA_VEZ = 3
IGNORAR = re.compile(r"no-?reply|mailer-daemon|postmaster|notificaciones?@|notifications?@|newsletter|bounce", re.I)


def texto_de(msg):
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
    # Quita la parte citada de respuestas anteriores
    t = re.split(r"\n(?:El .{5,120} escribió:|On .{5,120} wrote:|-{2,} ?Mensaje original|-{2,} ?Original Message|De: .+\nEnviado)", t)[0]
    t = "\n".join(l for l in t.splitlines() if not l.startswith(">"))
    return re.sub(r"\n{3,}", "\n\n", t).strip()[:8000]


def telefono_en(texto):
    for m in re.findall(r"(?:\+|00)?\d[\d\s.\-()]{7,}\d", texto):
        d = re.sub(r"\D", "", m)
        d = d[2:] if d.startswith("00") else d
        if re.fullmatch(r"[6789]\d{8}", d):
            d = "34" + d
        if 9 <= len(d) <= 15:
            return d
    return ""


def es_automatico(msg, remitente, propio):
    if not remitente or remitente == propio or IGNORAR.search(remitente):
        return True
    if msg.get("List-Unsubscribe") or msg.get("List-Id") or (msg.get("Precedence", "").lower() in ("bulk", "list", "junk")):
        return True
    return msg.get("Auto-Submitted", "no").lower() != "no"


def main():
    falta = [k for k in ("IMAP_SERVIDOR", "IMAP_USUARIO", "IMAP_CLAVE", "IMPORTADOR_CLAVE") if not os.environ.get(k)]
    if falta:
        print("Importador de correo sin configurar (faltan secretos: %s). No se hace nada." % ", ".join(falta))
        return
    usuario = os.environ["IMAP_USUARIO"].strip().lower()
    fs = Firestore(os.environ["IMPORTADOR_CLAVE"])
    estado = fs.leer("importador/correo") or {}

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
        if not crudo:
            continue
        msg = email.message_from_bytes(crudo, policy=email.policy.default)
        nombre, remitente = email.utils.parseaddr(str(msg.get("Reply-To") or msg.get("From") or ""))
        remitente = remitente.lower()
        if es_automatico(msg, remitente, usuario):
            continue
        if not nombre:
            nombre = email.utils.parseaddr(str(msg.get("From") or ""))[0]
        try:
            fecha = email.utils.parsedate_to_datetime(msg["Date"]).astimezone(datetime.timezone.utc)
        except Exception:
            fecha = datetime.datetime.now(datetime.timezone.utc)
        fecha = fecha.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        asunto = str(msg.get("Subject") or "").strip()[:200]
        mid = str(msg.get("Message-ID") or "%s-%s" % (validez, uid))
        mensaje = {"id": "correo-" + hashlib.sha1(mid.encode()).hexdigest()[:16], "fecha": fecha, "canal": "correo",
                   "de": ("%s <%s>" % (nombre, remitente)) if nombre else remitente, "asunto": asunto, "texto": texto_de(msg)}
        nueva = {"canal": "correo", "nombre": nombre, "empresa": "", "telefono": telefono_en(mensaje["texto"]), "email": remitente, "asunto": re.sub(r"^((re|rv|fw|fwd)\s*:\s*)+", "", asunto, flags=re.I),
                 "nota": "", "fecha": fecha, "ultimo": fecha, "estado": "nueva", "sinLeer": True, "pedidosCliente": [], "autor": "importador-correo"}
        r = fs.anadir_a_solicitud(id_documento("correo", remitente), nueva, mensaje)
        print("  %s: %s (%s)" % (r, remitente, asunto[:60]))
        fs.escribir("importador/correo", {"uidvalidity": validez, "ultimoUid": ultimo})

    if not uids and not desde:
        ultimo = siguiente - 1  # primera vez sin correos recientes: empezar desde ahora
    if ultimo != desde or estado.get("uidvalidity") != validez:
        fs.escribir("importador/correo", {"uidvalidity": validez, "ultimoUid": ultimo})
    imap.logout()


if __name__ == "__main__":
    main()
