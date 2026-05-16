# import rasterio
# from rasterio.plot import show
# from rasterio.enums import Resampling
# import matplotlib.pyplot as plt
# from pathlib import Path

# # Construir la ruta al archivo dinámicamente según la estructura de tu proyecto
# print("HOLAAAAA")
# base_dir = Path(__file__).resolve().parents[1]
# print(base_dir)
# file_name = "S2B_MSIL2A_20230331T142719_R053_T19HEA_20240826T093847_B03.tif"
# file_path = base_dir / "data" / "raw" / "sentinel2" / file_name
# print(file_path)

# if not file_path.exists():
#     print(f"Error: No se encontró el archivo en {file_path}")
# else:
#     print(f"Abriendo y procesando: {file_path.name}")
#     print("Cargando la interfaz gráfica... (esto puede tardar unos segundos)")
    
#     # Usar rasterio para abrir el GeoTIFF
#     with rasterio.open(file_path) as src:
#         print("\n--- METADATOS DE LA IMAGEN ---")
#         print(f"Dimensiones: {src.width} columnas x {src.height} filas")
#         print(f"Total de píxeles: {src.width * src.height:,}")
#         print(f"Resolución espacial: {src.res[0]}m x {src.res[1]}m")
#         print(f"Sistema de Coordenadas (CRS): {src.crs}")
#         print(f"Cantidad de bandas: {src.count}")
#         print("------------------------------\n")

#         # Factor de escala (0.1 = 10% de la resolución original)
#         scale = 0.1
        
#         # Leer la banda 1 (B03) redimensionada para evitar el lag
#         data = src.read(
#             1,
#             out_shape=(int(src.height * scale), int(src.width * scale)),
#             resampling=Resampling.bilinear
#         )
        
#         # Ajustar la transformación para que las coordenadas en el gráfico sigan siendo reales
#         transform = src.transform * src.transform.scale(
#             (src.width / data.shape[1]), (src.height / data.shape[0])
#         )

#         fig, ax = plt.subplots(figsize=(10, 10))
#         # Pasamos el arreglo "data" y su "transform" en lugar de "src" completo
#         show(data, transform=transform, ax=ax, title="Sentinel-2 Banda 3 (10% Resolución)", cmap='gray')
#         plt.show()
import rasterio
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Configuración de rutas
BASE_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BASE_DIR / "data" / "processed" / "sentinel2"

# 1. Buscar automáticamente todos los archivos .tif procesados
archivos_procesados = list(PROCESSED_DIR.glob("*.tif"))

if not archivos_procesados:
    print(f"Error: No se encontraron archivos en {PROCESSED_DIR}")
    exit()

# Seleccionamos el primero de la lista para visualizar
TIF_PATH = archivos_procesados[6]
print(f"Visualizando: {TIF_PATH.name}")

# 2. Cargar y procesar datos para visualización
with rasterio.open(TIF_PATH) as src:
    ndsi = src.read(1)
    # Reemplazamos el NoData (-9999) por NaN para que no afecte el color
    ndsi = np.where(ndsi == -9999, np.nan, ndsi)

# 3. Crear el gráfico
plt.figure(figsize=(10, 8))

# El NDSI va de -1 a 1. El hielo suele estar sobre 0.4.
# Usamos un mapa de colores que resalte el azul (hielo)
img = plt.imshow(ndsi, cmap='terrain', vmin=-0.2, vmax=1.0)

plt.colorbar(img, label='Índice NDSI')
plt.title(f"Mapa de Nieve/Hielo - Glaciar Echaurren\nArchivo: {TIF_PATH.name}")
plt.xlabel("Píxeles (Ancho)")
plt.ylabel("Píxeles (Alto)")

plt.show()