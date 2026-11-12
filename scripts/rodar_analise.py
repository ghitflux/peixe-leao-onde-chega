"""Roda a análise completa a partir de data/ e grava reports/resultados.json, as figuras e o CSV reutilizável."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from peixe_leao import analise, dados, frente, graficos, site

SAIDA = Path("reports")
FIGURAS = SAIDA / "figuras"


def _registros(tabela: pd.DataFrame) -> list[dict]:
    return json.loads(tabela.to_json(orient="records", force_ascii=False))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    inicio = time.time()
    FIGURAS.mkdir(parents=True, exist_ok=True)
    base = dados.carregar()
    teatros = {chave: analise.montar_teatro(base, chave) for chave in ("atlantico", "mediterraneo")}

    # 1. reconstrução da frente
    curvas = {chave: analise.area_e_frente(t) for chave, t in teatros.items()}
    cronologia = analise.cronologia(teatros)

    # 2. velocidade da frente: simulação de resposta conhecida e dados reais
    simulacao = pd.DataFrame(frente.comparar_estimadores(velocidade=250.0, repeticoes=200, semente=0))
    velocidades = {chave: analise.velocidades(t) for chave, t in teatros.items()}
    esforco = {chave: analise.esforco_e_atraso(t) for chave, t in teatros.items()}

    # 3 a 5. modelo, linhas de base e validação no tempo
    validacoes = {
        f"{chave}_{corte}": analise.validar(teatros[chave], corte) for chave, cortes in analise.CORTES.items() for corte in cortes
    }

    # 6. previsão: a forma do modelo de cada teatro sai da regra aplicada à validação
    escolhas = {chave: analise.escolha_da_forma(validacoes, chave) for chave in teatros}
    previsoes, resumos = {}, {}
    for chave, t in teatros.items():
        previsoes[chave], resumos[chave] = analise.prever(t, escolhas[chave]["usa_temperatura"])
    tabela = pd.concat(previsoes.values(), ignore_index=True)
    termico = analise.limite_termico(list(teatros.values()))

    colunas = [
        "celula", "teatro", "regiao", "lat_sul", "lon_oeste", "ocupada", "ano_primeiro_registro", "ano_bruto",
        "prob_5_anos", "prob_5_anos_inf", "prob_5_anos_sup", "prob_10_anos", "prob_10_anos_inf", "prob_10_anos_sup",
        "prob_suscetivel", "tmin_c", "limite_termico", "distancia_origem_km",
    ]  # fmt: skip
    tabela[colunas].to_csv(SAIDA / "probabilidade_de_chegada.csv", index=False, lineterminator="\n")

    resultados = {
        "coleta": {
            "data": base["coleta"]["coletado_em"][:10],
            "fontes": base["coleta"]["fontes"],
            "funil": base["coleta"]["funil"],
            "ausencias_no_gbif": base["coleta"]["ausencias_no_gbif"],
            "registros_limpos_por_teatro": base["coleta"]["registros_limpos_por_teatro"],
            "conjuntos_de_dados": base["coleta"]["conjuntos_de_dados"],
        },
        "configuracao": {
            "ano_final": analise.ANO_FINAL,
            "inicio_da_expansao": analise.INICIO_EXPANSAO,
            "cortes": analise.CORTES,
            "celula_graus": 1,
            "profundidade_maxima_m": 300,
        },
        "teatros": {
            chave: {
                **analise.resumo_do_teatro(t),
                "fontes_do_primeiro_registro": analise.fontes_do_primeiro_registro(t),
                "area_e_frente": _registros(curvas[chave]),
            }
            for chave, t in teatros.items()
        },
        "cronologia": _registros(cronologia),
        "registros_que_contradizem": analise.registros_que_contradizem(base),
        "velocidade": {
            "simulacao": _registros(simulacao),
            "dados_reais": {chave: json.loads(v.to_json(orient="index", force_ascii=False)) for chave, v in velocidades.items()},
            "esforco_e_atraso": esforco,
        },
        "validacao": validacoes,
        "rotulos_dos_metodos": analise.ROTULOS,
        "escolha_da_forma": escolhas,
        "previsao": resumos,
        "previsao_maiores_probabilidades": {
            chave: _registros(
                p[~p["ocupada"]].sort_values("prob_10_anos", ascending=False).head(12)[
                    ["celula", "regiao", "lat_sul", "lon_oeste", "prob_suscetivel", "prob_5_anos", "prob_10_anos", "prob_10_anos_inf", "prob_10_anos_sup", "tmin_c"]
                ]
            )
            for chave, p in previsoes.items()
        },
        "limite_termico": termico,
    }
    resultados["para_o_site"] = site.bloco(resultados)

    figuras = graficos_do_estudo(base, teatros, curvas, simulacao, velocidades, validacoes, tabela, resultados)
    for nome, figura in figuras.items():
        figura.savefig(FIGURAS / f"{nome}.png")
        plt.close(figura)

    resultados["tempo_de_execucao_s"] = round(time.time() - inicio, 1)
    (SAIDA / "resultados.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False, default=float), encoding="utf-8")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.float_format", lambda v: f"{v:.3f}")
    for chave in teatros:
        print(chave, {k: v for k, v in resultados["teatros"][chave].items() if k != "area_e_frente"})
        print(velocidades[chave].to_string())
        print("esforço e atraso:", esforco[chave])
    print(cronologia.to_string())
    print(simulacao[["cenario", "estimador", "erro_relativo", "reqm_relativo"]].to_string())
    for nome, v in validacoes.items():
        print("=====", nome, "| alvo", v["celulas_alvo"], "| velocidade média histórica", round(v["velocidade_media_historica_km_ano"]))
        for forma, p in v["parametros"].items():
            print("  ", forma, {k: (round(x, 4) if isinstance(x, float) else x) for k, x in p.items()})
        for horizonte, h in v["horizontes"].items():
            print(f"  {horizonte} anos: alvo {h['celulas_alvo']}, colonizadas {h['colonizadas']}")
            for metodo in analise.ROTULOS:
                m = h[metodo]
                print(f"    {metodo:30s} AUC {m['auc']:.3f} [{m['auc_ic'][0]:.3f}; {m['auc_ic'][1]:.3f}]  Brier {m['brier']:.4f}  previstas {m['previstas']:.1f}")
            print("    calibração:", [(x["faixa"], x["celulas"], round(x["previsto"], 2), round(x["observado"], 2)) for x in h["modelo"]["calibracao"]])
        print("  erro no ano:", v["erro_no_ano"])
        for regiao, linha in v["regioes"].items():
            print("  ", regiao, linha)
        print(pd.DataFrame(v["curvas"]).round(0).to_string())
    print("escolha da forma:", escolhas)
    for chave, resumo in resumos.items():
        print(chave, json.dumps(resumo, ensure_ascii=False, default=float))
        print(pd.DataFrame(resultados["previsao_maiores_probabilidades"][chave]).to_string())
    print(json.dumps(resultados["registros_que_contradizem"], ensure_ascii=False))
    print(json.dumps(resultados["para_o_site"], ensure_ascii=False, indent=1)[:3000])
    print("limite térmico:", termico)
    print(f"Gravado em {SAIDA / 'resultados.json'}, {SAIDA / 'probabilidade_de_chegada.csv'} e {FIGURAS} em {time.time() - inicio:.0f} s")


def graficos_do_estudo(base, teatros, curvas, simulacao, velocidades, validacoes, tabela, r) -> dict:
    """As figuras do README. Os títulos dizem a conclusão e são montados com os números do resultado."""
    num = graficos.numero
    atl, med = r["teatros"]["atlantico"], r["teatros"]["mediterraneo"]
    figuras = {}
    figuras["mapa_primeiro_registro"] = graficos.mapa_do_primeiro_registro(
        base["celulas"],
        base["costa"],
        f"Em 40 anos, o peixe-leão foi registrado em {atl['celulas_com_registro']} de {atl['celulas_de_plataforma']} células do Atlântico oeste",
        f"Ano do primeiro registro corroborado por célula de 1° da plataforma (0 a 300 m). No Mediterrâneo, {med['celulas_com_registro']} de {med['celulas_de_plataforma']} células.",
    )
    figuras["area_no_tempo"] = graficos.area_no_tempo(
        curvas,
        analise.INICIO_EXPANSAO,
        f"O auge foi em {atl['ano_de_pico']} no Atlântico ({atl['novas_celulas_no_pico']} células novas no ano) e em {med['ano_de_pico']} no Mediterrâneo ({med['novas_celulas_no_pico']})",
        "Células de 1° com registro corroborado de peixe-leão, acumulado por ano. No Mediterrâneo, registro anterior a 2012 não data a chegada.",
    )
    dados_frente = {}
    for chave, t in teatros.items():
        distancia, ano, _ = analise.dados_da_frente(t)
        dados_frente[chave] = {"distancia": distancia, "ano": ano, "nome": f"{t.nome}, a partir de {t.inicio + 1}"}
    v = r["velocidade"]["dados_reais"]["atlantico"]
    figuras["distancia_x_ano"] = graficos.distancia_x_ano(
        dados_frente,
        f"A média diz {num(v['Média: distância contra ano (linha de base)']['km_por_ano'], 0)} km por ano; a frente andou a {num(v['Frente: quantil 0,10 do ano']['km_por_ano'], 0)} no Atlântico",
        "Cada ponto é uma célula. A reta laranja é a média; a azul passa pelos registros mais cedo em cada distância.",
    )
    pior = simulacao[simulacao["cenario"] == simulacao["cenario"].iloc[-1]].set_index("estimador")["erro_relativo"]
    erro_do_quantil = abs(pior["Frente: quantil 0,10 do ano"]) * 100
    figuras["erro_dos_estimadores"] = graficos.erro_dos_estimadores(
        simulacao,
        f"Com detecção imperfeita, a média erra a velocidade em {num(abs(pior['Média: distância contra ano (linha de base)']) * 100, 0)}%; "
        f"o quantil do ano, em {'menos de 1' if erro_do_quantil < 1 else num(erro_do_quantil, 0)}%",
        "Invasão simulada com frente de 250 km por ano. Ponto: erro médio em 200 simulações; barra: 5% a 95%.",
    )
    paineis = [
        {"rotulo": "Atlântico, ajuste até 2010", "curvas": validacoes["atlantico_2010"]["curvas"]},
        {"rotulo": "Atlântico, ajuste até 2018", "curvas": validacoes["atlantico_2018"]["curvas"]},
        {"rotulo": "Mediterrâneo, ajuste até 2018", "curvas": validacoes["mediterraneo_2018"]["curvas"]},
    ]
    figuras["validacao_area"] = graficos.validacao(
        paineis,
        "celulas",
        "células com registro",
        site.titulo_da_validacao(r),
        "Células com registro depois de cada corte: o que cada método previa e o que aconteceu.",
    )
    figuras["mapa_da_previsao"] = graficos.mapa_da_previsao(
        tabela,
        base["costa"],
        site.titulo_da_previsao(r),
        "Probabilidade de primeiro registro de 2026 a 2035 em cada célula ainda sem registro. Exercício de modelagem, não previsão oficial.",
    )
    return figuras


if __name__ == "__main__":
    main()
