import copy

import pytest

from briefing import validacion
from briefing.validacion import _parsear_numero

from .test_schema import _informe_minimo_valido


def _fuente(url="https://www.reuters.com/a", medio="Reuters", nivel=2, fecha="2026-10-06"):
    return {"url": url, "medio": medio, "nivel": nivel, "fecha": fecha, "idioma": "en"}


def _noticia(id_="2026-S41-x-01", confianza="una_fuente", fuentes=None, cifras=None, **texto):
    return {
        "id": id_,
        "hilo_id": "algo-2026",
        "titulo": texto.get("titulo", "Título"),
        "texto": texto.get("texto", "Texto de la noticia."),
        "por_que_importa": texto.get("por_que_importa", "Por qué importa."),
        "confianza": confianza,
        "relevancia_espana_ue": "media",
        "fuentes": fuentes if fuentes is not None else [_fuente()],
        "cifras": cifras if cifras is not None else [],
    }


def _informe_con(**overrides) -> dict:
    informe = copy.deepcopy(_informe_minimo_valido())
    informe.update(overrides)
    return informe


# fuentes.yaml de prueba, pequeño y estable: no depende del contenido real
# (que puede crecer) para que estos tests no se rompan cuando se amplíe.
FUENTES_CFG = {
    "niveles": {
        1: {"dominios": ["europa.eu"]},
        2: {"dominios": ["reuters.com", "bloomberg.com"]},
        3: {"dominios": ["project-syndicate.org"]},
    }
}


# --- _parsear_numero -------------------------------------------------------


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("2,9%", 2.9),
        ("82.1", 82.1),
        ("7.700,5 puntos", 7700.5),  # español: punto de miles, coma decimal
        ("7,700.5 USD", 7700.5),  # inglés: coma de miles, punto decimal
        ("-3,2 %", -3.2),
        ("cayó −2,3 % en el mes", -2.3),  # signo menos tipográfico (U+2212)
        ("cayó –2,3 % en el mes", -2.3),  # en dash (U+2013)
        ("cayó —2,3 % en el mes", -2.3),  # em dash (U+2014)
        ("bajó a 2,3.", 2.3),  # punto final de frase, no parte del número
    ],
)
def test_parsear_numero(texto: str, esperado: float) -> None:
    assert _parsear_numero(texto) == esperado


def test_parsear_numero_sin_numero_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        _parsear_numero("sin ningún número aquí")


# --- validar_titular --------------------------------------------------------


def test_titular_que_referencia_una_noticia_real_no_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["titular"] = {"texto": "Algo pasó", "noticia_id": "2026-S41-macro-01"}
    assert validacion.validar_titular(informe) == []


def test_titular_con_id_inexistente_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["titular"] = {"texto": "Algo pasó", "noticia_id": "no-existe"}
    assert len(validacion.validar_titular(informe)) == 1


def test_titular_puede_referenciar_una_noticia_de_un_modulo() -> None:
    informe = _informe_con(macro_global=[])
    informe["modulos"]["eeuu"] = {
        "sin_novedades": False,
        "noticias": [_noticia(id_="2026-S41-eeuu-01")],
    }
    informe["titular"] = {"texto": "Algo pasó", "noticia_id": "2026-S41-eeuu-01"}
    assert validacion.validar_titular(informe) == []


# --- avisos_titular_largo -----------------------------------------------


def test_titular_corto_no_avisa() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["titular"] = {"texto": "Algo pasó", "noticia_id": "2026-S41-macro-01"}
    assert validacion.avisos_titular_largo(informe) == []


def test_titular_largo_avisa() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["titular"] = {
        # Caso real: 93 caracteres, se truncaba como asunto de email.
        "texto": "Los huthíes golpean una instalación de Aramco mientras la Fed y el BCE esperan a final de mes",
        "noticia_id": "2026-S41-macro-01",
    }
    assert len(validacion.avisos_titular_largo(informe)) == 1


