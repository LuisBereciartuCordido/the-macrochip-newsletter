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
from briefing.semanas import semana_iso

log = logging.getLogger("fetch_data")

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"


def descargar() -> dict[str, dict]:
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
    datos.update(mercados.cierres_semanales())

    return {clave: dato.to_dict() for clave, dato in datos.items()}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--semana", help="Forzar la semana ISO (AAAA-Sww); por defecto, la semana actual"
    )
    args = parser.parse_args(argv)

    semana = args.semana or semana_iso(datetime.date.today())

    try:
        datos = descargar()
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
