"""Acceso mínimo a Firestore por REST con el usuario «importador» (solo biblioteca estándar de Python)."""
import json, re, urllib.parse, urllib.request, urllib.error, pathlib

CONFIG = pathlib.Path(__file__).resolve().parent.parent / "firebase-config.js"
IMPORTADOR = "importador@shop4fit-stocks.firebaseapp.com"


def _config():
    t = CONFIG.read_text(encoding="utf-8")
    return re.search(r'apiKey:\s*"([^"]+)"', t).group(1), re.search(r'projectId:\s*"([^"]+)"', t).group(1)


def _pedir(metodo, url, cuerpo=None, token=None):
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    r = urllib.request.Request(url, data=datos, method=metodo, headers={"Content-Type": "application/json"})
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _valor(v):
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, (list, tuple)):
        return {"arrayValue": {"values": [_valor(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: _valor(x) for k, x in v.items()}}}
    if v is None:
        return {"nullValue": None}
    return {"stringValue": str(v)}


def _python(v):
    if "mapValue" in v:
        return {k: _python(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "arrayValue" in v:
        return [_python(x) for x in v["arrayValue"].get("values", [])]
    if "integerValue" in v:
        return int(v["integerValue"])
    return next(iter(v.values()))


class Firestore:
    def __init__(self, clave):
        self.api_key, self.proyecto = _config()
        st, r = _pedir("POST", "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + self.api_key,
                       {"email": IMPORTADOR, "password": clave, "returnSecureToken": True})
        if st != 200:
            raise SystemExit("No se pudo iniciar sesión como %s en Firebase: %s" % (IMPORTADOR, r.get("error", {}).get("message", st)))
        self.token = r["idToken"]
        self.raiz = "projects/%s/databases/(default)/documents" % self.proyecto
        self.base = "https://firestore.googleapis.com/v1/" + self.raiz

    def leer(self, ruta):
        st, r = _pedir("GET", self.base + "/" + ruta, token=self.token)
        if st == 404:
            return None
        if st != 200:
            raise RuntimeError("Firestore %s: %s" % (st, r))
        return {k: _python(v) for k, v in r.get("fields", {}).items()}

    def escribir(self, ruta, datos):
        st, r = _pedir("PATCH", self.base + "/" + ruta, {"fields": {k: _valor(v) for k, v in datos.items()}}, self.token)
        if st != 200:
            raise RuntimeError("Firestore %s: %s" % (st, r))

    def anadir_a_solicitud(self, doc_id, nueva, mensaje):
        """Crea la solicitud si no existe; si ya existe, solo le añade el mensaje y la marca como no leída."""
        st, r = _pedir("POST", "%s/solicitudes?documentId=%s" % (self.base, urllib.parse.quote(doc_id, safe="")),
                       {"fields": {k: _valor(v) for k, v in dict(nueva, mensajes=[mensaje]).items()}}, self.token)
        if st == 200:
            return "nueva"
        if st != 409:
            raise RuntimeError("Firestore %s: %s" % (st, r))
        st, r = _pedir("POST", self.base.replace("/documents", "/documents:commit"), {"writes": [{
            "update": {"name": "%s/solicitudes/%s" % (self.raiz, doc_id), "fields": {"ultimo": _valor(mensaje["fecha"]), "sinLeer": _valor(True)}},
            "updateMask": {"fieldPaths": ["ultimo", "sinLeer"]},
            "updateTransforms": [{"fieldPath": "mensajes", "appendMissingElements": {"values": [_valor(mensaje)]}}],
            "currentDocument": {"exists": True}}]}, self.token)
        if st != 200:
            raise RuntimeError("Firestore %s: %s" % (st, r))
        return "añadida"


def id_documento(prefijo, clave):
    return prefijo + "-" + re.sub(r"[^a-z0-9._@+-]", "_", clave.lower())[:120]