def test_titular_justo_en_el_limite_no_avisa() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["titular"] = {"texto": "x" * 60, "noticia_id": "2026-S41-macro-01"}
    assert validacion.avisos_titular_largo(informe) == []


def test_limite_de_titular_es_configurable() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["titular"] = {"texto": "x" * 20, "noticia_id": "2026-S41-macro-01"}
    assert len(validacion.avisos_titular_largo(informe, limite_caracteres=10)) == 1


# --- validar_confianza_y_fuentes ------------------------------------------


def test_confirmado_con_una_fuente_nivel_1_no_da_error() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(
                confianza="confirmado",
                fuentes=[_fuente(url="https://www.ecb.europa.eu/x", nivel=1)],
            )
        ]
    )
    assert validacion.validar_confianza_y_fuentes(informe, FUENTES_CFG) == []


def test_confirmado_con_una_sola_fuente_nivel_2_da_error() -> None:
    informe = _informe_con(
        macro_global=[_noticia(confianza="confirmado", fuentes=[_fuente(nivel=2)])]
    )
    assert len(validacion.validar_confianza_y_fuentes(informe, FUENTES_CFG)) == 1


def test_confirmado_con_dos_fuentes_mismo_dominio_da_error() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(
                confianza="confirmado",
                fuentes=[
                    _fuente(url="https://www.reuters.com/a", nivel=2),
                    _fuente(url="https://www.reuters.com/b", nivel=2),
                ],
            )
        ]
    )
    assert len(validacion.validar_confianza_y_fuentes(informe, FUENTES_CFG)) == 1


def test_confirmado_con_dos_fuentes_dominios_distintos_no_da_error() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(
                confianza="confirmado",
                fuentes=[
                    _fuente(url="https://www.reuters.com/a", nivel=2),
                    _fuente(url="https://www.bloomberg.com/b", nivel=2),
                ],
            )
        ]
    )
    assert validacion.validar_confianza_y_fuentes(informe, FUENTES_CFG) == []


def test_confirmado_con_nivel_1_autodeclarado_pero_sin_catalogar_da_error() -> None:
    # El cambio clave de este bloque: antes, que la propia noticia se
    # autodeclarase nivel=1 bastaba para confirmar, sin comprobar nada
    # contra fuentes.yaml. Un dominio no catalogado ya no puede, por sí
    # solo, confirmar una noticia aunque diga nivel=1.
    informe = _informe_con(
        macro_global=[
            _noticia(
                confianza="confirmado",
                fuentes=[_fuente(url="https://www.mediodesconocido.com/a", nivel=1)],
            )
        ]
    )
    assert len(validacion.validar_confianza_y_fuentes(informe, FUENTES_CFG)) == 1


# --- validar_nivel_de_fuentes -----------------------------------------------


def test_nivel_declarado_coincide_con_el_catalogado_no_da_error() -> None:
    informe = _informe_con(
        macro_global=[_noticia(fuentes=[_fuente(url="https://www.reuters.com/a", nivel=2)])]
    )
    assert validacion.validar_nivel_de_fuentes(informe, FUENTES_CFG) == []


def test_nivel_declarado_distinto_del_catalogado_da_error() -> None:
    informe = _informe_con(
        macro_global=[_noticia(fuentes=[_fuente(url="https://www.reuters.com/a", nivel=1)])]
    )
    assert len(validacion.validar_nivel_de_fuentes(informe, FUENTES_CFG)) == 1


def test_nivel_declarado_para_dominio_no_catalogado_no_da_error() -> None:
    # Un dominio no catalogado no es error aquí: puede ser una fuente nueva
    # legítima (lo cubre, por separado, avisos_fuentes_no_catalogadas).
    informe = _informe_con(
        macro_global=[
            _noticia(fuentes=[_fuente(url="https://www.mediodesconocido.com/a", nivel=1)])
        ]
    )
    assert validacion.validar_nivel_de_fuentes(informe, FUENTES_CFG) == []


