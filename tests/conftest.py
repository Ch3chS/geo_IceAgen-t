import os
import sys
from pathlib import Path

# En máquinas con PostgreSQL/PostGIS instalado, PROJ_LIB/PROJ_DATA pueden
# quedar apuntando a la base de datos PROJ de esa instalación, incompatible
# con la que trae empaquetada rasterio (CRSError: DATABASE.LAYOUT.VERSION...).
# Se limpian solo para el proceso de tests -- rasterio usa automáticamente su
# propia base de datos PROJ si no hay una variable externa que la pise. Esto
# no afecta el entorno del sistema ni a otros programas (QGIS, psql, etc.).
for _var in ("PROJ_LIB", "PROJ_DATA"):
    os.environ.pop(_var, None)

# scripts/ no es un paquete instalado; se agrega la raíz del repo a sys.path
# para poder importar `scripts.process_data` y `scripts.spatial_analysis`
# como namespace packages.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
