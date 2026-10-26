#!/usr/bin/env python3
"""Genera el catálogo de productos de shop4fit.online con un código de barras para cada uno.

Uso:  python3 catalogo/generar.py exportacion-woocommerce.csv

Entrada: la exportación de WooCommerce (Productos → Exportar, todas las columnas).
Salida:
  catalogo/productos-shop4fit.csv   para abrir en Excel: código de barras, referencia, nombre, categoría y foto
  catalogo.json                     el mismo catálogo para la app (Stock → Catálogo web)

Código de barras: el GTIN/EAN que tenga el producto en la web; si no tiene, uno interno EAN-13
«21» + ID de WooCommerce (10 cifras) + dígito de control. Es fijo: el mismo producto siempre recibe
el mismo código, y no choca con los internos de la app, que empiezan por «20».
"""
import csv, json, pathlib, re, sys, unicodedata

RAIZ = pathlib.Path(__file__).resolve().parent.parent
NOMBRE_CAT = {"musculacion": "Máquinas de musculación", "cardio": "Máquinas cardiovasculares", "funcional": "Material funcional de salas colectivas",
              "peso-libre": "Peso libre", "suelos": "Suelos técnicos", "estructuras": "Estructuras"}

# Categorías de la web → categoría y tipo de la app
MAPA = [
    (r"cardio", "cardio", ""),
    (r"musculaci", "musculacion", ""),
    (r"peso libre|mancuern|discos|barras", "peso-libre", ""),
    (r"rack|multipower|banco|estructur|jaula", "estructuras", ""),
    (r"carril", "suelos", "Carriles de césped"),
    (r"c[eé]sped", "suelos", "Césped"),
    (r"loseta", "suelos", "Loseta"),
    (r"tatami", "suelos", "Tatami"),
    (r"suelo", "suelos", ""),
    (r"funcional|pilates|yoga|colectiv|accesorio|sacos|power bag", "funcional", ""),
]


def ean_check(d12):
    return (10 - sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12)) % 10) % 10


def gtin_valido(g):
    g = re.sub(r"\D", "", g or "")
    if len(g) == 12:
        g = "0" + g
    return g if len(g) == 13 and ean_check(g[:12]) == int(g[12]) else ""


def codigo_interno(wid):
    base = "21" + str(int(wid)).zfill(10)
    return base + str(ean_check(base))


def norm(t):
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower().strip()


def col(cab, *nombres):
    """Busca una columna por su nombre en español o en inglés."""
    n = {norm(c): c for c in cab}
    for x in nombres:
        if norm(x) in n:
            return n[norm(x)]
    for x in nombres:  # coincidencia parcial (p. ej. «GTIN, UPC, EAN o ISBN»)
        for k, c in n.items():
            if k.startswith(norm(x)):
                return c
    return None


def categoria_app(cats):
    texto = norm(" | ".join(cats))
    for patron, cat, sub in MAPA:
        if re.search(patron, texto):
            return cat, sub
    return "funcional", ""


def leer(ruta):
    datos = pathlib.Path(ruta).read_bytes().decode("utf-8-sig")
    filas = list(csv.DictReader(datos.splitlines(), delimiter=";" if datos.split("\n", 1)[0].count(";") > datos.split("\n", 1)[0].count(",") else ","))
    cab = filas[0].keys() if filas else []
    C = {k: col(cab, *v) for k, v in {
        "id": ["ID"], "tipo": ["Tipo", "Type"], "sku": ["SKU"], "gtin": ["GTIN", "EAN"], "nombre": ["Nombre", "Name"],
        "publicado": ["Publicado", "Published"], "cats": ["Categorías", "Categories"], "imgs": ["Imágenes", "Images"],
        "padre": ["Superior", "Parent"]}.items()}
    if not C["id"] or not C["nombre"]:
        sys.exit("No parece una exportación de productos de WooCommerce (faltan las columnas ID y Nombre).")
    g = lambda f, k: (f.get(C[k]) or "").strip() if C[k] else ""
    porid, porsku = {}, {}
    for f in filas:
        porid[g(f, "id")] = f
        if g(f, "sku"):
            porsku[g(f, "sku")] = f
    con_hijos = {re.sub(r"^id:", "", g(f, "padre")) for f in filas if g(f, "padre")}
    con_hijos |= {g(porsku[g(f, "padre")], "id") for f in filas if g(f, "padre") in porsku}
    salida = []
    for f in filas:
        tipo, wid = norm(g(f, "tipo")), g(f, "id")
        if g(f, "publicado") not in ("1", ""):
            continue  # borradores y privados fuera
        if "variable" in tipo and wid in con_hijos:
            continue  # el producto «padre» no es un artículo físico: entran sus variaciones
        if "grouped" in tipo or "agrupado" in tipo or "external" in tipo or "externo" in tipo:
            continue
        padre_ref = g(f, "padre")
        padre = porid.get(re.sub(r"^id:", "", padre_ref)) or porsku.get(padre_ref) if padre_ref else None
        rutas = [c.strip() for c in (g(f, "cats") or (g(padre, "cats") if padre else "")).split(",") if c.strip()]  # «Suelos > Losetas, Ofertas»
        cats = [c.split(">")[-1].strip() for c in rutas]
        img = (g(f, "imgs") or (g(padre, "imgs") if padre else "")).split(",")[0].strip()
        nombre = g(f, "nombre") or (g(padre, "nombre") if padre else "")
        cat, sub = categoria_app(rutas + ([g(padre, "nombre")] if padre else []) + [nombre])
        gt = gtin_valido(g(f, "gtin"))
        salida.append({"i": int(wid), "c": gt or codigo_interno(wid), "r": g(f, "sku"), "n": nombre, "w": " / ".join(dict.fromkeys(cats)),
                       "cat": cat, "sub": sub, "f": img, "gtin": bool(gt)})
    salida.sort(key=lambda p: (p["cat"], p["n"].lower()))
    return salida


def escribir(prods):
    codigos = {}
    for p in prods:
        if p["c"] in codigos:
            print("Aviso: código repetido %s en %s y %s; se usa el interno" % (p["c"], codigos[p["c"]], p["i"]))
            p["c"] = codigo_interno(p["i"])
        codigos[p["c"]] = p["i"]
    with open(RAIZ / "catalogo" / "productos-shop4fit.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Código de barras", "Referencia web", "Nombre", "Categoría web", "Categoría app", "Foto", "ID web", "Origen del código"])
        for p in prods:
            w.writerow([p["c"], p["r"], p["n"], p["w"], NOMBRE_CAT[p["cat"]] + (" · " + p["sub"] if p["sub"] else ""), p["f"], p["i"], "EAN de la web" if p["gtin"] else "Interno"])
    (RAIZ / "catalogo.json").write_text(json.dumps({"generado": __import__("datetime").date.today().isoformat(),
        "productos": [{k: v for k, v in p.items() if k != "gtin" and v != ""} for p in prods]}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("%d productos → catalogo/productos-shop4fit.csv y catalogo.json" % len(prods))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    escribir(leer(sys.argv[1]))
