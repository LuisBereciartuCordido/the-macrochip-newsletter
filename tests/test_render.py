import copy

from briefing import render

from .test_schema import _informe_minimo_valido

MODULOS_CFG = [
    {"id": "eeuu", "titulo": "EE. UU."},
    {"id": "europa", "titulo": "Europa"},
    {"id": "asia_china", "titulo": "Asia y China"},
    {"id": "emergentes", "titulo": "Emergentes"},
    {"id": "energia_materias_primas", "titulo": "Energía y materias primas"},
    {"id": "tecnologia_ia", "titulo": "Tecnología e IA"},
    {"id": "geopolitica_riesgos", "titulo": "Geopolítica y riesgos"},
]

MERCADOS_CFG = [
    {"id": "sp500", "nombre": "S&P 500", "unidad": "puntos"},
    {"id": "eur_usd", "nombre": "EUR/USD", "unidad": "USD por EUR"},
    {"id": "oro", "nombre": "Oro", "unidad": "USD/onza"},
]


def test_formatear_valor_puntos_sin_decimales() -> None:
    assert render._formatear_valor(7700.5, "puntos") == "7,700 puntos"


def test_formatear_valor_porcentaje() -> None:
    assert render._formatear_valor(2.87, "% interanual") == "2.9 %"


def test_formatear_valor_eur_usd_cuatro_decimales() -> None:
    assert render._formatear_valor(1.0834, "USD por EUR") == "1.0834 USD"


def test_formatear_variacion_sin_semana_anterior() -> None:
    assert render._formatear_variacion(100, None) == "—"


def test_formatear_variacion_positiva_lleva_signo() -> None:
    assert render._formatear_variacion(110, 100) == "+10.00 %"


def test_formatear_variacion_negativa() -> None:
    assert render._formatear_variacion(90, 100) == "-10.00 %"


def test_formatear_variacion_coloreada_en_verde_si_sube() -> None:
    salida = render._formatear_variacion_coloreada(110, 100)
    assert f'color:{render.COLOR_VARIACION_POSITIVA}' in salida
    assert "+10.00 %" in salida


def test_formatear_variacion_coloreada_en_rojo_si_baja() -> None:
    salida = render._formatear_variacion_coloreada(90, 100)
    assert f'color:{render.COLOR_VARIACION_NEGATIVA}' in salida
    assert "-10.00 %" in salida


def test_formatear_variacion_coloreada_sin_semana_anterior_no_colorea() -> None:
    assert render._formatear_variacion_coloreada(100, None) == "—"


def test_renderizar_lo_esencial() -> None:
    informe = {"lo_esencial": ["Primera cosa.", "Segunda cosa."]}
    salida = render.renderizar_lo_esencial(informe)
    assert "- Primera cosa." in salida
    assert "- Segunda cosa." in salida


def test_renderizar_mercados_con_variacion() -> None:
    datos = {"sp500": {"valor": 7700.0}, "eur_usd": {"valor": 1.08}}
    anterior = {"sp500": {"valor": 7000.0}}

    salida = render.renderizar_mercados(datos, anterior, MERCADOS_CFG)

    assert "S&P 500" in salida
    assert "+10.00 %" in salida  # variación respecto a la semana anterior
    assert "—" in salida  # eur_usd no tiene semana anterior en este test
    assert "sin dato" in salida  # "oro" no está en `datos`
    assert "|" not in salida  # lista, no tabla Markdown (sección 11)


def test_renderizar_macro_global_incluye_emoji_de_confianza() -> None:
    informe = _informe_minimo_valido()
    salida = render.renderizar_macro_global(informe)
    assert "✅" in salida  # la noticia de ejemplo tiene confianza=confirmado
    assert informe["macro_global"][0]["titulo"] in salida


def test_renderizar_modulos_sin_novedades() -> None:
    informe = _informe_minimo_valido()  # todos los módulos vienen sin_novedades=True
    salida = render.renderizar_modulos(informe, MODULOS_CFG)
    assert "Sin novedades relevantes esta semana." in salida
    assert "EE. UU." in salida
    assert "Geopolítica y riesgos" in salida


def test_renderizar_modulos_respeta_el_orden_de_modulos_ids() -> None:
    informe = _informe_minimo_valido()
    salida = render.renderizar_modulos(informe, MODULOS_CFG)
    assert salida.index("EE. UU.") < salida.index("Europa") < salida.index("Geopolítica y riesgos")


