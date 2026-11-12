"""Bloco `para_o_site` do resultados.json e os títulos das figuras que dependem dos números."""

from __future__ import annotations


def _n(valor: float, casas: int, idioma: str) -> str:
    """Número no formato do idioma: vírgula decimal em pt e es, ponto em en; milhar com ponto ou vírgula."""
    texto = f"{valor:,.{casas}f}"
    if idioma == "en":
        return texto
    return texto.replace(",", " ").replace(".", ",").replace(" ", ".")


def _pct(valor: float, idioma: str) -> str:
    return f"{_n(valor * 100, 0, idioma)}%"


def numeros(r: dict) -> dict:
    """Os números que o texto usa, tirados do resultado, num só lugar."""
    v10 = r["validacao"]["atlantico_2010"]
    brasil = v10["regioes"]["Costa brasileira"]
    h5 = v10["horizontes"]["5"]
    curva = v10["curvas"][-1]
    previsao = r["previsao"]["atlantico"]["regioes"]["Costa brasileira"]
    topo = r["previsao_maiores_probabilidades"]["atlantico"][0]
    limpo = sum(r["coleta"]["registros_limpos_por_teatro"].values())
    celulas = sum(t["celulas_de_plataforma"] for t in r["teatros"].values())
    return {
        "brasil_mediana": brasil["ano_mediano_previsto"],
        "brasil_p05": brasil["ano_previsto_p05"],
        "brasil_p95": brasil["ano_previsto_p95"],
        "brasil_observado": brasil["ano_observado_do_primeiro_registro"],
        "brasil_velocidade": brasil["ano_velocidade_constante"],
        "brasil_vizinha": brasil["ano_vizinha"],
        "auc_modelo": h5["modelo"]["auc"],
        "auc_vizinha": h5["vizinha"]["auc"],
        "brier_modelo": h5["modelo"]["brier"],
        "brier_vizinha": h5["vizinha"]["brier"],
        "celulas_previstas_final": curva["modelo_celulas"],
        "celulas_previstas_p05": curva["modelo_celulas_p05"],
        "celulas_previstas_p95": curva["modelo_celulas_p95"],
        "celulas_observadas_final": curva["observado_celulas"],
        "celulas_velocidade_final": curva["velocidade_constante_celulas"],
        "celulas_vizinha_final": curva["vizinha_celulas"],
        "ano_final": curva["ano"],
        "topo_prob": topo["prob_10_anos"],
        "topo_lat": topo["lat_sul"],
        "brasil_novas_10": previsao["novas_celulas_esperadas_em_10_anos"],
        "brasil_sem_registro": previsao["celulas_sem_registro"],
        "registros": limpo,
        "celulas": celulas,
    }


def titulo_da_validacao(r: dict) -> str:
    n = numeros(r)
    return (
        f"Com dados até 2010, o modelo previa {_n(n['celulas_previstas_final'], 0, 'pt')} células ocupadas em {n['ano_final']}; "
        f"foram {n['celulas_observadas_final']}"
    )


def titulo_da_previsao(r: dict) -> str:
    n = numeros(r)
    return f"Até 2035, a chegada mais provável é no Nordeste do Brasil: até {_pct(n['topo_prob'], 'pt')} por célula"


