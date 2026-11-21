#!/usr/bin/env python3
"""
Franja «Hoy recordamos a…» para la portada de familiaberbel.org.

Lee los datos publicados del buscador (index.html) y busca a las personas
PÚBLICAS (fallecidas o nacidas hace más de un siglo) con el apellido Berbel o
una de sus variantes que nacieron el día y mes indicados. Si nadie nació ese
día, usa la fecha de bautismo. Nunca usa personas vivas ni menores: sus fechas
no están en los datos publicados.

Uso:
    python3 efemerides.py                 # fecha de hoy (hora de Madrid)
    python3 efemerides.py --fecha 21-11   # día-mes concreto
    python3 efemerides.py --texto         # además, lista legible por stderr

Escribe en stdout el bloque de Gutenberg (un grupo con la clase
«hoy-recordamos») listo para sustituir la franja de la portada.
"""
import argparse, base64, datetime, gzip, html, json, re, sys, unicodedata
from pathlib import Path

BUSCADOR = "https://berbene.github.io/Buscador-Familia-Berbel/"
VARIANTES = {"berbel", "bervel", "belber", "belbel", "velbel", "velber", "verbal",
             "belver", "bellver", "velver", "berben", "berbell"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MAXIMO = 15
PUBLICA = 0


def norm(t):
    t = unicodedata.normalize("NFD", t or "").lower()
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def cargar(ruta):
    s = Path(ruta).read_text(encoding="utf-8")
    b = re.search(r'window\.DATOS_GZ_B64="([^"]+)"', s).group(1)
    return json.loads(gzip.decompress(base64.b64decode(b)))


def es_berbel(apellidos):
    return any(w in VARIANTES for w in re.findall(r"[a-zñ]+", norm(apellidos)))


def fecha_exacta(f, dia, mes):
    """Solo fechas completas «D mes AAAA» (sin «h.», «antes de», «entre»…)."""
    m = re.fullmatch(r"(\d{1,2}) ([a-z]{3}) (\d{3,4})", (f or "").strip())
    if m and int(m[1]) == dia and m[2] == MESES[mes - 1]:
        return int(m[3])
    return None


def pueblo(lugar):
    return (lugar or "").split(",")[0].strip()


def buscar(D, dia, mes):
    nac, bau = [], []
    for pid, p in D["p"].items():
        if not p or p[0] is None or (len(p) > 12 and p[12] != PUBLICA):
            continue
        if not es_berbel(p[1]):
            continue
        nombre = f"{p[0]} {p[1]}".strip()
        a = fecha_exacta(p[3], dia, mes)
        if a:
            nac.append((a, nombre, pueblo(p[4]), pid))
            continue
        a = fecha_exacta(p[5], dia, mes)
        if a:
            bau.append((a, nombre, pueblo(p[4]), pid))
    if nac:
        return "nac", sorted(nac)[:MAXIMO]
    return "bau", sorted(bau)[:MAXIMO]


def bloque(tipo, personas):
    e = html.escape
    if personas:
        cab = "🕯️ <strong>Hoy recordamos a</strong>" + ("" if tipo == "nac" else " (bautizados un día como hoy)") + ": "
        items = " · ".join(
            f'<a href="{BUSCADOR}#p{pid}">{e(nom)}</a> ({e(lug) + ", " if lug else ""}{a})'
            for a, nom, lug, pid in personas)
        texto = cab + items + f' · <a href="{BUSCADOR}">Busca a tus antepasados →</a>'
    else:
        texto = (f'🕯️ <strong>Hoy recordamos</strong> a todos los Berbel que nos precedieron · '
                 f'<a href="{BUSCADOR}">Busca a tus antepasados →</a>')
    return (
        '<!-- wp:group {"align":"full","className":"hoy-recordamos","style":{"color":{"background":"#0a4744","text":"#ffffff"},'
        '"spacing":{"padding":{"top":"8px","bottom":"8px","left":"12px","right":"12px"}},"elements":{"link":{"color":{"text":"#ffff00"}}}},'
        '"layout":{"type":"constrained","contentSize":"100%"}} -->\n'
        '<div class="wp-block-group alignfull hoy-recordamos has-text-color has-background has-link-color" '
        'style="color:#ffffff;background-color:#0a4744;padding-top:8px;padding-right:12px;padding-bottom:8px;padding-left:12px">'
        '<!-- wp:paragraph {"className":"cinta","style":{"typography":{"fontSize":"15px","lineHeight":"1.4"},"spacing":{"margin":{"top":"0","bottom":"0"}}}} -->\n'
        f'<p class="cinta" style="margin-top:0;margin-bottom:0;font-size:15px;line-height:1.4">{texto}</p>\n'
        '<!-- /wp:paragraph --></div>\n<!-- /wp:group -->'
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default=str(Path(__file__).with_name("index.html")))
    ap.add_argument("--fecha", help="DD-MM; por defecto, hoy en Madrid")
    ap.add_argument("--texto", action="store_true")
    a = ap.parse_args()
    if a.fecha:
        dia, mes = map(int, a.fecha.split("-"))
    else:
        try:
            from zoneinfo import ZoneInfo
            hoy = datetime.datetime.now(ZoneInfo("Europe/Madrid")).date()
        except Exception:
            hoy = datetime.date.today()
        dia, mes = hoy.day, hoy.month
    tipo, personas = buscar(cargar(a.datos), dia, mes)
    if a.texto:
        print(f"{dia:02d}-{mes:02d} · {tipo} · {len(personas)} personas", file=sys.stderr)
        for p in personas:
            print("  ", p, file=sys.stderr)
    print(bloque(tipo, personas))


if __name__ == "__main__":
    main()
