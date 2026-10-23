"""Cliente de mercados vía el endpoint no oficial de Yahoo Finance.

Se usa solo para los instrumentos de mercados.yaml sin fuente oficial
gratuita: Nikkei 225, oro y los proxies de MSCI World/Emerging
Markets/Europe (vía ETFs). S&P 500 y Brent salen de FRED, y EUR/USD del
BCE (ver src/briefing/fuentes/fred.py y ecb.py).

Desviación registrada en CLAUDE.md, sección 6: la candidata inicial,
Stooq, quedó descartada porque ahora exige superar un challenge anti-bot
en JavaScript. Este endpoint (el mismo que usa la librería yfinance) no
tiene clave ni challenge, pero tampoco es oficial ni está documentado por
Yahoo — puede cambiar sin aviso. No hay fuente de respaldo todavía: ver la
razón en CLAUDE.md.
"""

from __future__ import annotations

import datetime
import logging

import requests

from briefing.modelos import Dato

log = logging.getLogger(__name__)

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
TIMEOUT_SEGUNDOS = 20
# Excepción deliberada: a diferencia de BCE/Eurostat/INE/FRED (sección 6 de
# CLAUDE.md, donde un User-Agent propio hace que algunos CDN cuelguen la
# conexión), este endpoint de Yahoo sí necesita un User-Agent de navegador
# — sin él, rechaza la petición por parecer tráfico no humano.
CABECERAS = {"User-Agent": "Mozilla/5.0"}

# id de mercados.yaml -> (ticker de Yahoo, unidad). nikkei225 es el índice
# real (puntos); oro es un futuro en USD/onza; los tres MSCI son ETFs
# (sección 13: un ETF cotiza en dólares por participación, no en
# "puntos" — llamarlo así sería un dato incorrecto, no solo un matiz de
# formato), así que su unidad es USD, igual que ya refleja
# config/mercados.yaml.
INSTRUMENTOS: dict[str, tuple[str, str]] = {
    "nikkei225": ("^N225", "puntos"),
    "oro": ("GC=F", "USD/onza"),
    "msci_world": ("URTH", "USD"),
    "msci_em": ("IEMG", "USD"),
    "msci_europe": ("IEUR", "USD"),
}


MAX_DIAS_ANTIGUEDAD = 7


class SinCotizacion(ValueError):
    """Yahoo Finance no devolvió ningún cierre válido para el ticker pedido."""


class CotizacionDemasiadoAntigua(ValueError):
    """El último cierre disponible es más antiguo de lo esperado.

    Con "range": "5d" siempre debería haber un cierre reciente salvo que el
    endpoint esté devolviendo datos obsoletos o cacheados — algo que, dado
    que es un endpoint no documentado (sección 6 de CLAUDE.md), conviene
    detectar con un error explícito en vez de publicar en silencio un precio
    viejo como si fuera el de esta semana.
    """


def _comprobar_frescura(ticker: str, fecha: str, hoy: datetime.date) -> None:
    antiguedad = (hoy - datetime.date.fromisoformat(fecha)).days
    if antiguedad > MAX_DIAS_ANTIGUEDAD:
        raise CotizacionDemasiadoAntigua(
            f"{ticker}: el último cierre disponible es del {fecha}, hace {antiguedad} días "
            f"(más de los {MAX_DIAS_ANTIGUEDAD} esperados)"
        )


def _ultimo_cierre(ticker: str, *, hoy: datetime.date | None = None) -> tuple[str, float]:
    url = f"{BASE_URL}/{ticker}"
    log.info("Consultando Yahoo Finance: %s", ticker)
    respuesta = requests.get(
        url,
        params={"range": "5d", "interval": "1d"},
        headers=CABECERAS,
        timeout=TIMEOUT_SEGUNDOS,
    )
    respuesta.raise_for_status()
    cuerpo = respuesta.json()["chart"]

    resultados = cuerpo.get("result")
    if not resultados:
        raise SinCotizacion(
            f"Yahoo Finance no devolvió datos para {ticker}: {cuerpo.get('error')}"
        )

    resultado = resultados[0]
    marcas_tiempo = resultado["timestamp"]
    cierres = resultado["indicators"]["quote"][0]["close"]

    # El último elemento puede venir sin cerrar (sesión del día en curso),
    # así que se busca desde el final el último cierre que no sea nulo.
    for marca, cierre in zip(reversed(marcas_tiempo), reversed(cierres)):
        if cierre is not None:
            fecha = (
                datetime.datetime.fromtimestamp(marca, tz=datetime.timezone.utc).date().isoformat()
            )
            _comprobar_frescura(ticker, fecha, hoy or datetime.date.today())
            return fecha, float(cierre)

    raise SinCotizacion(f"Yahoo Finance no devolvió ningún cierre válido para {ticker}")


def cierres_semanales(*, hoy: datetime.date | None = None) -> dict[str, Dato]:
    """Último cierre disponible de cada instrumento de INSTRUMENTOS."""
    resultado: dict[str, Dato] = {}
    for id_, (ticker, unidad) in INSTRUMENTOS.items():
        fecha, valor = _ultimo_cierre(ticker, hoy=hoy)
        resultado[id_] = Dato(
            valor=valor,
            unidad=unidad,
            fecha=fecha,
            fuente="Yahoo Finance (no oficial)",
            url=f"https://finance.yahoo.com/quote/{ticker}",
        )
    return resultado
