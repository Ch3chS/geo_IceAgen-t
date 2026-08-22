import pytest

from scripts import run_snowmelt as rs
from scripts.glacier_config import get_config


@pytest.fixture(autouse=True)
def _restaurar_echaurren():
    yield
    rs.configurar_glaciar("echaurren")


class TestConfigurarGlaciarRunSnowmelt:
    def test_default_es_echaurren(self):
        assert rs.SLUG == "echaurren"
        assert rs.OUTPUTS_DIR.name == "echaurren"
        assert rs.DEM_ASC_PATH.name == "echaurren_dem.asc"

    def test_juncal_deriva_rutas_correctas(self):
        rs.configurar_glaciar("juncal")
        cfg = get_config("juncal")

        assert rs.SLUG == "juncal"
        assert rs.AOI_BOUNDS == cfg.aoi_bounds_utm
        assert rs.AOI_CRS == f"EPSG:{cfg.crs_epsg}"
        assert rs.FABDEM_PATH.parts[-3:] == ("juncal", "fabdem", "fabdem_dem.tif")
        assert rs.DEM_ASC_PATH.name == "juncal_dem.asc"
        assert "juncal" in rs.FORZANTE_PATH.name
        assert rs.OUTPUTS_DIR.name == "juncal"
        assert set(rs.sa.DGA_ESTACIONES) == {"05403002", "05410002"}
        assert rs.OUT_DIR.name == "out"