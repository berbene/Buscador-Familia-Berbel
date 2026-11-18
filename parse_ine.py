"""Convierte los CSV del INE (frecuencia de apellidos) en un JSON compacto
para el mapa del apellido. Uso: python3 -I parse_ine.py <dir_csv> <salida.json>"""
import csv, json, sys, os

GRAFIAS = ["Berbel", "Belber", "Belver", "Bellver", "Bervel"]

# Los municipios vienen ordenados por código INE de provincia, sin columna de
# provincia. Marcamos el primer municipio de cada bloque provincial.
CORTES = {
    "Berbel": [
        ("Albacete", "Albacete"), ("Alacant/Alicante", "Alicante/Alacant"),
        ("Albox", "Almería"), ("Marratxí", "Balears, Illes"),
        ("Badalona", "Barcelona"), ("Puerto de Santa María, El", "Cádiz"),
        ("Almassora", "Castellón/Castelló"), ("Puertollano", "Ciudad Real"),
        ("Córdoba", "Córdoba"), ("Coruña, A", "Coruña, A"),
        ("Motilla del Palancar", "Cuenca"), ("Figueres", "Girona"),
        ("Albolote", "Granada"), ("Huelva", "Huelva"), ("Huesca", "Huesca"),
        ("Alcaudete", "Jaén"), ("Ponferrada", "León"), ("Lleida", "Lleida"),
        ("Logroño", "Rioja, La"), ("Alcalá de Henares", "Madrid"),
        ("Benalmádena", "Málaga"), ("Águilas", "Murcia"), ("Gijón", "Asturias"),
        ("Santa Lucía de Tirajana", "Palmas, Las"),
        ("Vilagarcía de Arousa", "Pontevedra"), ("Segovia", "Segovia"),
        ("Alcalá de Guadaíra", "Sevilla"), ("Reus", "Tarragona"),
        ("Algemesí", "Valencia/València"), ("Viana de Cega", "Valladolid"),
        ("Ortuella", "Bizkaia"), ("Zaragoza", "Zaragoza"), ("Melilla", "Melilla"),
    ],
    "Belber": [("Madrid", "Madrid")],
    "Belver": [
        ("Vitoria-Gasteiz", "Araba/Álava"), ("Almería", "Almería"),
        ("Barcelona", "Barcelona"), ("Burgos", "Burgos"), ("Ripoll", "Girona"),
        ("Madrid", "Madrid"), ("Málaga", "Málaga"),
        ("Corvera de Asturias", "Asturias"), ("Salamanca", "Salamanca"),
        ("Astillero, El", "Cantabria"), ("Palacios y Villafranca, Los", "Sevilla"),
        ("Bonrepòs i Mirambell", "Valencia/València"),
        ("Valladolid", "Valladolid"), ("Barakaldo", "Bizkaia"),
        ("Casaseca de las Chanas", "Zamora"), ("Zaragoza", "Zaragoza"),
        ("Melilla", "Melilla"),
    ],
    "Bellver": [
        ("Hellín", "Albacete"), ("Alcoi/Alcoy", "Alicante/Alacant"),
        ("Almería", "Almería"), ("Palma", "Balears, Illes"),
        ("Badalona", "Barcelona"), ("Burgos", "Burgos"),
        ("Alcalà de Xivert", "Castellón/Castelló"), ("Blanes", "Girona"),
        ("Granada", "Granada"), ("Donostia/San Sebastián", "Gipuzkoa"),
        ("Quesada", "Jaén"), ("Alcobendas", "Madrid"), ("Málaga", "Málaga"),
        ("Torres de Cotillas, Las", "Murcia"), ("Sevilla", "Sevilla"),
        ("Tarragona", "Tarragona"), ("Agullent", "Valencia/València"),
        ("Zaragoza", "Zaragoza"),
    ],
    "Bervel": [("Almería", "Almería")],
}

ANDALUCIA = {"Almería", "Cádiz", "Córdoba", "Granada", "Huelva", "Jaén",
             "Málaga", "Sevilla"}


def num(s):
    s = (s or "").strip()
    if s in ("", "."):
        return None  # dato secreto (<5) o vacío
    return float(s.replace(".", "").replace(",", "."))


def filas(ruta):
    with open(ruta, encoding="utf-8") as f:
        dentro = False
        for r in csv.reader(f):
            if r and r[0] in ("Provincia", "Municipio"):
                dentro = True
                continue
            if dentro and r and r[0]:
                yield r[0], [num(x) for x in r[1:7]]


def main(d, salida):
    out = {"grafias": GRAFIAS, "andalucia": sorted(ANDALUCIA),
           "residencia": {}, "nacimiento": {}, "municipios": {}, "totales": {}}
    for g in GRAFIAS:
        for tipo, fich in (("residencia", "provincia_de_residencia"),
                           ("nacimiento", "provincia_de_nacimiento")):
            datos = {}
            for nombre, v in filas(os.path.join(d, f"apellido_{g}_-Por_{fich}.csv")):
                if nombre == "Total":
                    out["totales"].setdefault(g, {})[tipo] = v
                else:
                    datos[nombre] = v
            out[tipo][g] = datos
        cortes = dict(CORTES[g])
        prov, munis = None, []
        for nombre, v in filas(os.path.join(d, f"apellido_{g}_-Por_municipio.csv")):
            if nombre in cortes and (prov is None or list(cortes).index(nombre) >
                                     list(cortes).index(next(k for k, p in cortes.items() if p == prov))):
                prov = cortes[nombre]
            if prov is None:
                raise SystemExit(f"{g}: municipio sin provincia: {nombre}")
            munis.append([nombre, prov] + v)
        out["municipios"][g] = munis
        usados = {m[1] for m in munis}
        falta = set(cortes.values()) - usados
        if falta:
            raise SystemExit(f"{g}: cortes no usados {falta}")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
