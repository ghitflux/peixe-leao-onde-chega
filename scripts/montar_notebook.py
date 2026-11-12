"""Monta analise.ipynb com nbformat. Depois de montar, execute:

    uv run python scripts/montar_notebook.py
    uv run jupyter nbconvert --to notebook --execute --inplace analise.ipynb

O notebook é uma narrativa fina: lê o extrato de data/ e as tabelas de reports/resultados.json (geradas por
scripts/rodar_analise.py) e conta a história. O ajuste completo e as simulações rodam no script, não aqui.
"""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

RAIZ = Path(__file__).resolve().parents[1]

CELULAS: list[tuple[str, str]] = [
    ("md", """# Onde o peixe-leão vai chegar a seguir, e quando?

O peixe-leão (*Pterois volitans* e *P. miles*), nativo do Indo-Pacífico, invadiu o Atlântico oeste a partir da
Flórida e, pelo Canal de Suez, o Mediterrâneo. A decisão que este estudo informa é onde concentrar vigilância e
detecção precoce nos próximos anos.

O caminho: (1) reconstruir a frente de invasão com registros públicos; (2) medir a velocidade da frente sem se
enganar com a detecção imperfeita; (3) ajustar um modelo de espalhamento e conferi-lo no tempo, contra duas regras
simples; (4) prever, com faixa de incerteza.

É análise de dado público agregado, feita por um profissional de dados, não por um biólogo. Os números vêm de
`reports/resultados.json`; o método está em `src/peixe_leao/` e é conferido em `tests/`."""),
    ("code", """import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import display

from peixe_leao import analise, dados, frente, graficos

pd.set_option("display.float_format", lambda v: f"{v:,.2f}")
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_colwidth", 90)
r = json.loads(Path("reports/resultados.json").read_text(encoding="utf-8"))
base = dados.carregar()
teatros = {chave: analise.montar_teatro(base, chave) for chave in ("atlantico", "mediterraneo")}


def mostrar(figura):
    display(figura)
    plt.close(figura)


print("Coleta:", r["coleta"]["data"])"""),
    ("md", """## 1. Do registro bruto ao dado central

Três fontes públicas, sem chave: o banco de espécies aquáticas não nativas do USGS (NAS), o GBIF e o OBIS. O funil
abaixo mostra o que cada filtro tira. Dois pontos pedem atenção:

- **o GBIF devolve registros de ausência** (censos que procuraram o peixe e não acharam) na mesma busca. Eles não
  são baixados; a contagem está na segunda tabela;
- **as três fontes se repetem**: o NAS é republicado dentro do GBIF e do OBIS, e a mesma observação de ciência
  cidadã aparece nas duas redes."""),
    ("code", """funil = pd.DataFrame(r["coleta"]["funil"]).set_index("passo")
display(funil)
display(pd.Series(r["coleta"]["ausencias_no_gbif"], name="registros de ausência no GBIF (não baixados)").to_frame())"""),
    ("md", """O dado central é o **ano do primeiro registro corroborado** em cada célula de 1° da plataforma continental (0 a
300 m de profundidade). "Corroborado" quer dizer que há outro registro na mesma célula ou numa vizinha, no mesmo ano
ou nos três seguintes. Um registro sozinho pode ser erro de data, de identificação ou um animal solto que não deixou
população.

A tabela compara os dados com a cronologia publicada. A coluna do registro bruto mostra onde os dados públicos
discordam da literatura; a do registro corroborado, o que a regra faz com isso."""),
    ("code", """display(pd.DataFrame(r["cronologia"]))
display(pd.DataFrame({chave: {k: v for k, v in valor.items() if k != "mais_antigos"} for chave, valor in r["registros_que_contradizem"].items()}))"""),
    ("code", """atl, med = r["teatros"]["atlantico"], r["teatros"]["mediterraneo"]
mostrar(graficos.mapa_do_primeiro_registro(
    base["celulas"], base["costa"],
    f"O peixe-leão foi registrado em {atl['celulas_com_registro']} de {atl['celulas_de_plataforma']} células do Atlântico oeste",
    "Ano do primeiro registro corroborado por célula de 1° da plataforma (0 a 300 m).",
))
display(pd.DataFrame({chave: {k: v for k, v in valor.items() if k not in ("area_e_frente", "fontes_do_primeiro_registro")} for chave, valor in r["teatros"].items()}))"""),
    ("md", """## 2. A velocidade da frente

"Avança X km por ano" é a conta que todo mundo faz: a distância ao ponto de introdução contra o ano do primeiro
registro, por mínimos quadrados. Ela tem dois problemas. A frente é quem foi mais longe em cada época, não a média,
porque as células atrás da frente continuam sendo ocupadas por anos. E o primeiro registro vem depois da chegada, com
atraso maior onde há menos gente olhando.

Antes de aplicar qualquer estimador aos dados, ele é testado numa **invasão simulada com velocidade conhecida** (250
km por ano), em quatro cenários de dificuldade crescente."""),
    ("code", """sim = pd.DataFrame(r["velocidade"]["simulacao"])
display((sim.pivot(index="estimador", columns="cenario", values="erro_relativo") * 100).round(1)[list(dict.fromkeys(sim["cenario"]))])
mostrar(graficos.erro_dos_estimadores(sim, "Erro de cada estimador numa invasão de velocidade conhecida", "Frente de 250 km por ano. Ponto: erro médio em 200 simulações; barra: 5% a 95%."))"""),
    ("md", """Nos dados reais, a velocidade é medida no ramo que avança (no Atlântico, o do sul e do oeste; o ramo norte, pela
costa leste dos EUA, é levado pela Corrente do Golfo e não passa o inverno). O intervalo é de 95%, por bootstrap de
células."""),
    ("code", """for chave in teatros:
    print(chave)
    display(pd.DataFrame(r["velocidade"]["dados_reais"][chave]).T.round(0))
display(pd.DataFrame(r["velocidade"]["esforco_e_atraso"]))"""),
    ("md", """## 3. O modelo de espalhamento e a validação no tempo

O modelo descreve o primeiro registro de cada célula, ano a ano: o risco cresce com a proximidade (pelo mar) de
células já ocupadas e com o esforço de observação; uma fração das células não é suscetível (sem recife, fria demais
ou sem observador), e essa fração depende do habitat e da temperatura do mês mais frio.

A validação é a de quem não conhece o futuro: o modelo é ajustado com o que se sabia até um ano de corte e prevê os
anos seguintes. Ao lado dele, as duas regras simples (velocidade constante e célula vizinha) e duas versões
reduzidas do próprio modelo."""),
    ("code", """linhas = []
for nome, v in r["validacao"].items():
    for horizonte, h in v["horizontes"].items():
        for metodo, rotulo in r["rotulos_dos_metodos"].items():
            m = h[metodo]
            linhas.append({
                "teatro e corte": nome.replace("_", ", até "), "horizonte (anos)": int(horizonte), "método": rotulo,
                "AUC": m["auc"], "AUC inf.": m["auc_ic"][0], "AUC sup.": m["auc_ic"][1], "Brier": m["brier"],
                "células previstas": m["previstas"], "células colonizadas": h["colonizadas"],
            })
display(pd.DataFrame(linhas).set_index(["teatro e corte", "horizonte (anos)", "método"]).round(3))"""),
    ("code", """paineis = [
    {"rotulo": "Atlântico, ajuste até 2010", "curvas": r["validacao"]["atlantico_2010"]["curvas"]},
    {"rotulo": "Atlântico, ajuste até 2018", "curvas": r["validacao"]["atlantico_2018"]["curvas"]},
    {"rotulo": "Mediterrâneo, ajuste até 2018", "curvas": r["validacao"]["mediterraneo_2018"]["curvas"]},
]
mostrar(graficos.validacao(paineis, "celulas", "células com registro", "Células ocupadas depois de cada corte: previsto e realizado", "A faixa azul é a de 90% das simulações do modelo."))"""),
    ("md", """### O teste difícil: a foz do Amazonas e a chegada ao Brasil

A tabela mostra, para cada corte, o que o modelo e as regras simples diziam sobre regiões que ainda não tinham
registro. A linha das Guianas é a que mostra o erro de caminho: o modelo esperava a passagem por ali bem antes do
primeiro registro."""),
    ("code", """linhas = []
for nome, v in r["validacao"].items():
    for regiao, x in v["regioes"].items():
        linhas.append({
            "corte": nome.replace("_", ", até "), "região": regiao, "1º registro observado": x["ano_observado_do_primeiro_registro"],
            "modelo: mediana": x["ano_mediano_previsto"], "modelo: 5%": x["ano_previsto_p05"], "modelo: 95%": x["ano_previsto_p95"],
            "prob. de algum registro até 2025": x["probabilidade_de_algum_registro_ate_o_ano_final"],
            "velocidade constante": x["ano_velocidade_constante"], "célula vizinha": x["ano_vizinha"],
        })
display(pd.DataFrame(linhas).set_index(["corte", "região"]))
display(pd.DataFrame({nome: {metodo: f"{x['erro_absoluto_medio']:.1f} ({x['vies']:+.1f})" for metodo, x in v["erro_no_ano"].items() if metodo != "celulas"} for nome, v in r["validacao"].items()}).rename(index=r["rotulos_dos_metodos"]))"""),
    ("md", """## 4. A previsão para os próximos dez anos

O modelo é reajustado com todos os dados até 2025 e simulado até 2035. A tabela completa, por célula, está em
`reports/probabilidade_de_chegada.csv`. **É um exercício de modelagem, não uma previsão oficial.**"""),
    ("code", """tabela = pd.read_csv("reports/probabilidade_de_chegada.csv")
mostrar(graficos.mapa_da_previsao(tabela, base["costa"], "Probabilidade de primeiro registro até 2035", "Células ainda sem registro; em cinza, as que já têm."))
for chave in teatros:
    print(chave, "| parâmetros:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r["previsao"][chave]["parametros"].items() if not k.endswith("_ic")})
    display(pd.DataFrame(r["previsao"][chave]["regioes"]).T)
    display(pd.DataFrame(r["previsao_maiores_probabilidades"][chave]))
display(pd.DataFrame({k: v for k, v in r["limite_termico"].items() if isinstance(v, dict)}))"""),
    ("md", """## 5. O que levar daqui

- A regra de bolso "avança X km por ano" depende de qual conta se faz: a média e a frente dão números diferentes
  nos mesmos dados, e a simulação mostra qual delas erra com detecção imperfeita.
- O modelo de espalhamento acerta **quanto** a invasão cresce melhor do que acerta **onde**: para ordenar as células
  pela chance de serem as próximas, a regra da vizinha faz quase o mesmo.
- A primeira versão do modelo, sem a fração de células não suscetíveis, previa que quase tudo seria ocupado. O
  termo foi acrescentado depois de ver esse erro; por isso a validação do modelo final não é mais um teste intocado.
- O README lista onde o estudo falha e o que faltaria para isto virar contribuição científica."""),
]


def main() -> None:
    caderno = new_notebook()
    caderno.cells = [new_markdown_cell(texto) if tipo == "md" else new_code_cell(texto) for tipo, texto in CELULAS]
    caderno.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    caderno.metadata["language_info"] = {"name": "python"}
    nbformat.write(caderno, RAIZ / "analise.ipynb")
    print(f"analise.ipynb montado com {len(caderno.cells)} células")


if __name__ == "__main__":
    main()
