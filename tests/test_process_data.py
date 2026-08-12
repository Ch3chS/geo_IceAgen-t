import numpy as np
import pytest
import rasterio

from scripts import process_data as pdmod


class TestCalcularNdsi:
    def test_nieve_da_ndsi_positivo(self):
        verde = np.array([[0.8]], dtype=np.float32)
        swir = np.array([[0.1]], dtype=np.float32)
        ndsi = pdmod.calcular_ndsi(verde, swir)
        assert ndsi[0, 0] == pytest.approx((0.8 - 0.1) / (0.8 + 0.1))

    def test_roca_sin_nieve_da_ndsi_negativo(self):
        verde = np.array([[0.2]], dtype=np.float32)
        swir = np.array([[0.3]], dtype=np.float32)
        ndsi = pdmod.calcular_ndsi(verde, swir)
        assert ndsi[0, 0] < 0

    def test_denominador_cero_usa_nodata(self):
        verde = np.array([[0.0]], dtype=np.float32)
        swir = np.array([[0.0]], dtype=np.float32)
        ndsi = pdmod.calcular_ndsi(verde, swir, nodata=-9999.0)
        assert ndsi[0, 0] == -9999.0

    def test_valores_quedan_en_rango_valido(self):
        rng = np.random.default_rng(0)
        verde = rng.uniform(0.01, 1.0, size=(10, 10)).astype(np.float32)
        swir = rng.uniform(0.01, 1.0, size=(10, 10)).astype(np.float32)
        ndsi = pdmod.calcular_ndsi(verde, swir)
        assert np.all(ndsi >= -1.0) and np.all(ndsi <= 1.0)

    def test_dtype_de_salida_es_float32(self):
        verde = np.array([[0.5]], dtype=np.float64)
        swir = np.array([[0.2]], dtype=np.float64)
        ndsi = pdmod.calcular_ndsi(verde, swir)
        assert ndsi.dtype == np.float32


class TestPatronSentinel2:
    def test_nombre_valido_extrae_banda_y_fecha(self):
        nombre = "S2A_MSIL2A_20230126T143751_R096_T19HCC_20230126T183045_B03.tif"
        m = pdmod.PATTERN_S2.match(nombre)
        assert m is not None
        assert m.group("band") == "B03"
        assert m.group("date") == "20230126"

    def test_nombre_no_relacionado_no_matchea(self):
        assert pdmod.PATTERN_S2.match("archivo_cualquiera.tif") is None


class TestPatronLandsat:
    def test_nombre_valido_extrae_banda(self):
        nombre = "LC08_L2SP_233083_20230126_02_T1_green.tif"
        m = pdmod.PATTERN_LS.match(nombre)
        assert m is not None
        assert m.group("band") == "green"

    def test_es_insensible_a_mayusculas(self):
        nombre = "LC08_L2SP_233083_20230126_02_T1_SWIR16.tif"
        assert pdmod.PATTERN_LS.match(nombre) is not None

    def test_banda_no_soportada_no_matchea(self):
        nombre = "LC08_L2SP_233083_20230126_02_T1_blue.tif"
        assert pdmod.PATTERN_LS.match(nombre) is None


class TestEpsgDeCrs:
    def test_epsg_valido(self):
        crs = rasterio.crs.CRS.from_epsg(32719)
        assert pdmod._epsg_de_crs(crs) == 32719

    def test_crs_sin_epsg_retorna_menos_uno(self):
        class CrsRoto:
            def to_epsg(self):
                raise ValueError("sin EPSG asociado")

        assert pdmod._epsg_de_crs(CrsRoto()) == -1