def test_renderizar_concepto_semana() -> None:
    informe = _informe_minimo_valido()
    salida = render.renderizar_concepto_semana(informe)
    assert informe["concepto_semana"]["titulo"] in salida
    assert informe["concepto_semana"]["texto"] in salida


def test_renderizar_perspectiva_con_listas_vacias() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["perspectiva_largo_plazo"] = {"estructural": [], "ruido": []}
    salida = render.renderizar_perspectiva(informe)
    assert salida.count("(nada reseñable)") == 2


def test_renderizar_para_profundizar_omite_modulos_sin_novedades() -> None:
    informe = _informe_minimo_valido()  # todos los módulos están sin_novedades=True
    salida = render.renderizar_para_profundizar(informe, MODULOS_CFG)
    assert "Macro global" in salida  # macro_global sí tiene una noticia de ejemplo
    assert "eeuu" not in salida


def test_renderizar_para_profundizar_usa_el_titulo_del_modulo_no_el_id() -> None:
    # Bug real encontrado en pruebas locales (sección 13): usaba el id ("asia_china") en vez del título
    # ("Asia y China") que viene de modulos_cfg.
    informe = _informe_minimo_valido()
    informe["modulos"]["asia_china"] = {
        "sin_novedades": False,
        "noticias": [
            {
                "id": "x",
                "hilo_id": "x",
                "titulo": "t",
                "texto": "t",
                "por_que_importa": "t",
                "confianza": "confirmado",
                "relevancia_espana_ue": "media",
                "fuentes": [
                    {
                        "url": "https://www.reuters.com/a",
                        "medio": "Reuters",
                        "nivel": 2,
                        "fecha": "2026-10-06",
                        "idioma": "es",
                    }
                ],
                "cifras": [],
            }
        ],
    }
    salida = render.renderizar_para_profundizar(informe, MODULOS_CFG)
    assert "Asia y China" in salida
    assert "asia_china" not in salida


def test_renderizar_indice_no_promete_enlaces_de_ancla() -> None:
    salida = render.renderizar_indice(MODULOS_CFG)
    assert "EE. UU." in salida
    assert "[" not in salida  # no son enlaces, solo una lista de lectura


def test_renderizar_titulo() -> None:
    informe = _informe_minimo_valido()
    salida = render.renderizar_titulo(informe, "The Macrochip", "https://x.test/logo.png")
    assert "The Macrochip" in salida
    assert informe["titular"]["texto"] in salida
    assert "5 al 11 de octubre de 2026" in salida
    assert 'src="https://x.test/logo.png"' in salida
    assert f'width="{render.LOGO_ANCHO_PX}"' in salida


def test_formatear_rango_fechas_mismo_mes() -> None:
    assert render._formatear_rango_fechas("2026-10-05", "2026-10-11") == "5 al 11 de octubre de 2026"


def test_formatear_rango_fechas_cruza_de_mes() -> None:
    assert (
        render._formatear_rango_fechas("2026-10-29", "2026-11-04")
        == "29 de octubre al 4 de noviembre de 2026"
    )


def test_formatear_rango_fechas_cruza_de_anio() -> None:
    assert (
        render._formatear_rango_fechas("2026-12-28", "2027-01-03")
        == "28 de diciembre de 2026 al 3 de enero de 2027"
    )


def test_renderizar_contexto_ia_incluye_datos_y_noticias() -> None:
    informe = _informe_minimo_valido()
    datos = {"sp500": {"valor": 7700.0, "unidad": "puntos", "fecha": "2026-10-03", "fuente": "FRED"}}

    salida = render.renderizar_contexto_ia(informe, datos)

    assert "sp500" in salida
    assert informe["macro_global"][0]["titulo"] in salida
    assert informe["macro_global"][0]["hilo_id"] in salida
    assert "```" in salida  # bloque de código copiable


def test_renderizar_contexto_ia_recorta_si_supera_el_limite() -> None:
    informe = _informe_minimo_valido()
    salida = render.renderizar_contexto_ia(informe, datos={}, limite_caracteres=50)
    assert "[...contexto recortado por tamaño...]" in salida


