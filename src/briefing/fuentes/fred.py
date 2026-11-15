"""Cliente de datos de la Fed y mercados de EE. UU. vía la API de FRED.

Requiere la variable de entorno FRED_API_KEY (clave gratuita, se obtiene
en https://fred.stlouisfed.org/docs/api/api_key.html).
"""

from __future__ import annotations

import logging
import os

import requests

from briefing.modelos import Dato

log = logging.getLogger(__name__)

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
TIMEOUT_SEGUNDOS = 20


class FredApiKeyFaltante(RuntimeError):
    """No se encontró la variable de entorno FRED_API_KEY."""


class SinObservaciones(ValueError):
    """FRED no devolvió ninguna observación con valor real para la serie pedida."""


# Cuántas observaciones recientes se piden para buscar la última con valor
# real. FRED marca una observación sin dato como "." en vez de omitirla —
# hallazgo real: en noviembre de 2026, el IPC de EE. UU. (CPIAUCSL con
# units=pc1, variación interanual) devolvía "." para octubre de 2026 porque
# la comparación interanual necesita el índice de octubre de 2025, mes que
# el BLS nunca llegó a publicar por el cierre del Gobierno federal de ese
# año. Con limit=1 (pedir solo la más reciente) el pipeline entero se
# paraba en fetch_data.py. El mismo fallo podría darse en cualquiera de las
# otras series de FRED (p. ej. SP500 o DCOILBRENTEU un día festivo en el
# que FRED aún no haya publicado el último cierre), así que el margen vive
# en el helper compartido, no solo en el caso del IPC.
MAX_OBSERVACIONES_A_REVISAR = 10


def _clave_api() -> str:
    clave = os.environ.get("FRED_API_KEY")
    if not clave:
        raise FredApiKeyFaltante(
            "Falta la variable de entorno FRED_API_KEY (clave gratuita de FRED)"
        )
    return clave


def _ultima_observacion(serie: str, **parametros_extra: str) -> tuple[str, float]:
    """Último dato con valor real de `serie`, retrocediendo si hace falta.

    No fabrica una comparación distinta cuando falta un punto (p. ej. no
    compara contra un mes distinto para "rellenar" un IPC interanual sin
    dato): simplemente usa la fecha real anterior en la que esa misma
    comparación sí existe, y la devuelve con su fecha real — el criterio de
    si presentarlo como noticia o como referencia es del redactor
    (prompts/redactor.md), no de este cliente.
    """
    parametros = {
        "series_id": serie,
        "api_key": _clave_api(),
        "file_type": "json",
        "sort_order": "desc",
        "limit": MAX_OBSERVACIONES_A_REVISAR,
        **parametros_extra,
    }
    log.info("Consultando FRED: serie %s", serie)
    respuesta = requests.get(BASE_URL, params=parametros, timeout=TIMEOUT_SEGUNDOS)
    respuesta.raise_for_status()
    observaciones = respuesta.json().get("observations") or []
    for observacion in observaciones:
        if observacion["value"] != ".":
            return observacion["date"], float(observacion["value"])

    raise SinObservaciones(
        f"FRED no devolvió ninguna observación con valor real para la serie {serie} "
        f"en las últimas {MAX_OBSERVACIONES_A_REVISAR} disponibles"
    )


def _url_serie(serie: str) -> str:
    return f"https://fred.stlouisfed.org/series/{serie}"


def tipo_fed() -> Dato:
    """Tipo de interés efectivo de los fondos federales (FEDFUNDS), % anual."""
    fecha, valor = _ultima_observacion("FEDFUNDS")
    return Dato(valor=valor, unidad="% anual", fecha=fecha, fuente="FRED", url=_url_serie("FEDFUNDS"))


def ipc_eeuu() -> Dato:
    """IPC de EE. UU., variación interanual (CPIAUCSL con units=pc1)."""
    fecha, valor = _ultima_observacion("CPIAUCSL", units="pc1")
    return Dato(
        valor=valor, unidad="% interanual", fecha=fecha, fuente="FRED", url=_url_serie("CPIAUCSL")
    )


def sp500() -> Dato:
    """Último cierre diario del S&P 500 (SP500)."""
    fecha, valor = _ultima_observacion("SP500")
    return Dato(valor=valor, unidad="puntos", fecha=fecha, fuente="FRED", url=_url_serie("SP500"))


def brent() -> Dato:
    """Precio del Brent, USD por barril (DCOILBRENTEU)."""
    fecha, valor = _ultima_observacion("DCOILBRENTEU")
    return Dato(
        valor=valor, unidad="USD/barril", fecha=fecha, fuente="FRED", url=_url_serie("DCOILBRENTEU")
    )
