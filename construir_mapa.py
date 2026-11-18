"""Genera apellido.html a partir de mapa_plantilla.html y los CSV del INE.
Uso: python3 -I construir_mapa.py <dir_csv> <geo.json>"""
import json, subprocess, sys, os, tempfile
d = os.path.dirname(os.path.abspath(__file__))
tmp = os.path.join(tempfile.mkdtemp(), "ine.json")
subprocess.run([sys.executable, "-I", os.path.join(d, "parse_ine.py"), sys.argv[1], tmp], check=True)
datos = open(tmp, encoding="utf-8").read().replace("</", "<\\/")
html = open(os.path.join(d, "mapa_plantilla.html"), encoding="utf-8").read().replace("/*DATOS_INE*/", datos).replace("/*DATOS_GEO*/", open(sys.argv[2], encoding="utf-8").read())
open(os.path.join(d, "apellido.html"), "w", encoding="utf-8").write(html)
print("apellido.html", len(html))
