"""Convierte el TopoJSON de es-atlas (IGN, licencia MIT; es/municipalities.json)
en trazados SVG ya proyectados para mapa_plantilla.html: provincias de España,
comunidades autónomas y los municipios de Andalucía.
Uso: python3 -I construir_geo.py <municipalities.json> <salida geo.json>"""
import json, math, sys

K, CO = 100, math.cos(math.radians(40))
CANARIAS = {"35", "38", "05"}  # provincias y comunidad que van al recuadro


def mover_canarias(lo, la):
    # Recuadro abajo a la izquierda, a escala 0,6
    return -9.75 + (lo + 18.3) * 0.6, 35.15 + (la - 27.55) * 0.6


def px(lo, la):
    return (lo + 10) * K * CO, (44 - la) * K


def main(src, dst):
    t = json.load(open(src, encoding="utf-8"))
    sx, sy = t["transform"]["scale"]
    tx, ty = t["transform"]["translate"]
    arcos = []
    for a in t["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in a:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcos.append(pts)

    def anillo(idx):
        pts = []
        for i in idx:
            a = arcos[i] if i >= 0 else arcos[~i][::-1]
            pts.extend(a if not pts else a[1:])
        return pts

    def trazado(geom, canarias, umbral=0.8, centro=False):
        polys = [geom["arcs"]] if geom["type"] == "Polygon" else geom["arcs"]
        out = []
        for poly in polys:
            for r in poly:
                q, ult = [], None
                for lo, la in anillo(r):
                    if canarias:
                        lo, la = mover_canarias(lo, la)
                    x, y = px(lo, la)
                    if ult and abs(x - ult[0]) + abs(y - ult[1]) < umbral:
                        continue
                    q.append((x, y))
                    ult = (x, y)
                if len(q) >= 3:
                    out.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in q) + "Z")
                    if centro:
                        area = abs(sum(q[i][0] * q[i - 1][1] - q[i - 1][0] * q[i][1] for i in range(len(q))))
                        if area > centro_mayor[0]:
                            centro_mayor[:] = [area, sum(x for x, _ in q) / len(q), sum(y for _, y in q) / len(q)]
        return "".join(out)
    centro_mayor = [0, 0, 0]

    geo = {"prov": {}, "ccaa": {}}
    for g in t["objects"]["provinces"]["geometries"]:
        if g["id"] == "54":
            continue  # Gibraltar
        geo["prov"][g["id"]] = trazado(g, g["id"] in CANARIAS)
    for g in t["objects"]["autonomous_regions"]["geometries"]:
        if g["properties"]["name"] != "Andalucía":
            continue
        geo["ccaa"][g["properties"]["name"]] = trazado(g, g["id"] in CANARIAS)
    ANDALUCIA = {"04", "11", "14", "18", "21", "23", "29", "41"}
    geo["mun"], geo["munNom"], geo["munCen"] = {}, {}, {}
    for g in t["objects"]["municipalities"]["geometries"]:
        if g["id"][:2] in ANDALUCIA:
            centro_mayor[:] = [0, 0, 0]
            geo["mun"][g["id"]] = trazado(g, False, umbral=0.5, centro=True)
            geo["munNom"][g["id"]] = g["properties"]["name"]
            geo["munCen"][g["id"]] = [round(centro_mayor[1], 1), round(centro_mayor[2], 1)]
    json.dump(geo, open(dst, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