def bloco(r: dict) -> dict:
    n = numeros(r)
    v10 = r["validacao"]["atlantico_2010"]
    curvas = v10["curvas"]

    def pontos(coluna: str) -> list:
        return [[linha["ano"], round(float(linha[coluna]), 1)] for linha in curvas]

    med, p05, p95, obs = (int(n[k]) for k in ("brasil_mediana", "brasil_p05", "brasil_p95", "brasil_observado"))
    texto = {}
    for idioma in ("pt", "en", "es"):
        texto[idioma] = {
            "previstas": _n(n["celulas_previstas_final"], 0, idioma),
            "auc_m": _n(n["auc_modelo"], 2, idioma),
            "auc_v": _n(n["auc_vizinha"], 2, idioma),
            "topo": _pct(n["topo_prob"], idioma),
            "registros": _n(n["registros"], 0, idioma),
            "celulas": _n(n["celulas"], 0, idioma),
        }
    pt, en, es = texto["pt"], texto["en"], texto["es"]
    return {
        "numero_chave": {"pt": f"{med} × {obs}", "en": f"{med} vs {obs}", "es": f"{med} × {obs}"},
        "pergunta": {
            "pt": "Onde o peixe-leão vai chegar a seguir, e quando?",
            "en": "Where will the lionfish show up next, and when?",
            "es": "¿Adónde llegará el pez león a continuación, y cuándo?",
        },
        "resultado": {
            "pt": (
                f"Um modelo de espalhamento ajustado só com os registros até 2010 previa o primeiro registro no Brasil para {med} "
                f"(faixa de 90%: {p05} a {p95}); ele veio em {obs}. Para os próximos dez anos, a chegada mais provável é no Nordeste "
                f"do Brasil, com até {pt['topo']} de probabilidade por célula de 1°."
            ),
            "en": (
                f"A spread model fitted only to records through 2010 put the first Brazilian record in {med} "
                f"(90% range: {p05} to {p95}); it came in {obs}. Over the next ten years the most likely arrivals are along "
                f"northeastern Brazil, with up to {en['topo']} probability per 1° cell."
            ),
            "es": (
                f"Un modelo de dispersión ajustado solo con los registros hasta 2010 preveía el primer registro en Brasil para {med} "
                f"(rango del 90%: {p05} a {p95}); llegó en {obs}. Para los próximos diez años, la llegada más probable está en el "
                f"nordeste de Brasil, con hasta {es['topo']} de probabilidad por celda de 1°."
            ),
        },
        "detalhe": {
            "pt": (
                f"Nesse teste o modelo acerta quanto a invasão cresce ({pt['previstas']} células previstas para {n['ano_final']}, "
                f"{n['celulas_observadas_final']} observadas; a regra da célula vizinha previa {n['celulas_vizinha_final']}), mas "
                f"empata com ela na ordem das células (AUC de {pt['auc_m']} contra {pt['auc_v']}). No gráfico, as células de "
                f"plataforma com registro depois de 2010: o previsto por cada método e o que aconteceu."
            ),
            "en": (
                f"In that test the model gets the size of the invasion right ({en['previstas']} cells predicted for {n['ano_final']}, "
                f"{n['celulas_observadas_final']} observed; the nearest-neighbour rule predicted {n['celulas_vizinha_final']}), but "
                f"only ties with that rule at ranking which cells come next (AUC {en['auc_m']} vs {en['auc_v']}). The chart shows "
                f"shelf cells with a record after 2010: what each method predicted and what happened."
            ),
            "es": (
                f"En esa prueba el modelo acierta cuánto crece la invasión ({es['previstas']} celdas previstas para {n['ano_final']}, "
                f"{n['celulas_observadas_final']} observadas; la regla de la celda vecina preveía {n['celulas_vizinha_final']}), pero "
                f"empata con ella al ordenar las celdas (AUC de {es['auc_m']} frente a {es['auc_v']}). En el gráfico, las celdas de "
                f"plataforma con registro después de 2010: lo previsto por cada método y lo que ocurrió."
            ),
        },
        "dados": {
            "pt": f"{pt['registros']} registros públicos de USGS NAS, GBIF e OBIS depois da limpeza, em {pt['celulas']} células de 1° da plataforma do Atlântico oeste e do Mediterrâneo, de 1985 a 2025.",
            "en": f"{en['registros']} public records from USGS NAS, GBIF and OBIS after cleaning, on {en['celulas']} one-degree shelf cells of the western Atlantic and the Mediterranean, 1985 to 2025.",
            "es": f"{es['registros']} registros públicos de USGS NAS, GBIF y OBIS tras la limpieza, en {es['celulas']} celdas de 1° de la plataforma del Atlántico occidental y del Mediterráneo, de 1985 a 2025.",
        },
        "etiquetas": ["invasão biológica", "modelo de espalhamento", "validação no tempo", "dados de ocorrência", "NumPy/SciPy"],
        "grafico": {
            "tipo": "linhas",
            "titulo": {
                "pt": "Células ocupadas depois de 2010: previsto e realizado (Atlântico oeste)",
                "en": "Occupied cells after 2010: predicted vs observed (western Atlantic)",
                "es": "Celdas ocupadas después de 2010: previsto y observado (Atlántico occidental)",
            },
            "eixo_x": {"pt": "Ano", "en": "Year", "es": "Año"},
            "eixo_y": {"pt": "Células de 1° com registro", "en": "1° cells with a record", "es": "Celdas de 1° con registro"},
            "formato_x": "numero",
            "formato_y": "numero",
            "series": [
                {"nome": {"pt": "Modelo de espalhamento", "en": "Spread model", "es": "Modelo de dispersión"}, "papel": "principal", "pontos": pontos("modelo_celulas")},
                {"nome": {"pt": "Velocidade constante", "en": "Constant speed", "es": "Velocidad constante"}, "papel": "base", "pontos": pontos("velocidade_constante_celulas")},
                {"nome": {"pt": "Célula vizinha", "en": "Nearest neighbour", "es": "Celda vecina"}, "papel": "alternativa", "pontos": pontos("vizinha_celulas")},
                {"nome": {"pt": "O que aconteceu", "en": "What happened", "es": "Lo que ocurrió"}, "papel": "neutro", "pontos": pontos("observado_celulas")},
            ],
            "faixa": {"serie": 0, "inferior": pontos("modelo_celulas_p05"), "superior": pontos("modelo_celulas_p95")},
        },
    }