def test_nivel_catalogado_coincide_tambien_por_subdominio() -> None:
    informe = _informe_con(
        macro_global=[_noticia(fuentes=[_fuente(url="https://www.ecb.europa.eu/x", nivel=1)])]
    )
    assert validacion.validar_nivel_de_fuentes(informe, FUENTES_CFG) == []


def test_nivel_catalogado_elige_el_sufijo_mas_especifico() -> None:
    # "ecb.europa.eu" coincide con "europa.eu" (nivel 1, genérico) y con
    # "ecb.europa.eu" (nivel 3, exacto y más específico). Antes, recorrer
    # los niveles en orden (1, 2, 3...) devolvía el primero que coincidiera
    # — nivel 1 — sin importar que hubiera una coincidencia más específica
    # en un nivel posterior. Ahora debe ganar el sufijo más largo.
    cfg = {
        "niveles": {
            1: {"dominios": ["europa.eu"]},
            3: {"dominios": ["ecb.europa.eu"]},
        }
    }
    assert validacion._nivel_catalogado("ecb.europa.eu", cfg) == 3


def test_dominio_normaliza_mayusculas_y_quita_puerto() -> None:
    assert validacion._dominio("https://WWW.Reuters.com:443/a") == "reuters.com"


# --- avisos_fuentes_no_catalogadas -------------------------------------------


def test_dominio_catalogado_no_genera_aviso() -> None:
    informe = _informe_con(
        macro_global=[_noticia(fuentes=[_fuente(url="https://www.reuters.com/a", nivel=2)])]
    )
    assert validacion.avisos_fuentes_no_catalogadas(informe, FUENTES_CFG) == []


def test_dominio_no_catalogado_genera_aviso() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(fuentes=[_fuente(url="https://www.mediodesconocido.com/a", nivel=2)])
        ]
    )
    assert len(validacion.avisos_fuentes_no_catalogadas(informe, FUENTES_CFG)) == 1


def test_dominio_no_catalogado_repetido_avisa_una_sola_vez() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(
                id_="2026-S41-x-01",
                fuentes=[_fuente(url="https://www.mediodesconocido.com/a", nivel=2)],
            ),
            _noticia(
                id_="2026-S41-x-02",
                fuentes=[_fuente(url="https://www.mediodesconocido.com/b", nivel=2)],
            ),
        ]
    )
    assert len(validacion.avisos_fuentes_no_catalogadas(informe, FUENTES_CFG)) == 1


# --- validar_cifras ---------------------------------------------------------


def test_cifra_sin_ref_datos_no_se_comprueba() -> None:
    informe = _informe_con(
        macro_global=[_noticia(cifras=[{"valor": "2,9%", "ref_datos": None}])]
    )
    assert validacion.validar_cifras(informe, datos={}) == []


def test_cifra_con_ref_datos_inexistente_da_error() -> None:
    informe = _informe_con(
        macro_global=[_noticia(cifras=[{"valor": "2,9%", "ref_datos": "no_existe"}])]
    )
    assert len(validacion.validar_cifras(informe, datos={})) == 1


def test_cifra_que_coincide_dentro_de_tolerancia_no_da_error() -> None:
    informe = _informe_con(
        macro_global=[_noticia(cifras=[{"valor": "2,90%", "ref_datos": "ipc_espana"}])]
    )
    datos = {"ipc_espana": {"valor": 2.9}}
    assert validacion.validar_cifras(informe, datos) == []


def test_cifra_que_no_coincide_da_error() -> None:
    informe = _informe_con(
        macro_global=[_noticia(cifras=[{"valor": "3,5%", "ref_datos": "ipc_espana"}])]
    )
    datos = {"ipc_espana": {"valor": 2.9}}
    assert len(validacion.validar_cifras(informe, datos)) == 1


# --- validar_fechas_fuente ---------------------------------------------------


def test_fuente_dentro_del_periodo_no_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(fuentes=[_fuente(fecha="2026-10-07")])])
    assert validacion.validar_fechas_fuente(informe) == []


