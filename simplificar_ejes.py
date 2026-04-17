import json
from shapely.geometry import shape, mapping

ruta_entrada = r"C:\Users\rperez\Desktop\Sistema territorial ECH\versiones\v2\zonas_ejes_para_webmap_smr\ejes_ide_24022026.geojson"
ruta_salida  = r"C:\Users\rperez\Desktop\Sistema territorial ECH\versiones\v2\zonas_ejes_para_webmap_smr\ejes_ide_simplificado.geojson"

print("Leyendo archivo...")
with open(ruta_entrada, "r", encoding="utf-8") as f:
    geo = json.load(f)

print(f"Features originales: {len(geo['features'])}")

features_simpl = []
for i, f in enumerate(geo["features"]):
    if i % 10000 == 0:
        print(f"Procesando {i}/{len(geo['features'])}...")
    try:
        geom = shape(f["geometry"])
        geom_s = geom.simplify(0.001, preserve_topology=True)
        if not geom_s.is_empty:
            features_simpl.append({
                "type": "Feature",
                "properties": f.get("properties", {}),
                "geometry": mapping(geom_s)
            })
    except:
        pass

print(f"Features resultado: {len(features_simpl)}")
print("Guardando...")

with open(ruta_salida, "w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection", "features": features_simpl}, f, separators=(",", ":"))

import os
mb = os.path.getsize(ruta_salida) / 1024 / 1024
print(f"Tamaño final: {mb:.1f} MB")
print("Listo!")