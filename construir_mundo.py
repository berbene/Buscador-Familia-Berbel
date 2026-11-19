"""Genera apellido-mundo.html: mapa mundial del apellido Berbel.
España usa los datos del INE (primer apellido, residencia); el resto de
países, la estimación de Forebears (forebears_berbel.json).
Contornos: world-atlas countries-50m.json (Natural Earth, dominio público).
Uso: python3 -I construir_mundo.py <countries-50m.json> <dir_csv_INE>"""
import json, math, os, subprocess, sys, tempfile

D = os.path.dirname(os.path.abspath(__file__))
K = 150
A1, A2, A3, A4, M = 1.340264, -0.081106, 0.000893, 0.003796, math.sqrt(3) / 2

# Nombre de Forebears -> (código ISO numérico, nombre en español)
PAISES = {
    "Spain": ("724", "España"), "Brazil": ("076", "Brasil"), "Argentina": ("032", "Argentina"),
    "France": ("250", "Francia"), "Colombia": ("170", "Colombia"), "United States": ("840", "Estados Unidos"),
    "Belgium": ("056", "Bélgica"), "Venezuela": ("862", "Venezuela"), "Uruguay": ("858", "Uruguay"),
    "Switzerland": ("756", "Suiza"), "England": ("826", "Reino Unido (Inglaterra)"), "Mexico": ("484", "México"),
    "Paraguay": ("600", "Paraguay"), "Chile": ("152", "Chile"), "Italy": ("380", "Italia"),
    "Angola": ("024", "Angola"), "Puerto Rico": ("630", "Puerto Rico"), "Romania": ("642", "Rumanía"),
    "Singapore": ("702", "Singapur"), "Belarus": ("112", "Bielorrusia"), "Ecuador": ("218", "Ecuador"),
    "Denmark": ("208", "Dinamarca"), "Czechia": ("203", "Chequia"),
}


def proy(lo, la):
    l, p = math.radians(lo), math.radians(la)
    t = math.asin(M * math.sin(p))
    t2, t6 = t * t, t ** 6
    x = 2 * math.sqrt(3) * l * math.cos(t) / (3 * (9 * A4 * t6 * t2 + 7 * A3 * t6 + 3 * A2 * t2 + A1))
    y = t * (A4 * t6 * t2 + A3 * t6 + A2 * t2 + A1)
    return x * K, -y * K


def geometria(src):
    t = json.load(open(src, encoding="utf-8"))
    sx, sy = t["transform"]["scale"]
    tx, ty = t["transform"]["translate"]
    arcos = []
    for a in t["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx; y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcos.append(pts)

    def anillo(idx):
        pts = []
        for i in idx:
            a = arcos[i] if i >= 0 else arcos[~i][::-1]
            pts.extend(a if not pts else a[1:])
        return pts

    paises = {}
    for g in t["objects"]["countries"]["geometries"]:
        if g.get("type") is None or g["properties"]["name"] == "Antarctica":
            continue
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        trozos, mejor = [], (0, 0, 0)
        for poly in polys:
            for k, r in enumerate(poly):
                q, ult = [], None
                for lo, la in anillo(r):
                    x, y = proy(lo, la)
                    if ult and abs(x - ult[0]) + abs(y - ult[1]) < 0.7:
                        continue
                    q.append((x, y)); ult = (x, y)
                if len(q) < 3:
                    continue
                if max(x for x, _ in q) - min(x for x, _ in q) > 300:
                    continue  # anillo partido por el antimeridiano (Kiribati, Fiyi…): se dibujaría como una raya
                trozos.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in q) + "Z")
                if k == 0:
                    area = abs(sum(q[i][0] * q[i - 1][1] - q[i - 1][0] * q[i][1] for i in range(len(q)))) / 2
                    if area > mejor[0]:
                        cx = sum(x for x, _ in q) / len(q); cy = sum(y for _, y in q) / len(q)
                        mejor = (area, cx, cy)
        if trozos:
            paises[g.get("id") or g["properties"]["name"]] = {
                "d": "".join(trozos), "c": [round(mejor[1], 1), round(mejor[2], 1)], "a": round(mejor[0], 1),
                "n": g["properties"]["name"]}
    return paises


def main(world, dir_csv):
    geo = geometria(world)
    tmp = os.path.join(tempfile.mkdtemp(), "ine.json")
    subprocess.run([sys.executable, "-I", os.path.join(D, "parse_ine.py"), dir_csv, tmp], check=True)
    ine = json.load(open(tmp, encoding="utf-8"))
    tot = ine["totales"]["Berbel"]["residencia"]  # [1º, ‰ 1º, 2º, ‰, ambos, ‰]
    fb = json.load(open(os.path.join(D, "forebears_berbel.json"), encoding="utf-8"))
    datos = []
    for nombre, n, uno_de in fb["paises"]:
        cod, es = PAISES[nombre]
        if nombre == "Spain":
            # Población de España implícita en el ‰ del INE
            pob = tot[0] / tot[1] * 1000 if tot[1] else None
            datos.append({"id": cod, "n": es, "t": int(tot[0]), "pm": round(tot[0] / pob * 1e6, 2) if pob else None,
                          "f": "INE", "fb": n})
        else:
            datos.append({"id": cod, "n": es, "t": n, "pm": round(1e6 / uno_de, 3), "f": "Forebears",
                          "parcial": nombre == "England"})
    html = open(os.path.join(D, "mundo_plantilla.html"), encoding="utf-8").read()
    html = html.replace("/*DATOS*/", json.dumps(datos, ensure_ascii=False).replace("</", "<\\/"))
    html = html.replace("/*GEO*/", json.dumps(geo, ensure_ascii=False, separators=(",", ":")))
    open(os.path.join(D, "apellido-mundo.html"), "w", encoding="utf-8").write(html)
    print("apellido-mundo.html", len(html), "España:", datos[0])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
