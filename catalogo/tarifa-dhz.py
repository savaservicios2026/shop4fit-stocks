#!/usr/bin/env python3
"""Añade al catálogo de la app las máquinas de la tarifa DHZ (proveedor Fitness Deluxe).

Uso:  pdftotext -layout "TARIFA DHZ 2026.pdf" dhz.txt
      python3 catalogo/tarifa-dhz.py dhz.txt

Salida: catalogo-proveedores.json, que la app junta con catalogo.json (Catálogo web y Recuento).
Así las máquinas se pueden buscar, contar e imprimir etiqueta, y pasan a Stock al darlas de alta.

Código de barras: interno EAN-13 «22» + número (10 cifras) + dígito de control. Es fijo: al volver a
generar, cada referencia conserva su código y las nuevas reciben el siguiente libre. No choca con los
internos de la app («20») ni con los de la web («21»).
"""
import json, pathlib, re, sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "catalogo-proveedores.json"
TARIFA, PROVEEDOR = "Tarifa DHZ 2026", "Fitness Deluxe"
FILA = re.compile(r"^(.*?)\s+(D-[A-Z0-9][A-Z0-9\-./]*)\s+([\d.]+,\d\d)\s*€\s*(.*)$")


def ean_check(d12):
    return (10 - sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12)) % 10) % 10


def categoria(seccion, nombre):
    s, n = seccion.upper(), nombre.upper()
    if re.search(r"BICI|REMO|CINTA|ELIPTICA|ESCALADORA", s):
        return "cardio", ""
    if "ACCESORIOS" in s:
        return "funcional", ""
    if re.search(r"BANCO|SOPORTES", s) or re.search(r"\bBENCH|\bBECH|\bBECNH|\bBANCO|\bRACK", n):
        return "estructuras", ""
    if re.search(r"PLATE LOADED|POWER", s):
        return "musculacion", "Palanca"
    return "musculacion", "Placas"


def leer(ruta):
    seccion, salida = "", []
    for bloque in re.split(r"\n\s*\n", pathlib.Path(ruta).read_text(encoding="utf-8")):
        lineas = [l for l in bloque.split("\n") if l.strip() and not re.match(r"^\s*Página \d+\s*$", l)]
        filas = [(i, FILA.match(" " + l.strip())) for i, l in enumerate(lineas)]
        filas = [(i, m) for i, m in filas if m]
        if not filas:  # título de sección («CINTA DHZ», «DHZ - SERIE EVOST II - BANCO»…)
            for l in lineas:
                s = re.sub(r"\s*Página \d+", "", l).strip()
                if s and s not in ("NUEVO", "2026"):
                    seccion = s
            continue
        i, m = filas[0]
        partes = []
        for j, l in enumerate(lineas):  # el nombre puede seguir en la línea de abajo
            s = (m.group(1).strip() + " " + m.group(4)) if j == i else l
            s = re.sub(r"\bNUEVO\b|^\s*2026\s*$|Página \d+", "", s).strip()
            if s:
                partes.append(s)
        nombre = re.sub(r"^DHZ\s*-\s*", "DHZ - ", re.sub(r"\s+", " ", " ".join(partes)))
        cat, sub = categoria(seccion, nombre)
        salida.append({"r": m.group(2), "n": nombre, "cat": cat, "sub": sub,
                       "t": float(m.group(3).replace(".", "").replace(",", "."))})
    return salida


def escribir(prods):
    previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() else {"productos": []}
    codigos = {p["r"]: p["c"] for p in previo["productos"] if p.get("r")}
    sig = max([int(c[2:12]) for c in codigos.values()] + [0]) + 1
    otros = [p for p in previo["productos"] if p.get("tarifa") != TARIFA]
    for p in prods:
        if p["r"] not in codigos:
            base = "22" + str(sig).zfill(10)
            codigos[p["r"]], sig = base + str(ean_check(base)), sig + 1
        p.update(c=codigos[p["r"]], w=TARIFA + " · " + PROVEEDOR, tarifa=TARIFA, prov=PROVEEDOR)
    todos = otros + prods
    SALIDA.write_text(json.dumps({"generado": __import__("datetime").date.today().isoformat(), "productos":
        [{k: v for k, v in p.items() if v != ""} for p in todos]}, ensure_ascii=False, indent=0), encoding="utf-8")
    print("%d productos de %s → %s" % (len(prods), TARIFA, SALIDA.name))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    escribir(leer(sys.argv[1]))