def test_fuente_antes_del_periodo_pero_reciente_no_da_error() -> None:
    # El periodo del informe mínimo es 2026-10-05 a 2026-10-11. Una fuente
    # del 2026-10-02 es anterior al inicio del periodo, pero solo tiene 9
    # días de antigüedad respecto al cierre (10-11) — dentro del límite de
    # 10 días de prompts/redactor.md, así que no debería bloquear. Este es
    # justo el caso real que encontró la prueba en local (sección 13).
    informe = _informe_con(macro_global=[_noticia(fuentes=[_fuente(fecha="2026-10-02")])])
    assert validacion.validar_fechas_fuente(informe) == []


def test_fuente_demasiado_antigua_sin_marcar_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(fuentes=[_fuente(fecha="2026-01-01")])])
    assert len(validacion.validar_fechas_fuente(informe)) == 1


def test_fuente_demasiado_antigua_marcada_como_historica_no_da_error() -> None:
    fuente = _fuente(fecha="2026-01-01")
    fuente["contexto_historico"] = True
    informe = _informe_con(macro_global=[_noticia(fuentes=[fuente])])
    assert validacion.validar_fechas_fuente(informe) == []


def test_fuente_con_fecha_futura_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(fuentes=[_fuente(fecha="2026-10-12")])])
    assert len(validacion.validar_fechas_fuente(informe)) == 1


def test_antiguedad_maxima_dias_es_configurable() -> None:
    informe = _informe_con(macro_global=[_noticia(fuentes=[_fuente(fecha="2026-10-02")])])
    # Con un límite de solo 3 días, esa misma fuente del 10-02 ya no entra.
    assert len(validacion.validar_fechas_fuente(informe, antiguedad_maxima_dias=3)) == 1


# --- validar_palabras_prohibidas --------------------------------------------

PALABRAS = {"sensacionalismo": ["pánico"], "recomendacion": ["deberías comprar"]}


def test_texto_limpio_no_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(texto="Todo normal esta semana.")])
    assert validacion.validar_palabras_prohibidas(informe, PALABRAS) == []


def test_texto_con_palabra_prohibida_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(texto="Cunde el pánico en los mercados.")])
    assert len(validacion.validar_palabras_prohibidas(informe, PALABRAS)) == 1


def test_palabra_prohibida_en_titular_da_error() -> None:
    # Antes solo se miraba título/texto/por_qué_importa de cada noticia:
    # titular, lo_esencial, concepto_semana y perspectiva_largo_plazo
    # pasaban sin comprobar.
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["titular"] = {"texto": "Cunde el pánico en Wall Street", "noticia_id": "2026-S41-macro-01"}
    assert len(validacion.validar_palabras_prohibidas(informe, PALABRAS)) == 1


def test_palabra_prohibida_en_lo_esencial_da_error() -> None:
    informe = _informe_con(lo_esencial=["Cunde el pánico en los mercados."])
    assert len(validacion.validar_palabras_prohibidas(informe, PALABRAS)) == 1


def test_palabra_prohibida_en_concepto_semana_da_error() -> None:
    informe = _informe_con()
    informe["concepto_semana"] = {
        "id": "x",
        "titulo": "Pánico bursátil",
        "texto": "Explicación.",
    }
    assert len(validacion.validar_palabras_prohibidas(informe, PALABRAS)) == 1


def test_palabra_prohibida_en_perspectiva_largo_plazo_da_error() -> None:
    informe = _informe_con()
    informe["perspectiva_largo_plazo"] = {
        "estructural": ["Cunde el pánico estructural."],
        "ruido": [],
    }
    assert len(validacion.validar_palabras_prohibidas(informe, PALABRAS)) == 1


def test_palabra_prohibida_sin_tildes_igualmente_se_detecta() -> None:
    informe = _informe_con(macro_global=[_noticia(texto="Cunde el panico en los mercados.")])
    assert len(validacion.validar_palabras_prohibidas(informe, PALABRAS)) == 1