def test_renderizar_contexto_ia_recorta_por_linea_completa_no_a_mitad_de_frase() -> None:
    # Hallazgo real: antes recortaba por conteo de caracteres a lo bruto y
    # dejaba una frase cortada a mitad de palabra. Ahora descarta la última
    # línea entera si no cabe completa, en vez de dejarla a medias.
    informe = _informe_minimo_valido()
    informe["macro_global"].append(
        {
            **informe["macro_global"][0],
            "id": "2026-S41-macro-02",
            "hilo_id": "otro-hilo",
            "titulo": "Segunda noticia con un titulo bastante largo para forzar el recorte",
            "texto": "Texto de la segunda noticia que no debería aparecer cortado a medias.",
        }
    )
    sin_limite = render.renderizar_contexto_ia(informe, datos={}, limite_caracteres=10**9)
    # limite_caracteres se mide sobre el cuerpo (empieza en "PROMPT
    # SUGERIDO:"), no sobre la salida completa (que lleva cabecera y
    # enlace delante) — hay que descontar ese desplazamiento.
    inicio_cuerpo = sin_limite.index("PROMPT SUGERIDO:")
    limite_justo = sin_limite.index("\n- [otro-hilo]") - inicio_cuerpo

    salida = render.renderizar_contexto_ia(informe, datos={}, limite_caracteres=limite_justo)

    assert "Segunda noticia" not in salida  # se descarta entera, no a medias
    assert "[...contexto recortado por tamaño...]" in salida


def test_renderizar_contexto_ia_incluye_enlaces_a_claude_y_chatgpt() -> None:
    informe = _informe_minimo_valido()
    salida = render.renderizar_contexto_ia(informe, datos={})
    assert "https://claude.ai/new?q=" in salida
    assert "Abrir directamente en Claude" in salida
    assert "https://chat.openai.com/?q=" in salida
    assert "Abrir directamente en ChatGPT" in salida


def test_renderizar_transparencia_cuenta_fuentes_por_nivel() -> None:
    informe = _informe_minimo_valido()  # una fuente de nivel 1
    salida = render.renderizar_transparencia(informe)
    assert "nivel 1: 1" in salida
    assert "nivel 2: 0" in salida


def test_renderizar_transparencia_cuenta_descartes_por_motivo() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["fuentes_descartadas"] = [
        {"url": "https://x.com/a", "motivo": "paywall"},
        {"url": "https://x.com/b", "motivo": "paywall"},
        {"url": "https://x.com/c", "motivo": "antigua"},
    ]
    salida = render.renderizar_transparencia(informe)
    assert "paywall: 2" in salida
    assert "antigua: 1" in salida


def test_renderizar_transparencia_resume_mas_de_5_cambios() -> None:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe["cambios_verificador"] = [
        {"noticia_id": f"n{i}", "cambio": "x", "motivo": "y"} for i in range(7)
    ]
    salida = render.renderizar_transparencia(informe)
    assert "2 cambio(s) más en log.json" in salida


def test_renderizar_aviso_legal() -> None:
    assert "No es asesoramiento financiero" in render.renderizar_aviso_legal()


def test_renderizar_informe_junta_todas_las_secciones_en_orden() -> None:
    informe = _informe_minimo_valido()
    salida = render.renderizar_informe(
        informe,
        datos={},
        datos_semana_anterior=None,
        mercados_cfg=MERCADOS_CFG,
        modulos_cfg=MODULOS_CFG,
        nombre_newsletter="The Macrochip",
        logo_url="https://x.test/logo.png",
    )

    for titulo in (
        "The Macrochip",
        informe["titular"]["texto"],
        "Lo esencial",
        "Mercados esta semana",
        "Macro global",
        "Concepto de la semana",
        "Perspectiva de largo plazo",
        "Para profundizar",
        "Paquete de contexto para IA",
        "No es asesoramiento financiero",
    ):
        assert titulo in salida

    assert salida.index("Lo esencial") < salida.index("Mercados esta semana")
    assert salida.index("Para profundizar") < salida.index("Paquete de contexto para IA")


def test_renderizar_informe_no_incluye_la_transparencia() -> None:
    # Decisión de producto (sección 5): "cómo se hizo este informe" no va
    # en el email público, solo en transparencia.md (de uso interno).
    informe = _informe_minimo_valido()
    salida = render.renderizar_informe(
        informe,
        datos={},
        datos_semana_anterior=None,
        mercados_cfg=MERCADOS_CFG,
        modulos_cfg=MODULOS_CFG,
        nombre_newsletter="The Macrochip",
        logo_url="https://x.test/logo.png",
    )
    assert "Cómo se hizo este informe" not in salida
