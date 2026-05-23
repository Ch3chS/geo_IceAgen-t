# Configuración de rutas
import rasterio
import matplotlib.pyplot as plt
import numpy as np
import geopandas as gpd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "landsat"
# Ruta a tu shapefile (ajusta la carpeta "vector" si la llamaste distinto)
VECTOR_PATH = BASE_DIR / "data" / "IPG_2022_v2" / "INV_PG_2022_v2.shp"

# 1. Buscar automáticamente todos los archivos .tif procesados
archivos_procesados = list(PROCESSED_DIR.glob("*.tif"))

if not archivos_procesados:
    print(f"Error: No se encontraron archivos en {PROCESSED_DIR}")
    exit()

# Seleccionamos el primero de la lista para visualizar
TIF_PATH = archivos_procesados[0]
print(f"Visualizando: {TIF_PATH.name}")

# 2. Cargar y procesar datos para visualización
with rasterio.open(TIF_PATH) as src:
    ndsi = src.read(1)
    
    # EXTRAER METADATOS ESPACIALES CLAVE
    # Sacamos los límites y el CRS para poder alinear el polígono vectorial
    bounds = src.bounds
    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
    raster_crs = src.crs
    
    # Reemplazamos el NoData (-9999) por NaN para que no afecte el color
    ndsi = np.where(ndsi == -9999, np.nan, ndsi)

# 3. Cargar y preparar el polígono de la DGA
print("Cargando y alineando polígono vectorial...")
inventario_dga = gpd.read_file(VECTOR_PATH)
echaurren_vector = inventario_dga[
    inventario_dga['NOMBRE'].str.contains('Echaurren Norte', case=False, na=False)
]
# Reproyectamos sobre la marcha para asegurar que calce con el satélite
echaurren_utm = echaurren_vector.to_crs(raster_crs)

# 4. Crear el gráfico
fig, ax = plt.subplots(figsize=(10, 8))

# El NDSI va de -1 a 1.
# AGREGAMOS EL "EXTENT": Esto ubica los píxeles en sus metros UTM reales
# img = ax.imshow(ndsi, cmap='terrain', vmin=-0.2, vmax=1.0, extent=extent)

# Aplicamos interpolación bilineal para suavizar los bordes de los píxeles de 30m
img = ax.imshow(ndsi, cmap='terrain', vmin=-0.2, vmax=1.0, extent=extent, interpolation='bilinear')

# DIBUJAMOS EL POLÍGONO
# Lo anclamos al mismo eje (ax), transparente por dentro, borde negro, y tu alpha de 0.7
echaurren_utm.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=2, alpha=0.7)

plt.colorbar(img, label='Índice NDSI')
ax.set_title(f"Mapa de Nieve/Hielo - Glaciar Echaurren\nArchivo: {TIF_PATH.name}")

# Cambiamos las etiquetas numéricas a metros UTM
ax.set_xlabel("Coordenadas Este (m)")
ax.set_ylabel("Coordenadas Norte (m)")
ax.ticklabel_format(style='plain', axis='both') # Adiós a la notación científica

plt.show()