#!/usr/bin/env python3
"""Lleva los presupuestos aceptados en Teamleader Focus a Pedidos › Nuevo.

Busca los deals ganados desde la última vez y, de cada uno, sus presupuestos aceptados. Cada presupuesto se crea
una sola vez como pedido de cliente (documento «tl-<id del presupuesto>») con sus líneas: referencia (código del
producto en Teamleader), nombre, cantidad, precio y proveedor principal. La app cruza la referencia con Stock y lo
reparte sola entre Stock y Proveedores.
Se ejecuta cada 10 minutos desde GitHub Actions (.github/workflows/importar-teamleader.yml) con secretos:
  IMPORTADOR_CLAVE                       contraseña del usuario importador@rutech-61f25.firebaseapp.com
  TL_CLIENTE_ID, TL_CLIENTE_SECRETO      de la integración creada en el Marketplace de Teamleader
La primera vez se lanza a mano con el código que da la página teamleader.html (entrada «codigo»); después el
token de Teamleader se renueva solo y se guarda en Firestore (importador/teamleader), donde solo llega el importador.
"""
import datetime, json, os, sys, urllib.error, urllib.request
from firestore import Firestore

API = "https://api.focus.teamleader.eu/"
TOKEN_URL = "https://focus.teamleader.eu/oauth2/access_token"
REDIRECT = "https://savaservicios2026.github.io/shop4fit-stocks/teamleader.html"
DIAS_PRIMERA_VEZ = 7


def _post(url, cuerpo, token=None):
    r = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                               headers={"Content-Type": "application/json", "Accept": "application/json"})
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError("Teamleader %s %s: %s" % (url.rsplit("/", 1)[-1], e.code, e.read()[:300].decode(errors="replace")))


def iso(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class Teamleader:
    def __init__(self, fs):
        self.fs = fs
        self.estado = fs.leer("importador/teamleader") or {}
        base = {"client_id": os.environ["TL_CLIENTE_ID"], "client_secret": os.environ["TL_CLIENTE_SECRETO"]}
        codigo = os.environ.get("TL_CODIGO", "").strip()
        if codigo:
            r = _post(TOKEN_URL, dict(base, grant_type="authorization_code", code=codigo, redirect_uri=REDIRECT))
        elif self.estado.get("refresh"):
            r = _post(TOKEN_URL, dict(base, grant_type="refresh_token", refresh_token=self.estado["refresh"]))
        else:
            print("Teamleader sin autorizar: lanza la tarea a mano con el código de teamleader.html.")
            sys.exit(0)
        self.token = r["access_token"]
        # El refresh token solo sirve una vez: se guarda el nuevo antes de hacer nada más
        self.estado["refresh"] = r["refresh_token"]
        self.fs.escribir("importador/teamleader", self.estado)
        self.cache = {}

    def api(self, metodo, cuerpo):
        return _post(API + metodo, cuerpo, self.token)

    def una_vez(self, clave, f):
        if clave not in self.cache:
            try:
                self.cache[clave] = f()
            except RuntimeError as e:
                print("Aviso:", e)
                self.cache[clave] = None
        return self.cache[clave]

    def nombre_cliente(self, cliente):
        if not cliente:
            return ""
        def f():
            if cliente.get("type") == "company":
                return self.api("companies.info", {"id": cliente["id"]})["data"].get("name", "")
            d = self.api("contacts.info", {"id": cliente["id"]})["data"]
            return " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x)
        return self.una_vez(("cliente", cliente.get("id")), f) or ""

    def producto(self, pid):
        def f():
            d = self.api("products.info", {"id": pid, "includes": "suppliers"})["data"]
            sups = d.get("suppliers") or []
            sup = next((s for s in sups if s.get("classification") == "primary"), sups[0] if sups else None)
            return {"ref": d.get("code") or "", "nombre": d.get("name") or "",
                    "proveedor": self.nombre_cliente(sup.get("supplier")) if sup else ""}
        return self.una_vez(("producto", pid), f) or {"ref": "", "nombre": "", "proveedor": ""}

    def deals_ganados(self, desde):
        n = 1
        while True:
            r = self.api("deals.list", {"filter": {"status": ["won"], "updated_since": desde}, "page": {"size": 50, "number": n}})
            yield from r.get("data", [])
            if len(r.get("data", [])) < 50:
                return
            n += 1


def pedido(tl, deal, q):
    lineas = []
    for g in q.get("grouped_lines") or []:
        for li in g.get("line_items") or []:
            prod = li.get("product")
            if not prod:  # líneas de texto (transporte, montaje…): no son material
                continue
            p = tl.producto(prod["id"])
            precio = (li.get("unit_price") or {}).get("amount")
            lineas.append({"productoId": "", "ref": p["ref"], "nombre": p["nombre"] or (li.get("description") or "").strip(),
                           "cantidad": float(li.get("quantity") or 0), "precio": float(precio) if precio is not None else "",
                           "proveedor": p["proveedor"], "tlProducto": prod["id"]})
    cliente = tl.nombre_cliente(((deal.get("lead") or {}).get("customer")))
    return {"cliente": cliente or deal.get("title") or "Cliente de Teamleader", "presupuesto": deal.get("reference") or q.get("name") or "",
            "albaran": "", "numero": "", "fecha": datetime.date.today().isoformat(), "nota": deal.get("title") or "", "cancelado": False,
            "fase": "nuevo", "origen": "teamleader", "teamleaderId": q["id"], "tlDeal": deal["id"], "lineas": lineas}


def main():
    if not all(os.environ.get(k) for k in ("IMPORTADOR_CLAVE", "TL_CLIENTE_ID", "TL_CLIENTE_SECRETO")):
        print("Importador de Teamleader sin configurar (faltan secretos). No se hace nada.")
        return
    fs = Firestore(os.environ["IMPORTADOR_CLAVE"])
    tl = Teamleader(fs)
    ahora = datetime.datetime.now(datetime.timezone.utc)
    desde = tl.estado.get("desde") or iso(ahora - datetime.timedelta(days=DIAS_PRIMERA_VEZ))
    nuevos = 0
    for d in tl.deals_ganados(desde):
        deal = tl.api("deals.info", {"id": d["id"]})["data"]
        for ref in deal.get("quotations") or []:
            q = tl.api("quotations.info", {"id": ref["id"]})["data"]
            if q.get("status") != "accepted":
                continue
            datos = pedido(tl, deal, q)
            if not datos["lineas"]:
                continue
            if fs.crear("pedidosCliente", "tl-" + q["id"], datos):
                nuevos += 1
                print("Nuevo: %s · %s (%d líneas)" % (datos["cliente"], datos["presupuesto"], len(datos["lineas"])))
    # Una hora de margen: un deal que se mueva justo durante esta ejecución se vuelve a mirar (no se duplica)
    tl.estado["desde"] = iso(ahora - datetime.timedelta(hours=1))
    fs.escribir("importador/teamleader", tl.estado)
    print("Presupuestos aceptados nuevos: %d" % nuevos)


if __name__ == "__main__":
    main()
