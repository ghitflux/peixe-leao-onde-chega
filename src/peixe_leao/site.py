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


ESTIMADORES_TRADUZIDOS = {
    "Média: distância contra ano (linha de base)": {"pt": "Média: distância × ano", "en": "Mean: distance on year", "es": "Media: distancia × año"},
    "Média: ano contra distância": {"pt": "Média: ano × distância", "en": "Mean: year on distance", "es": "Media: año × distancia"},
    "Média: ano contra distância, com esforço": {"pt": "Média com esforço", "en": "Mean with effort", "es": "Media con esfuerzo"},
    "Frente: quantil 0,90 da distância": {"pt": "Quantil 0,90 da distância", "en": "0.90 quantile of distance", "es": "Cuantil 0,90 de la distancia"},
    "Frente: quantil 0,10 do ano": {"pt": "Quantil 0,10 do ano", "en": "0.10 quantile of year", "es": "Cuantil 0,10 del año"},
    "Frente: envelope dos recordes": {"pt": "Envelope dos recordes", "en": "Record envelope", "es": "Envolvente de récords"},
}
IDIOMAS = ("pt", "en", "es")


def _tres(funcao) -> dict:
    """Monta o texto nos três idiomas a partir de uma função do idioma."""
    return {idioma: funcao(idioma) for idioma in IDIOMAS}


def _celula(lat_sul: int, lon_oeste: int, idioma: str) -> str:
    """Rótulo curto da célula pelo canto sudoeste: '6°S 36°O' (em inglês, '6°S 36°W')."""
    ns = "N" if lat_sul >= 0 else "S"
    leste, oeste = {"pt": ("L", "O"), "en": ("E", "W"), "es": ("E", "O")}[idioma]
    lo = leste if lon_oeste >= 0 else oeste
    return f"{abs(int(lat_sul))}°{ns} {abs(int(lon_oeste))}°{lo}"


