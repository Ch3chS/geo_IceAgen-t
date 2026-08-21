import pytest

from scripts.glacier_config import (
    DEFAULT_GLACIAR,
    GLACIER_CONFIGS,
    get_config,
)


class TestGetConfig:
    def test_default_es_echaurren(self):
        assert DEFAULT_GLACIAR == "echaurren"
        assert get_config().slug == "echaurren"

    def test_juncal_tiene_datos_completos(self):
        juncal = get_config("juncal")
        assert juncal.slug == "juncal"
        assert juncal.nombre == "Glaciar Juncal Norte"
        assert juncal.crs_epsg == 32719
        assert len(juncal.bbox_wgs84) == 4
        assert len(juncal.aoi_bounds_utm) == 4
        # El AOI UTM de Juncal está al norte del de Echaurren (misma zona 19S)
        assert juncal.aoi_bounds_utm[1] > get_config("echaurren").aoi_bounds_utm[3]

    def test_juncal_estaciones_dga_son_de_aconcagua(self):
        juncal = get_config("juncal")
        assert set(juncal.dga_estaciones.keys()) == {"05403002", "05410002"}

    def test_glaciar_inexistente_levanta_keyerror(self):
        with pytest.raises(KeyError):
            get_config("no_existe")

    def test_todos_los_glaciares_son_validos(self):
        for slug, cfg in GLACIER_CONFIGS.items():
            assert cfg.slug == slug
            assert cfg.umbral_ndsi > 0
            assert cfg.elev_min_m > 0
            assert cfg.resolucion_m > 0