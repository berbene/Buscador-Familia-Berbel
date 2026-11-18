#!/usr/bin/env python3
"""
Convierte un archivo GEDCOM en datos.json para el buscador de antepasados.

Uso:
    python3 convertir_gedcom.py mi_arbol.ged
    python3 convertir_gedcom.py mi_arbol.ged --autonomo     # además crea buscador_autonomo.html

Solo usa la biblioteca estándar de Python 3.8+.

PRIVACIDAD (todo se aplica AQUÍ, antes de publicar: lo que no sale de este
script no existe en la web, aunque alguien descargue y descomprima los datos):

  estado 0 · PÚBLICA   consta su defunción o nació hace más de AÑOS_PRIVADO años.
                       Se publican nombre, fechas, lugares y oficio.
  estado 1 · PROTEGIDA viva o posiblemente viva y mayor de edad. Solo se publica
                       su NOMBRE y sus vínculos familiares. Ni sexo, ni fechas, ni
                       lugares, ni oficio, ni otros nombres, ni datos de boda.
  estado 2 · MENOR     viva o posiblemente viva y, según su año de nacimiento o
                       bautismo, menor de EDAD_ADULTA años. Solo consta que existe
                       (y en qué familia): sin nombre ni ningún otro dato.
                       Quien no tiene fecha se trata como PROTEGIDA (solo nombre).
  estado 3 · EXCLUIDA  persona que ha pedido no aparecer (archivo de exclusiones).
                       Igual que un menor: sin nombre ni ningún otro dato.

Las notas, fuentes, direcciones, fotos y demás etiquetas del GEDCOM NO se exportan nunca.

EXCLUSIONES: crea un archivo excluidos.txt junto a este script (o usa --excluir RUTA)
con una persona por línea: su identificador GEDCOM (p. ej. @I1234@) o su nombre
completo tal como figura en el árbol (p. ej. "María Gómez Salmerón").
Las líneas que empiezan por # son comentarios.
"""
import argparse, base64, datetime, gzip, json, re, sys, unicodedata
from pathlib import Path

AÑOS_PRIVADO = 110          # sin defunción: se considera posiblemente viva si nació hace menos de estos años
EDAD_ADULTA = 18            # por debajo de esta edad (o si no se puede saber), se oculta todo

MESES = {"JAN": "ene", "FEB": "feb", "MAR": "mar", "APR": "abr", "MAY": "may", "JUN": "jun",
         "JUL": "jul", "AUG": "ago", "SEP": "sep", "OCT": "oct", "NOV": "nov", "DEC": "dic"}
PREFIJOS = {"ABT": "h.", "EST": "h.", "CAL": "h.", "BEF": "antes de", "AFT": "después de"}
PUBLICA, PROTEGIDA, MENOR, EXCLUIDA = 0, 1, 2, 3