def test_palabra_prohibida_dentro_de_otra_palabra_no_da_error() -> None:
    # Límite de palabra: "panico" no debería saltar dentro de otra palabra
    # que simplemente la contenga como subcadena.
    informe = _informe_con(macro_global=[_noticia(texto="Esto no es paniconomía real.")])
    assert validacion.validar_palabras_prohibidas(informe, PALABRAS) == []


def test_entrada_marcada_como_raiz_coincide_por_subcadena() -> None:
    palabras_raiz = {"sensacionalismo": [{"raiz": "hund"}]}
    informe = _informe_con(macro_global=[_noticia(texto="El mercado se hundió ayer.")])
    assert len(validacion.validar_palabras_prohibidas(informe, palabras_raiz)) == 1


# --- avisos_limite_palabras --------------------------------------------------

MODULOS_CFG = [{"id": "eeuu", "limite_palabras": 5}]


def test_modulo_bajo_el_limite_no_avisa() -> None:
    informe = _informe_minimo_valido()
    informe["modulos"]["eeuu"] = {
        "sin_novedades": False,
        "noticias": [_noticia(titulo="corto", texto="", por_que_importa="")],
    }
    assert validacion.avisos_limite_palabras(informe, MODULOS_CFG) == []


def test_modulo_supera_el_limite_avisa() -> None:
    informe = _informe_minimo_valido()
    informe["modulos"]["eeuu"] = {
        "sin_novedades": False,
        "noticias": [
            _noticia(titulo="una frase con bastantes palabras de más", texto="", por_que_importa="")
        ],
    }
    assert len(validacion.avisos_limite_palabras(informe, MODULOS_CFG)) == 1


def test_modulo_sin_novedades_no_se_cuenta() -> None:
    informe = _informe_minimo_valido()  # todos los módulos ya vienen con sin_novedades=True
    assert validacion.avisos_limite_palabras(informe, MODULOS_CFG) == []


# --- avisos_concepto_semana_largo --------------------------------------------


def test_concepto_semana_corto_no_avisa() -> None:
    informe = _informe_minimo_valido()  # el concepto de ejemplo tiene 9 palabras
    assert validacion.avisos_concepto_semana_largo(informe) == []


def test_concepto_semana_largo_avisa() -> None:
    informe = _informe_minimo_valido()
    informe["concepto_semana"]["texto"] = " ".join(["palabra"] * 121)
    assert len(validacion.avisos_concepto_semana_largo(informe)) == 1


def test_limite_de_concepto_semana_es_configurable() -> None:
    informe = _informe_minimo_valido()
    informe["concepto_semana"]["texto"] = " ".join(["palabra"] * 10)
    assert len(validacion.avisos_concepto_semana_largo(informe, limite_palabras=5)) == 1


# --- avisos_concentracion_medios --------------------------------------------


def test_fuentes_repartidas_no_avisa() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(fuentes=[_fuente(medio="Reuters"), _fuente(medio="Bloomberg")])
        ]
    )
    assert validacion.avisos_concentracion_medios(informe) == []


def test_un_medio_mayoritario_avisa() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(
                fuentes=[_fuente(medio="Reuters"), _fuente(medio="Reuters"), _fuente(medio="BCE")]
            )
        ]
    )
    assert len(validacion.avisos_concentracion_medios(informe)) == 1


def test_concentracion_es_por_noticia_no_por_informe() -> None:
    # CLAUDE.md dice "more than 50% of a story's sources from a single
    # outlet" — por noticia, no por el conjunto del informe. Dos noticias,
    # cada una con sus fuentes repartidas al 50/50, no deberían avisar aunque
    # un medio sea mayoritario al sumar las de todo el informe.
    informe = _informe_con(
        macro_global=[
            _noticia(
                id_="2026-S41-macro-01",
                fuentes=[_fuente(medio="Reuters"), _fuente(medio="BCE")],
            ),
            _noticia(
                id_="2026-S41-macro-02",
                fuentes=[_fuente(medio="Reuters"), _fuente(medio="FMI")],
            ),
        ]
    )
    assert validacion.avisos_concentracion_medios(informe) == []