def graficos_extras(r: dict, pontos_da_frente: list[list[float]]) -> list[dict]:
    """Os outros achados do README como dados, para o site desenhar. Do mais importante para o menos.

    `pontos_da_frente` são os pares [ano, distância em km] das células do Atlântico usadas na velocidade.
    """
    curvas = r["validacao"]["atlantico_2010"]["curvas"]

    def serie(coluna: str) -> list:
        return [[linha["ano"], round(float(linha[coluna]))] for linha in curvas]

    # 1. a frente depois de 2010: o salto pela foz do Amazonas
    salto = max(range(1, len(curvas)), key=lambda k: curvas[k]["observado_frente_km"] - curvas[k - 1]["observado_frente_km"])
    ano_salto = curvas[salto]["ano"]
    antes, depois, previsto = curvas[salto - 1]["observado_frente_km"], curvas[salto]["observado_frente_km"], curvas[salto]["modelo_frente_km"]
    frente_validacao = {
        "tipo": "linhas",
        "titulo": {
            "pt": f"Em {ano_salto} a frente saltou de {_n(antes, 0, 'pt')} para {_n(depois, 0, 'pt')} km; o modelo previa {_n(previsto, 0, 'pt')}",
            "en": f"In {ano_salto} the front jumped from {_n(antes, 0, 'en')} to {_n(depois, 0, 'en')} km; the model expected {_n(previsto, 0, 'en')}",
            "es": f"En {ano_salto} el frente saltó de {_n(antes, 0, 'es')} a {_n(depois, 0, 'es')} km; el modelo preveía {_n(previsto, 0, 'es')}",
        },
        "leitura": {
            "pt": "Distância da frente ao ponto de introdução, pelo mar, com o modelo ajustado até 2010. A frente real ficou parada por anos e depois cruzou a foz do Amazonas de uma vez; o modelo previa um avanço contínuo.",
            "en": "Sea distance from the front to the introduction point, with the model fitted through 2010. The real front stalled for years and then crossed the Amazon mouth in one step; the model expected a steady advance.",
            "es": "Distancia del frente al punto de introducción, por mar, con el modelo ajustado hasta 2010. El frente real se detuvo durante años y luego cruzó la desembocadura del Amazonas de una vez; el modelo preveía un avance continuo.",
        },
        "eixo_x": {"pt": "Ano", "en": "Year", "es": "Año"},
        "eixo_y": {"pt": "Distância da frente (km)", "en": "Front distance (km)", "es": "Distancia del frente (km)"},
        "formato_x": "numero",
        "formato_y": "numero",
        "series": [
            {"nome": {"pt": "Modelo de espalhamento", "en": "Spread model", "es": "Modelo de dispersión"}, "papel": "principal", "pontos": serie("modelo_frente_km")},
            {"nome": {"pt": "Velocidade constante", "en": "Constant speed", "es": "Velocidad constante"}, "papel": "base", "pontos": serie("velocidade_constante_frente_km")},
            {"nome": {"pt": "O que aconteceu", "en": "What happened", "es": "Lo que ocurrió"}, "papel": "neutro", "pontos": serie("observado_frente_km")},
        ],
        "faixa": {"serie": 0, "inferior": serie("modelo_frente_km_p05"), "superior": serie("modelo_frente_km_p95")},
    }

    # 2. a previsão (no lugar do mapa): as células do Atlântico com maior probabilidade
    topo = r["previsao_maiores_probabilidades"]["atlantico"][:10]
    rotulos = _tres(lambda idioma: [_celula(c["lat_sul"], c["lon_oeste"], idioma) for c in topo])
    maior = topo[0]["prob_10_anos"]
    previsao = {
        "tipo": "barras",
        "titulo": {
            "pt": f"A célula mais provável tem {_pct(maior, 'pt')} de chance de ganhar registro em dez anos",
            "en": f"The most likely cell has a {_pct(maior, 'en')} chance of a first record within ten years",
            "es": f"La celda más probable tiene {_pct(maior, 'es')} de probabilidad de registro en diez años",
        },
        "leitura": {
            "pt": "As dez células de 1° do Atlântico oeste ainda sem registro com maior probabilidade de primeiro registro, pelo canto sudoeste. Quase todas ficam no Nordeste do Brasil. É exercício de modelagem, não previsão oficial.",
            "en": "The ten unrecorded 1° cells of the western Atlantic with the highest probability of a first record, labelled by their south-west corner. Nearly all lie along northeastern Brazil. A modelling exercise, not an official forecast.",
            "es": "Las diez celdas de 1° del Atlántico occidental aún sin registro con mayor probabilidad de primer registro, por su esquina suroeste. Casi todas están en el nordeste de Brasil. Es un ejercicio de modelado, no un pronóstico oficial.",
        },
        "eixo_x": {"pt": "Célula (canto sudoeste)", "en": "Cell (south-west corner)", "es": "Celda (esquina suroeste)"},
        "eixo_y": {"pt": "Probabilidade de primeiro registro", "en": "Probability of a first record", "es": "Probabilidad de primer registro"},
        "formato_x": "numero",
        "formato_y": "percentual",
        "series": [
            {"nome": {"pt": "Em 10 anos", "en": "Within 10 years", "es": "En 10 años"}, "papel": "principal", "rotulos": rotulos, "pontos": [[rotulos["pt"][k], c["prob_10_anos"]] for k, c in enumerate(topo)]},
            {"nome": {"pt": "Em 5 anos", "en": "Within 5 years", "es": "En 5 años"}, "papel": "neutro", "rotulos": rotulos, "pontos": [[rotulos["pt"][k], c["prob_5_anos"]] for k, c in enumerate(topo)]},
        ],
    }

    # 3. o erro de cada estimador de velocidade na invasão simulada
    cenarios = list(dict.fromkeys(linha["cenario"] for linha in r["velocidade"]["simulacao"]))
    erro = {(linha["cenario"], linha["estimador"]): linha["erro_relativo"] for linha in r["velocidade"]["simulacao"]}
    nomes = list(ESTIMADORES_TRADUZIDOS)
    rotulos_est = _tres(lambda idioma: [ESTIMADORES_TRADUZIDOS[nome][idioma] for nome in nomes])
    erro_media = abs(erro[(cenarios[-1], nomes[0])])
    erro_quantil = abs(erro[(cenarios[-1], "Frente: quantil 0,10 do ano")])

    def barras(cenario: str) -> list:
        return [[rotulos_est["pt"][k], round(erro[(cenario, nome)], 4)] for k, nome in enumerate(nomes)]

    estimadores = {
        "tipo": "barras",
        "titulo": {
            "pt": f"Com detecção imperfeita, a média erra a velocidade em {_pct(erro_media, 'pt')}; o quantil do ano, em {_n(erro_quantil * 100, 1, 'pt')}%",
            "en": f"With imperfect detection the mean misses the speed by {_pct(erro_media, 'en')}; the year quantile by {_n(erro_quantil * 100, 1, 'en')}%",
            "es": f"Con detección imperfecta, la media falla la velocidad en {_pct(erro_media, 'es')}; el cuantil del año, en {_n(erro_quantil * 100, 1, 'es')}%",
        },
        "leitura": {
            "pt": "Erro médio de cada estimador numa invasão simulada com frente de 250 km por ano, em 200 simulações. Abaixo de zero, o estimador subestima a velocidade. Os de média erram mais quando há menos observadores longe da origem.",
            "en": "Mean error of each estimator on a simulated invasion with a 250 km/yr front, over 200 runs. Below zero the estimator underestimates speed. The mean-based ones get worse when observers thin out far from the origin.",
            "es": "Error medio de cada estimador en una invasión simulada con un frente de 250 km por año, en 200 simulaciones. Por debajo de cero, el estimador subestima la velocidad. Los de media fallan más cuando hay menos observadores lejos del origen.",
        },
        "eixo_x": {"pt": "Estimador", "en": "Estimator", "es": "Estimador"},
        "eixo_y": {"pt": "Erro relativo na velocidade", "en": "Relative error in speed", "es": "Error relativo en la velocidad"},
        "formato_x": "numero",
        "formato_y": "percentual",
        "series": [
            {"nome": {"pt": "Menos esforço longe da origem", "en": "Less effort far from the origin", "es": "Menos esfuerzo lejos del origen"}, "papel": "principal", "rotulos": rotulos_est, "pontos": barras(cenarios[-1])},
            {"nome": {"pt": "Detecção imperfeita, esforço uniforme", "en": "Imperfect detection, even effort", "es": "Detección imperfecta, esfuerzo uniforme"}, "papel": "neutro", "rotulos": rotulos_est, "pontos": barras(cenarios[-2])},
        ],
    }

    # 4. distância contra ano do primeiro registro, célula a célula (Atlântico)
    from peixe_leao import frente  # import local: o resto do módulo só formata texto

    anos = [p[0] for p in pontos_da_frente]
    distancias = [p[1] for p in pontos_da_frente]
    anos_recorde, recordes = frente.envelope(distancias, anos)
    v = r["velocidade"]["dados_reais"]["atlantico"]
    media = v["Média: distância contra ano (linha de base)"]["km_por_ano"]
    frentes = [v[nome]["km_por_ano"] for nome in nomes[3:]]
    nuvem = {
        "tipo": "pontos",
        "titulo": {
            "pt": f"No Atlântico, a média dá {_n(media, 0, 'pt')} km por ano; os estimadores de frente, de {_n(min(frentes), 0, 'pt')} a {_n(max(frentes), 0, 'pt')}",
            "en": f"In the Atlantic the mean gives {_n(media, 0, 'en')} km/yr; front estimators give {_n(min(frentes), 0, 'en')} to {_n(max(frentes), 0, 'en')}",
            "es": f"En el Atlántico, la media da {_n(media, 0, 'es')} km por año; los estimadores de frente, de {_n(min(frentes), 0, 'es')} a {_n(max(frentes), 0, 'es')}",
        },
        "leitura": {
            "pt": "Cada ponto é uma célula de 1°: o ano do primeiro registro e a distância pelo mar até a Flórida. Os recordes de distância desenham a frente; a nuvem embaixo são as células ocupadas depois que a frente passou, e é ela que puxa a média para baixo.",
            "en": "Each dot is a 1° cell: the year of its first record and its sea distance to Florida. The distance records trace the front; the cloud below is cells filled in after the front passed, which is what drags the mean down.",
            "es": "Cada punto es una celda de 1°: el año del primer registro y la distancia por mar hasta Florida. Los récords de distancia dibujan el frente; la nube de abajo son las celdas ocupadas después de que pasó el frente, y es la que arrastra la media hacia abajo.",
        },
        "eixo_x": {"pt": "Ano do primeiro registro", "en": "Year of first record", "es": "Año del primer registro"},
        "eixo_y": {"pt": "Distância até a introdução (km)", "en": "Distance to introduction (km)", "es": "Distancia a la introducción (km)"},
        "formato_x": "numero",
        "formato_y": "numero",
        "series": [
            {"nome": {"pt": "Recordes de distância (a frente)", "en": "Distance records (the front)", "es": "Récords de distancia (el frente)"}, "papel": "principal", "pontos": [[int(a), round(float(d))] for a, d in zip(anos_recorde, recordes)]},
            {"nome": {"pt": "Células", "en": "Cells", "es": "Celdas"}, "papel": "neutro", "pontos": [[int(a), round(float(d))] for a, d in pontos_da_frente[:300]]},
        ],
    }

    # 5. a área ocupada ao longo do tempo (resume o mapa do primeiro registro)
    atl, med = r["teatros"]["atlantico"], r["teatros"]["mediterraneo"]
    area = {
        "tipo": "linhas",
        "titulo": {
            "pt": f"O auge foi em {atl['ano_de_pico']} no Atlântico ({atl['novas_celulas_no_pico']} células novas no ano) e em {med['ano_de_pico']} no Mediterrâneo",
            "en": f"Peak year: {atl['ano_de_pico']} in the Atlantic ({atl['novas_celulas_no_pico']} new cells) and {med['ano_de_pico']} in the Mediterranean",
            "es": f"El auge fue en {atl['ano_de_pico']} en el Atlántico ({atl['novas_celulas_no_pico']} celdas nuevas) y en {med['ano_de_pico']} en el Mediterráneo",
        },
        "leitura": {
            "pt": "Células de 1° da plataforma com registro corroborado de peixe-leão, acumulado por ano. Nos dois mares a invasão passou anos quase parada antes de disparar. No Mediterrâneo, registro anterior a 2012 não data a chegada.",
            "en": "One-degree shelf cells with a corroborated lionfish record, cumulative by year. In both seas the invasion sat nearly still for years before taking off. In the Mediterranean, records before 2012 are not used to date arrival.",
            "es": "Celdas de 1° de la plataforma con registro corroborado de pez león, acumulado por año. En ambos mares la invasión estuvo casi detenida durante años antes de dispararse. En el Mediterráneo, un registro anterior a 2012 no fecha la llegada.",
        },
        "eixo_x": {"pt": "Ano", "en": "Year", "es": "Año"},
        "eixo_y": {"pt": "Células de 1° com registro", "en": "1° cells with a record", "es": "Celdas de 1° con registro"},
        "formato_x": "numero",
        "formato_y": "numero",
        "series": [
            {"nome": {"pt": "Atlântico oeste", "en": "Western Atlantic", "es": "Atlántico occidental"}, "papel": "principal", "pontos": [[x["ano"], x["celulas_com_registro"]] for x in atl["area_e_frente"]]},
            {"nome": {"pt": "Mediterrâneo", "en": "Mediterranean", "es": "Mediterráneo"}, "papel": "alternativa", "pontos": [[x["ano"], x["celulas_com_registro"]] for x in med["area_e_frente"]]},
        ],
    }
    return [frente_validacao, previsao, estimadores, nuvem, area]


def bloco(r: dict, pontos_da_frente: list[list[float]] | None = None) -> dict:
    """Bloco do site. Com `pontos_da_frente`, inclui também `graficos_extras`."""
    principal = _bloco_principal(r)
    if pontos_da_frente is not None:
        principal["graficos_extras"] = graficos_extras(r, pontos_da_frente)
    return principal


def _bloco_principal(r: dict) -> dict:
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
