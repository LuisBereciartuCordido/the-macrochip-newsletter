#!/usr/bin/env python3
"""Descarga los datos duros de la semana y los guarda en data/<semana>/datos.json.

Uso:
    python scripts/fetch_data.py [--semana AAAA-Sww]

Si falla cualquier fuente, el script termina con código de salida distinto
de cero y **no** escribe datos.json (sección 4 de CLAUDE.md: "si un paso
falla, el flujo se detiene... y no crea el borrador").
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

from briefing.fuentes import ecb, eurostat, fred, ine, mercados
from briefing.modelos import Dato
from briefing.semanas import semana_anterior, semana_iso

log = logging.getLogger("fetch_data")

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"

# 35%: generoso a propósito. Ningún instrumento de mercados.INSTRUMENTOS
# debería moverse tanto en una semana sin que ya fuera, de por sí, la
# noticia principal — este umbral existe para pillar errores de datos
# (decimal desplazado, ticker equivocado, endpoint devolviendo otra cosa),
# no movimientos de mercado reales por grandes que sean.
UMBRAL_VARIACION_SEMANAL_SOSPECHOSA = 0.35


class VariacionSospechosa(ValueError):
    """Un instrumento de mercado cambió más de lo plausible en una semana."""


def _comprobar_variaciones_plausibles(
    datos_mercado: dict[str, dict], datos_semana_anterior: dict | None
) -> None:
    if not datos_semana_anterior:
        return
    for clave, dato in datos_mercado.items():
        anterior = datos_semana_anterior.get(clave)
        if not anterior or not anterior.get("valor"):
            continue
        variacion = abs(dato["valor"] - anterior["valor"]) / abs(anterior["valor"])
        if variacion > UMBRAL_VARIACION_SEMANAL_SOSPECHOSA:
            raise VariacionSospechosa(
                f"{clave}: {anterior['valor']} -> {dato['valor']} es un cambio del "
                f"{variacion:.0%} en una semana, por encima del "
                f"{UMBRAL_VARIACION_SEMANAL_SOSPECHOSA:.0%} esperado"
            )


def descargar(*, datos_semana_anterior: dict | None = None) -> dict[str, dict]:
    """Descarga todos los datos duros y devuelve el dict listo para datos.json.

    Las series mensuales (IPC/IPCA) se incluyen siempre, con su fecha real
    de publicación, aunque no hayan cambiado desde la semana anterior —
    antes se omitían si no eran "nuevas" (sección 6 de CLAUDE.md), pero eso
    le quitaba al redactor cualquier dato oficial estructurado al que
    citar cuando no había publicación esa semana, y acababa citando un
    medio externo en su lugar (hallazgo real, semana 2026-S42). Que un dato
    sea "noticia nueva" o "la última cifra oficial disponible" lo decide
    el criterio del redactor mirando la fecha (`prompts/redactor.md`), no
    la ausencia del dato.

    Si se pasa `datos_semana_anterior` (el datos.json de la semana ISO
    anterior), los instrumentos de Yahoo Finance (mercados.INSTRUMENTOS) se
    comprueban contra esa semana: una variación por encima de
    UMBRAL_VARIACION_SEMANAL_SOSPECHOSA aborta la descarga en vez de dejar
    pasar en silencio lo que probablemente sea un error de datos (sección
    6: Yahoo es un endpoint no oficial y sin fuente de respaldo).
    """
    datos: dict[str, Dato] = {}

    log.info("Descargando datos del BCE...")
    datos["bce_tipo_deposito"] = ecb.tipo_facilidad_deposito()
    datos["eur_usd"] = ecb.eur_usd_referencia()

    log.info("Descargando IPCA de la eurozona (Eurostat)...")
    datos["ipca_eurozona"] = eurostat.ipca_eurozona()

    log.info("Descargando IPC de España (INE)...")
    datos["ipc_espana"] = ine.ipc_espana()

    log.info("Descargando datos de la Fed y mercados de EE. UU. (FRED)...")
    datos["fed_tipo"] = fred.tipo_fed()
    datos["ipc_eeuu"] = fred.ipc_eeuu()
    datos["sp500"] = fred.sp500()
    datos["brent"] = fred.brent()

    log.info("Descargando mercados vía Yahoo Finance...")
    datos_yahoo = mercados.cierres_semanales()
    datos.update(datos_yahoo)

    resultado = {clave: dato.to_dict() for clave, dato in datos.items()}
    _comprobar_variaciones_plausibles(
        {clave: resultado[clave] for clave in datos_yahoo}, datos_semana_anterior
    )
    return resultado


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--semana", help="Forzar la semana ISO (AAAA-Sww); por defecto, la semana actual"
    )
    args = parser.parse_args(argv)

    semana = args.semana or semana_iso(datetime.date.today())

    ruta_semana_anterior = DATA_DIR / semana_anterior(semana) / "datos.json"
    datos_semana_anterior = (
        json.loads(ruta_semana_anterior.read_text()) if ruta_semana_anterior.exists() else None
    )

    try:
        datos = descargar(datos_semana_anterior=datos_semana_anterior)
    except Exception:
        log.exception("Fallo al descargar los datos duros; no se escribe datos.json")
        return 1

    destino = DATA_DIR / semana
    destino.mkdir(parents=True, exist_ok=True)
    ruta_datos = destino / "datos.json"
    ruta_datos.write_text(json.dumps(datos, indent=2, ensure_ascii=False, sort_keys=True))
    log.info("Escrito %s", ruta_datos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
