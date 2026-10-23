import datetime
import re

import pytest
import responses

from briefing.fuentes import mercados
from briefing.fuentes.mercados import INSTRUMENTOS, CotizacionDemasiadoAntigua, SinCotizacion

URL_URTH = "https://query1.finance.yahoo.com/v8/finance/chart/URTH"
URL_PATRON = re.compile(r"https://query1\.finance\.yahoo\.com/v8/finance/chart/.*")


def _fixture(marcas: list[int], cierres: list[float | None]) -> dict:
    return {
        "chart": {
            "result": [{"timestamp": marcas, "indicators": {"quote": [{"close": cierres}]}}],
            "error": None,
        }
    }


@responses.activate
def test_ultimo_cierre_ignora_el_ultimo_valor_si_es_nulo() -> None:
    # 1759536000 = 2025-10-04 (sesión en curso, todavía sin cerrar -> None)
    responses.add(
        responses.GET,
        URL_URTH,
        json=_fixture([1759449600, 1759536000], [209.5, None]),
        status=200,
    )

    fecha, valor = mercados._ultimo_cierre("URTH", hoy=datetime.date(2025, 10, 4))

    assert valor == 209.5
    assert fecha == "2025-10-03"


@responses.activate
def test_sin_resultado_lanza_error_explicito() -> None:
    responses.add(
        responses.GET,
        URL_URTH,
        json={"chart": {"result": None, "error": {"description": "No data found"}}},
        status=200,
    )

    with pytest.raises(SinCotizacion):
        mercados._ultimo_cierre("URTH")


@responses.activate
def test_todos_los_cierres_nulos_lanza_error_explicito() -> None:
    responses.add(
        responses.GET,
        URL_URTH,
        json=_fixture([1759449600], [None]),
        status=200,
    )

    with pytest.raises(SinCotizacion):
        mercados._ultimo_cierre("URTH")


@responses.activate
def test_cierres_semanales_devuelve_los_cinco_instrumentos() -> None:
    responses.add(
        responses.GET,
        URL_PATRON,
        json=_fixture([1759449600], [100.0]),
        status=200,
    )

    resultado = mercados.cierres_semanales(hoy=datetime.date(2025, 10, 3))

    assert set(resultado) == set(INSTRUMENTOS)
    for dato in resultado.values():
        assert dato.fuente == "Yahoo Finance (no oficial)"
        assert dato.valor == 100.0


@responses.activate
def test_cierre_demasiado_antiguo_lanza_error_explicito() -> None:
    # Mismo fixture que el primer test (cierre real del 2025-10-03), pero
    # comprobado contra una fecha "hoy" muy posterior: el endpoint no
    # debería devolver nunca un cierre tan viejo con "range": "5d".
    responses.add(
        responses.GET,
        URL_URTH,
        json=_fixture([1759449600, 1759536000], [209.5, None]),
        status=200,
    )

    with pytest.raises(CotizacionDemasiadoAntigua):
        mercados._ultimo_cierre("URTH", hoy=datetime.date(2025, 12, 1))
