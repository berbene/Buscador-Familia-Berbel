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

De las personas PÚBLICAS se exporta además la ficha completa: todos los acontecimientos
(con notas, fuentes y padrinos/testigos), notas, fuentes e imágenes enlazadas, y lo mismo de
sus matrimonios. Antes de publicarlos, los textos se limpian: se retiran correos, teléfonos y
líneas de dirección o contacto, y se sustituyen por "[persona protegida]" los nombres completos
de menores y de personas excluidas. De las personas no públicas no se exporta nada de esto.

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

# ---------- Ficha completa (solo personas públicas) ----------
EVENTOS_INDI = {"BIRT": "Nacimiento", "BAPM": "Bautismo", "CHR": "Bautismo", "CONF": "Confirmación",
    "DEAT": "Defunción", "BURI": "Entierro", "CREM": "Cremación", "RESI": "Residencia",
    "CENS": "Padrón o censo", "WILL": "Testamento", "PROB": "Testamentaría", "EMIG": "Emigración",
    "IMMI": "Inmigración", "NATU": "Naturalización", "EDUC": "Estudios", "GRAD": "Graduación",
    "OCCU": "Oficio", "PROP": "Propiedades", "ADOP": "Adopción", "TITL": "Título", "RELI": "Religión",
    "EVEN": "Acontecimiento"}
EVENTOS_FAM = {"MARR": "Matrimonio", "MARC": "Capitulaciones matrimoniales", "MARL": "Licencia matrimonial",
    "MARB": "Amonestaciones", "ENGA": "Esponsales", "DIV": "Divorcio", "SEP": "Separación",
    "ANUL": "Anulación", "EVEN": "Acontecimiento"}
RELACIONES = {"GODP": "padrino/madrina", "WITN": "testigo", "WITNESS": "testigo", "GODFATHER": "padrino",
    "GODMOTHER": "madrina", "OFFICIATOR": "oficiante", "PRIEST": "sacerdote"}
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_URL = re.compile(r"https?://\S+")
# Teléfonos: un número precedido de "teléfono", "móvil"… o con prefijo internacional (+34, 0034…).
RE_TEL = re.compile(r"(?i)(?:(?<=tel[eé]fono)|(?<=tel[eé]fonos)|(?<=tlf)|(?<=tfno)|(?<=m[oó]vil)|(?<=mob)|(?<=whatsapp))[\s.:,-]{0,4}(?:n[uúº°o]?\.?\s*)?(?:de\s+contacto\s*:?\s*)?(\+?[\d][\d .-]{7,}\d)|(?<![\w/.,:=#?&-])(?:\+|00)\d{2,3}[ .-]?\d[\d .-]{7,}\d")
# Líneas de contacto (las que añaden los colaboradores): empiezan por estas palabras.
RE_LINEA_CONTACTO = re.compile(r"(?im)^[ \t]*(direcci[oó]n|n[uú]mero de tel[eé]fono|tel[eé]fono|tfno|m[oó]vil|mob|e-?mail|correo[- ]?electr[oó]nico|nombre de contacto)\b.*$")
RETIRADO = "[dato de contacto retirado]"

