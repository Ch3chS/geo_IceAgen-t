# Directorio docker/

## Descripción

Contiene el entrypoint del contenedor. La definición de la imagen vive en el
`Dockerfile` de la raíz y la orquestación en `docker-compose.yml`.

## Estructura del directorio

- `entrypoint.sh` Punto de entrada del contenedor. Despacha subcomandos
  (`dashboard`, `pipeline`, `snowmelt`, `test`, `shell`).

## Cómo se arma la imagen

`Dockerfile` (raíz) usa un build **multi-etapa**:

1. `builder-rust` (`rust:1-slim-bookworm`): compila `snowmelt-cli`, el motor de
   balance de masa de la Etapa 5b. El workspace usa *edition 2024*, que exige
   Rust ≥ 1.85.
2. `runtime` (`python:3.13-slim-bookworm`): instala `requirements.txt`, copia el
   código y trae **solo el binario** desde la etapa anterior. El toolchain de
   Rust y el `target/` no viajan a la imagen final.

El binario se copia a `snowmelt-rs/target/release/snowmelt` porque es la ruta
exacta donde lo busca `scripts/run_snowmelt.py` (`SNOWMELT_BIN_CANDIDATES`). Así
la dockerización no requiere modificar el código Python.

## Uso

```bash
docker compose up -d              # dashboard en http://localhost:8501
docker compose logs -f dashboard
docker compose down
```

Otros subcomandos:

```bash
docker compose run --rm dashboard test              # pytest
docker compose run --rm dashboard shell             # bash interactivo
docker compose run --rm pipeline                    # pipeline completo
docker compose run --rm pipeline pipeline juncal    # un solo glaciar
docker compose run --rm dashboard snowmelt echaurren
```

## Decisiones de diseño

**Los datos no van en la imagen.** `data/` pesa ~15 GB (rasteres Landsat,
Sentinel-2 y FABDEM) y se genera localmente. `data/` y `outputs/` se montan como
volúmenes desde el host; `.dockerignore` los excluye del contexto de build.
Consecuencia: el contenedor necesita el repositorio clonado, no se basta a sí mismo.

**El pipeline no es el comando por defecto.** `docker compose up` levanta solo el
dashboard. El pipeline vive en un perfil aparte porque re-descarga ~15 GB y
**sobreescribe `outputs/<glaciar>/*.csv`** en el host. Si eso pasa por error, los
CSV versionados se restauran con `git checkout -- outputs/`.

**No se incluye PostGIS.** El pipeline trabaja con rasteres GeoTIFF y vectores
GeoPackage, no con base de datos: un contenedor PostGIS quedaría sin uso. Si el
proyecto migra los vectores a base de datos, se agrega en ese momento.

**`setup.sh` no se usa dentro del contenedor.** Ese script crea y activa un
`venv`, redundante acá porque el contenedor ya es el entorno aislado.
`entrypoint.sh` replica la misma secuencia del pipeline. `setup.sh` sigue siendo
el camino para una instalación nativa en Linux.

## Notas de operación

- **Docker Desktop debe estar abierto** antes de cualquier comando: el daemon no
  se levanta solo al invocar `docker` (falla con
  `failed to connect to the docker API ... dockerDesktopLinuxEngine`).
- Streamlit se lanza con `--server.address=0.0.0.0`. Sin eso escucharía en el
  `localhost` del contenedor y sería inalcanzable desde el navegador del host.
- `entrypoint.sh` debe conservar finales de línea **LF**. Con CRLF (al editarlo
  desde Windows) el contenedor falla con `bad interpreter`.
- Dentro del contenedor **no** hay que tocar `PROJ_LIB`/`PROJ_DATA`: quedan sin
  definir a propósito y `rasterio`/`pyproj` usan su PROJ empaquetado.