# --- avisos_modulo_sin_fuentes_fiables ---------------------------------------


def test_modulo_con_fuente_nivel_2_no_avisa() -> None:
    informe = _informe_minimo_valido()
    informe["modulos"]["eeuu"] = {
        "sin_novedades": False,
        "noticias": [_noticia(fuentes=[_fuente(nivel=2)])],
    }
    assert validacion.avisos_modulo_sin_fuentes_fiables(informe) == []


def test_modulo_solo_con_fuentes_nivel_3_avisa() -> None:
    informe = _informe_minimo_valido()
    informe["modulos"]["eeuu"] = {
        "sin_novedades": False,
        "noticias": [_noticia(fuentes=[_fuente(nivel=3)])],
    }
    assert len(validacion.avisos_modulo_sin_fuentes_fiables(informe)) == 1


# --- avisos_cifras_sin_verificar ---------------------------------------------


def test_sin_cifras_sueltas_no_avisa() -> None:
    informe = _informe_con(
        macro_global=[_noticia(cifras=[{"valor": "2,9%", "ref_datos": "ipc_espana"}])]
    )
    assert validacion.avisos_cifras_sin_verificar(informe) == []


def test_cifras_sin_ref_datos_se_cuentan() -> None:
    informe = _informe_con(
        macro_global=[
            _noticia(
                id_="2026-S41-macro-01",
                cifras=[{"valor": "3,8%", "ref_datos": None}],
            ),
            _noticia(
                id_="2026-S41-macro-02",
                cifras=[{"valor": "1,2%", "ref_datos": None}],
            ),
        ]
    )
    avisos = validacion.avisos_cifras_sin_verificar(informe)
    assert len(avisos) == 1
    assert "2 cifra" in avisos[0]


# --- validar_ids_de_noticia_unicos -------------------------------------------


def test_ids_unicos_no_da_error() -> None:
    informe = _informe_con(
        macro_global=[_noticia(id_="2026-S41-macro-01"), _noticia(id_="2026-S41-macro-02")]
    )
    assert validacion.validar_ids_de_noticia_unicos(informe) == []


def test_id_duplicado_entre_modulos_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-x-01")])
    informe["modulos"]["eeuu"] = {
        "sin_novedades": False,
        "noticias": [_noticia(id_="2026-S41-x-01")],
    }
    assert len(validacion.validar_ids_de_noticia_unicos(informe)) == 1


# --- validar_periodo_coherente_con_semana ------------------------------------


def test_periodo_coherente_con_semana_no_da_error() -> None:
    informe = _informe_minimo_valido()  # semana 2026-S41, periodo 2026-10-05 a 2026-10-11
    assert validacion.validar_periodo_coherente_con_semana(informe) == []


def test_periodo_que_no_coincide_con_la_semana_da_error() -> None:
    informe = _informe_minimo_valido()
    informe["periodo"] = {"inicio": "2026-10-12", "fin": "2026-10-18"}  # es la semana 2026-S42
    assert len(validacion.validar_periodo_coherente_con_semana(informe)) == 1


# --- validar_cambios_verificador_referencian_noticias_reales -----------------


def test_cambio_verificador_con_noticia_real_no_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["cambios_verificador"] = [
        {"noticia_id": "2026-S41-macro-01", "cambio": "x", "motivo": "y"}
    ]
    assert validacion.validar_cambios_verificador_referencian_noticias_reales(informe) == []


def test_cambio_verificador_con_noticia_inexistente_da_error() -> None:
    informe = _informe_con(macro_global=[_noticia(id_="2026-S41-macro-01")])
    informe["cambios_verificador"] = [{"noticia_id": "no-existe", "cambio": "x", "motivo": "y"}]
    assert len(validacion.validar_cambios_verificador_referencian_noticias_reales(informe)) == 1