def quitar_html(v):
    """Convierte el HTML que traen algunas notas (MyHeritage) en texto, conservando los enlaces."""
    if "<" not in v:
        return v
    import html as _html
    v = re.sub(r'(?is)<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"{m[2]} ({m[1]})" if m[2].strip() and m[2].strip() != m[1] else m[1], v)
    v = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", v)
    v = re.sub(r"(?s)<[^>]{1,300}>", "", v)
    return re.sub(r"\n{3,}", "\n\n", _html.unescape(v)).strip()

def arreglar_texto(v):
    """Corrige textos mal codificados (p. ej. 'VelaciÃ³n' -> 'Velación')."""
    if "Ã" in v or "Â" in v:
        try:
            return v.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return v

class Limpiador:
    """Quita de los textos publicados los datos de contacto y los nombres de personas ocultas."""
    def __init__(self):
        self.contactos = 0; self.nombres = 0; self.patrones = []
    def preparar_ocultos(self, nombres_ocultos):
        for n in sorted(set(nombres_ocultos), key=len, reverse=True):
            partes = [re.escape(x) for x in n.split() if x]
            if len(partes) >= 2:
                self.patrones.append(re.compile(r"(?i)\b" + r"\s+".join(partes) + r"\b"))
    @staticmethod
    def _tel(m):
        num = m[1] or m[0]
        if not 9 <= len(re.sub(r"\D", "", num)) <= 15:
            return m[0]
        return m[0].replace(num, " " + RETIRADO) if m[1] else RETIRADO
    def __call__(self, v):
        if not v:
            return v
        v = quitar_html(arreglar_texto(v))
        v2 = RE_LINEA_CONTACTO.sub(RETIRADO, v)
        v2 = RE_EMAIL.sub(RETIRADO, v2)
        # Teléfonos solo fuera de los enlaces (los enlaces llevan identificadores numéricos legítimos).
        partes, pos = [], 0
        for m in RE_URL.finditer(v2):
            partes.append(RE_TEL.sub(self._tel, v2[pos:m.start()])); partes.append(m[0]); pos = m.end()
        partes.append(RE_TEL.sub(self._tel, v2[pos:]))
        v2 = "".join(partes)
        if v2 != v:
            self.contactos += 1
        v3 = v2
        for pat in self.patrones:
            v3 = pat.sub("[persona protegida]", v3)
        if v3 != v2:
            self.nombres += 1
        # Varias líneas retiradas seguidas se quedan en una; si no queda nada más, el texto se descarta.
        v3 = re.sub(r"\[dato de contacto retirado\](?:[\s|:,-]*\[dato de contacto retirado\])+", RETIRADO, v3)
        if not re.sub(r"\[dato de contacto retirado\]|[\s|:,._-]", "", v3):
            return ""
        return v3.strip()

def hijos_de(L, i):
    """Líneas subordinadas de la línea i (nivel superior)."""
    n0 = L[i][0]; out = []
    for n, t, v in L[i + 1:]:
        if n <= n0:
            break
        out.append((n, t, v))
    return out

def ficha_eventos(L, tabla, limpiar, pid_de):
    """Acontecimientos con fecha, lugar, valor, notas, fuentes y personas asociadas."""
    evs = []
    for i, (n, t, v) in enumerate(L):
        if n != 1 or t not in tabla:
            continue
        sub = hijos_de(L, i)
        tipo = next((arreglar_texto(v2) for n2, t2, v2 in sub if t2 == "TYPE" and n2 == 2), "")
        etiqueta = tipo if (t == "EVEN" and tipo) else tabla[t]
        fecha = next((v2 for n2, t2, v2 in sub if n2 == 2 and t2 == "DATE"), "")
        lugar = next((v2 for n2, t2, v2 in sub if n2 == 2 and t2 == "PLAC"), "")
        notas = [x for x in (limpiar(v2) for n2, t2, v2 in sub if t2 == "NOTE") if x]
        fuentes = [x for x in (limpiar(v2) for n2, t2, v2 in sub if t2 == "SOUR") if x]
        asoc = []
        for j, (n2, t2, v2) in enumerate(sub):
            if t2 == "ASSO" and v2 in pid_de:
                rel = next((v3 for n3, t3, v3 in sub[j + 1:j + 3] if t3 == "RELA"), "")
                asoc.append([RELACIONES.get(rel.upper(), rel.lower() or "asociado/a"), pid_de[v2]])
        e = [etiqueta, fecha_es(fecha), lugar_limpio(limpiar(lugar)), limpiar(v.strip())]
        if notas or fuentes or asoc:
            e += [notas, fuentes, asoc]
        evs.append(e)
    return evs

def ficha_general(L, limpiar):
    """Notas, fuentes e imágenes de nivel 1."""
    notas = [x for x in (limpiar(v) for n, t, v in L if n == 1 and t == "NOTE") if x]
    fuentes = [x for x in (limpiar(v) for n, t, v in L if n == 1 and t == "SOUR") if x]
    imagenes = []
    for i, (n, t, v) in enumerate(L):
        if n == 1 and t == "OBJE":
            for n2, t2, v2 in hijos_de(L, i):
                if t2 == "FILE" and re.match(r"https?://", v2):
                    imagenes.append(re.sub(r"^http://", "https://", v2))
    return notas, fuentes, imagenes

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
                L=L, dado=dado, apell=apell, alias=alias, sexo=sexo, nac=nac, nacl=nacl, bap=bap,
                dfe=dfe, dfl=dfl, dead=dead_e, ocu=ocu, ref=ref,
                famc=next((v for n, t, v in L if n == 1 and t == "FAMC"), None),
                fams=[v for n, t, v in L if n == 1 and t == "FAMS"])
        elif r["tag"] == "FAM":
            L = r["l"]
            _, mf, ml = evento(L, "MARR")
            familias[r["id"]] = dict(
                L=L, h=next((v for n, t, v in L if n == 1 and t == "HUSB"), None),
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
    limpiar = Limpiador()
    limpiar.preparar_ocultos(f'{p["dado"]} {p["apell"]}' for p in personas.values()
                             if p["estado"] in (MENOR, EXCLUIDA) and p["dado"] and p["apell"])
    # Las asociaciones (padrinos, testigos) solo enlazan a personas públicas.
    pid_pub = {x: pid[x] for x, p in personas.items() if p["estado"] == PUBLICA}
    for x, p in personas.items():
        famc = fid.get(p["famc"])
        fams = [fid[f] for f in p["fams"] if f in fid]
        e = p["estado"]; cuenta[e] += 1
        # [nombre, apellidos, sexo, nacimiento, lugar nac., bautismo, defunción, lugar def., oficio, famc, fams, alias, estado]
        if e == PUBLICA:
            P[pid[x]] = [p["dado"], p["apell"], p["sexo"], fecha_es(p["nac"]), lugar_limpio(p["nacl"]),
                         fecha_es(p["bap"]), fecha_es(p["dfe"]) or ("sí" if p["dead"] else ""),
                         lugar_limpio(p["dfl"]), p["ocu"], famc, fams, p["alias"], e]
            L = p["L"]
            notas, fuentes, imgs = ficha_general(L, limpiar)
            testigo = []
            for i, (n, t, v) in enumerate(L):
                if n == 1 and t == "ASSO" and v in familias:
                    rel = next((v2 for n2, t2, v2 in hijos_de(L, i) if t2 == "RELA"), "")
                    testigo.append([RELACIONES.get(rel.upper(), rel.lower() or "asociado/a"), fid[v]])
            det = {"ev": ficha_eventos(L, EVENTOS_INDI, limpiar, pid_pub)}
            if notas: det["no"] = notas
            if fuentes: det["so"] = fuentes
            if imgs: det["im"] = imgs
            if testigo: det["as"] = testigo
            P[pid[x]].append(det)
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
        if boda_publica:
            notas, fuentes, _ = ficha_general(f["L"], limpiar)
            det = {"ev": ficha_eventos(f["L"], EVENTOS_FAM, limpiar, pid_pub)}
            if notas: det["no"] = notas
            if fuentes: det["so"] = fuentes
            F[fid[x]].append(det)

    auditar(P, F)

    datos = {"actualizado": datetime.date.today().strftime("%d/%m/%Y"), "p": P, "f": F}
    out = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    Path(a.salida).write_text(out, encoding="utf-8")
    print(f"{len(P)} personas: {cuenta[PUBLICA]} públicas, {cuenta[PROTEGIDA]} vivas solo con nombre, "
          f"{cuenta[MENOR]} menores ocultos, {cuenta[EXCLUIDA]} excluidas a petición; {len(F)} familias")
    print(f"Limpieza de textos: {limpiar.contactos} textos con datos de contacto retirados, "
          f"{limpiar.nombres} con nombres de personas ocultas sustituidos")
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
    # Ficha completa solo en personas y familias públicas, y sin datos de contacto.
    for i, p in P.items():
        if len(p) > 13 and p[12] != PUBLICA:
            errores.append(f"persona {i}: ficha completa en una persona no pública")
    for i, f in F.items():
        if len(f) > 5 and any(c is not None and P[c][12] != PUBLICA for c in f[:2]):
            errores.append(f"familia {i}: ficha completa con un cónyuge no público")
    texto = json.dumps([P, F], ensure_ascii=False)
    for m in RE_EMAIL.finditer(texto):
        errores.append(f"correo electrónico publicado: …{texto[max(0, m.start()-30):m.start()]}")
        break
    if errores:
        sys.exit("AUDITORÍA DE PRIVACIDAD FALLIDA — no se ha generado nada:\n  " + "\n  ".join(errores[:20]))
    print("Auditoría de privacidad superada: las personas no públicas solo llevan nombre (o nada).")

if __name__ == "__main__":
    main()