def leer(ruta):
    """Devuelve registros {tag, id, lineas:[(nivel, tag, valor)]} uniendo CONT/CONC."""
    regs, cur = [], None
    with open(ruta, encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.rstrip("\r\n")
            m = re.match(r"(\d+) (?:(@[^@]+@) )?(\S+)(?: (.*))?$", linea)
            if not m:
                continue
            nivel, xref, tag, val = int(m[1]), m[2], m[3], (m[4] or "")
            if nivel == 0:
                cur = {"id": xref, "tag": tag, "l": []}
                regs.append(cur)
            elif cur is not None:
                if tag in ("CONT", "CONC") and cur["l"]:
                    n, t, v = cur["l"][-1]
                    cur["l"][-1] = (n, t, v + ("\n" if tag == "CONT" else "") + val)
                else:
                    cur["l"].append((nivel, tag, val))
    return regs

def evento(lineas, tag):
    """Fecha y lugar del primer evento `tag` (nivel 1). existe=True si el evento figura."""
    for i, (n, t, v) in enumerate(lineas):
        if n == 1 and t == tag:
            fecha = lugar = ""
            for n2, t2, v2 in lineas[i + 1:]:
                if n2 <= 1:
                    break
                if n2 == 2 and t2 == "DATE" and not fecha:
                    fecha = v2
                if n2 == 2 and t2 == "PLAC" and not lugar:
                    lugar = v2
            return True, fecha, lugar
    return False, "", ""

def año(fecha):
    m = re.findall(r"\b(\d{4})\b", fecha or "")
    return int(m[0]) if m else None

def fecha_es(f):
    if not f:
        return ""
    f = f.strip()
    m = re.match(r"BET (.+) AND (.+)$", f)
    if m:
        return f"entre {fecha_es(m[1])} y {fecha_es(m[2])}"
    m = re.match(r"(ABT|EST|CAL|BEF|AFT) (.+)$", f)
    if m:
        return f"{PREFIJOS[m[1]]} {fecha_es(m[2])}"
    partes = f.split()
    return " ".join(MESES.get(p.upper(), p.lstrip("0") if p.isdigit() and len(p) <= 2 else p) for p in partes)

def lugar_limpio(p):
    # "Huéneja, 304, Granada, Andalucia, España" -> "Huéneja, Granada, Andalucia, España"
    return ", ".join(x.strip() for x in p.split(",") if x.strip() and not x.strip().isdigit())

def nombre(valor):
    m = re.match(r"(.*?)\s*/(.*?)/\s*(.*)$", valor)
    if m:
        return (m[1] + " " + m[3]).strip(), m[2].strip()
    return valor.strip(), ""

def clave(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()

def leer_excluidos(ruta):
    ids, nombres = set(), set()
    if ruta and Path(ruta).exists():
        for l in Path(ruta).read_text(encoding="utf-8-sig").splitlines():
            l = l.split("#", 1)[0].strip()
            if not l:
                continue
            if l.startswith("@") and l.endswith("@"):
                ids.add(l)
            else:
                nombres.add(clave(l))
    return ids, nombres

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gedcom")
    ap.add_argument("--salida", default=str(Path(__file__).with_name("datos.json")))
    ap.add_argument("--excluir", default=str(Path(__file__).with_name("excluidos.txt")),
                    help="archivo con las personas que no deben aparecer (por defecto excluidos.txt)")
    ap.add_argument("--autonomo", action="store_true", help="crea también buscador_autonomo.html con los datos incluidos")
    a = ap.parse_args()

    regs = leer(a.gedcom)
    hoy = datetime.date.today().year
    excl_ids, excl_nombres = leer_excluidos(a.excluir)
    personas, familias = {}, {}

    for r in regs:
        if r["tag"] == "INDI":
            L = r["l"]
            nombres = [v for n, t, v in L if n == 1 and t == "NAME"]
            dado, apell = nombre(nombres[0]) if nombres else ("", "")
            alias = []
            for extra in nombres[1:]:
                d2, a2 = nombre(extra)
                alias.append(d2 if not a2 else f"{d2} {a2}")
            sexo = next((v for n, t, v in L if n == 1 and t == "SEX"), "")
            _, nac, nacl = evento(L, "BIRT")
            bapt_e, bap, bapl = evento(L, "BAPM")
            if not bapt_e:
                bapt_e, bap, bapl = evento(L, "CHR")
            dead_e, dfe, dfl = evento(L, "DEAT")
            if not dead_e:
                dead_e = evento(L, "BURI")[0]          # enterrado = fallecido
            ocu = next((v for n, t, v in L if n == 1 and t == "OCCU"), "")
            ref = año(nac) or año(bap)
            personas[r["id"]] = dict(
                dado=dado, apell=apell, alias=alias, sexo=sexo, nac=nac, nacl=nacl, bap=bap,
                dfe=dfe, dfl=dfl, dead=dead_e, ocu=ocu, ref=ref,
                famc=next((v for n, t, v in L if n == 1 and t == "FAMC"), None),
                fams=[v for n, t, v in L if n == 1 and t == "FAMS"])
        elif r["tag"] == "FAM":
            L = r["l"]
            _, mf, ml = evento(L, "MARR")
            familias[r["id"]] = dict(
                h=next((v for n, t, v in L if n == 1 and t == "HUSB"), None),
                w=next((v for n, t, v in L if n == 1 and t == "WIFE"), None),
                mf=mf, ml=ml, ch=[v for n, t, v in L if n == 1 and t == "CHIL"])

    # ---- Clasificación de privacidad ----
    def es_adulta(p):
        # Solo se oculta como menor a quien tiene un año de nacimiento/bautismo que lo confirma.
        # Sin fecha, se muestra solo con su nombre (decisión del 18/11/2026).
        return p["ref"] is None or hoy - p["ref"] >= EDAD_ADULTA

    for x, p in personas.items():
        if x in excl_ids or clave(f'{p["dado"]} {p["apell"]}') in excl_nombres:
            p["estado"] = EXCLUIDA
        elif p["dead"] or (p["ref"] is not None and hoy - p["ref"] > AÑOS_PRIVADO):
            p["estado"] = PUBLICA
        elif es_adulta(p):
            p["estado"] = PROTEGIDA
        else:
            p["estado"] = MENOR

    # ---- Exportación (solo los campos permitidos por estado) ----
    pid = {x: i for i, x in enumerate(personas)}
    fid = {x: i for i, x in enumerate(familias)}
    P, F = {}, {}
    cuenta = {PUBLICA: 0, PROTEGIDA: 0, MENOR: 0, EXCLUIDA: 0}
    for x, p in personas.items():
        famc = fid.get(p["famc"])
        fams = [fid[f] for f in p["fams"] if f in fid]
        e = p["estado"]; cuenta[e] += 1
        # [nombre, apellidos, sexo, nacimiento, lugar nac., bautismo, defunción, lugar def., oficio, famc, fams, alias, estado]
        if e == PUBLICA:
            P[pid[x]] = [p["dado"], p["apell"], p["sexo"], fecha_es(p["nac"]), lugar_limpio(p["nacl"]),
                         fecha_es(p["bap"]), fecha_es(p["dfe"]) or ("sí" if p["dead"] else ""),
                         lugar_limpio(p["dfl"]), p["ocu"], famc, fams, p["alias"], e]
        elif e == PROTEGIDA:
            P[pid[x]] = [p["dado"], p["apell"], None, "", "", "", "", "", "", famc, fams, [], e]
        else:
            P[pid[x]] = [None, None, None, "", "", "", "", "", "", famc, fams, [], e]
    for x, f in familias.items():
        conyuges = [personas.get(f["h"]), personas.get(f["w"])]
        boda_publica = all(c is None or c["estado"] == PUBLICA for c in conyuges)
        F[fid[x]] = [pid.get(f["h"]), pid.get(f["w"]),
                     fecha_es(f["mf"]) if boda_publica else "", lugar_limpio(f["ml"]) if boda_publica else "",
                     [pid[c] for c in f["ch"] if c in pid]]

    auditar(P, F)

    datos = {"actualizado": datetime.date.today().strftime("%d/%m/%Y"), "p": P, "f": F}
    out = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    Path(a.salida).write_text(out, encoding="utf-8")
    print(f"{len(P)} personas: {cuenta[PUBLICA]} públicas, {cuenta[PROTEGIDA]} vivas solo con nombre, "
          f"{cuenta[MENOR]} menores ocultos, {cuenta[EXCLUIDA]} excluidas a petición; {len(F)} familias")
    if excl_ids or excl_nombres:
        print(f"Lista de exclusión: {len(excl_ids) + len(excl_nombres)} entradas en {a.excluir}")
    print(f"{a.salida}: {len(out) / 1e6:.1f} MB (≈{len(gzip.compress(out.encode(), 9)) / 1e6:.1f} MB comprimido)")

    if a.autonomo:
        plantilla = Path(__file__).with_name("buscador.html").read_text(encoding="utf-8")
        b64 = base64.b64encode(gzip.compress(out.encode(), 9)).decode()
        marca = "<!--DATOS_INCRUSTADOS-->"
        if marca not in plantilla:
            sys.exit("buscador.html no contiene la marca " + marca)
        html = plantilla.replace(marca, f'<script>window.DATOS_GZ_B64="{b64}";</script>')
        destino = Path(a.salida).with_name("buscador_autonomo.html")
        destino.write_text(html, encoding="utf-8")
        print(f"{destino}: {len(html) / 1e6:.1f} MB")

def auditar(P, F):
    """Comprobación de seguridad: detiene la exportación si algún dato no permitido se cuela."""
    errores = []
    for i, p in P.items():
        e = p[12]
        if e != PUBLICA and (p[2] is not None or any(p[3:9]) or p[11]):
            errores.append(f"persona {i}: datos personales en una persona no pública")
        if e in (MENOR, EXCLUIDA) and (p[0] is not None or p[1] is not None):
            errores.append(f"persona {i}: nombre en un menor o excluido")
    for i, f in F.items():
        if (f[2] or f[3]) and any(c is not None and P[c][12] != PUBLICA for c in f[:2]):
            errores.append(f"familia {i}: datos de boda de una persona no pública")
    if errores:
        sys.exit("AUDITORÍA DE PRIVACIDAD FALLIDA — no se ha generado nada:\n  " + "\n  ".join(errores[:20]))
    print("Auditoría de privacidad superada: las personas no públicas solo llevan nombre (o nada).")

if __name__ == "__main__":
    main()
