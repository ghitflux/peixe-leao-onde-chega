"""Figuras do README e do notebook, no estilo do portfólio."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle

from peixe_leao import frente
from peixe_leao.estilo import (
    APAGADO,
    AQUA,
    AZUL,
    EIXO,
    ESTILO,
    GRADE,
    LARANJA,
    RAMPA_AZUL,
    SUPERFICIE,
    TINTA,
    TINTA_SECUNDARIA,
    numero,
)

SEM_REGISTRO = "#e6e4dc"
JANELAS = {"atlantico": (-99, -29, -36, 44), "mediterraneo": (-7, 37.5, 29.5, 46.5)}
FAIXAS_DE_ANO = [(1985, 2003), (2004, 2008), (2009, 2012), (2013, 2017), (2018, 2025)]
# do registro mais antigo (escuro) ao mais recente (claro)
CORES_DE_ANO = list(reversed(RAMPA_AZUL))


def _titulos(fig: Figure, titulo: str, subtitulo: str) -> None:
    fig.text(0.02, 0.965, titulo, fontsize=13, fontweight="bold", color=TINTA, va="top")
    fig.text(0.02, 0.905, subtitulo, fontsize=9.5, color=TINTA_SECUNDARIA, va="top")


def _mapa(ax: plt.Axes, celulas: pd.DataFrame, cores: list, costa: list, janela: tuple, rotulo: str) -> None:
    """Desenha as células como quadrados de 1 grau e a linha de costa por cima."""
    oeste, leste, sul, norte = janela
    quadrados = [Rectangle((o, s), 1, 1) for s, o in zip(celulas["lat_sul"], celulas["lon_oeste"])]
    ax.add_collection(PatchCollection(quadrados, facecolors=cores, edgecolors=SUPERFICIE, linewidths=0.3))
    ax.add_collection(LineCollection(costa, colors=APAGADO, linewidths=0.6))
    ax.set_xlim(oeste, leste)
    ax.set_ylim(sul, norte)
    ax.set_aspect(1 / np.cos(np.radians((sul + norte) / 2)))
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_visible(True)
        lado.set_color(EIXO)
    ax.set_title(rotulo, fontsize=9.5, color=TINTA_SECUNDARIA, loc="left", pad=4)


def _cor_do_ano(ano) -> str:
    if pd.isna(ano):
        return SEM_REGISTRO
    for (inicio, fim), cor in zip(FAIXAS_DE_ANO, CORES_DE_ANO):
        if inicio <= ano <= fim:
            return cor
    return SEM_REGISTRO


def mapa_do_primeiro_registro(celulas: pd.DataFrame, costa: list, titulo: str, subtitulo: str) -> Figure:
    with plt.rc_context(ESTILO):
        fig = plt.figure(figsize=(8.2, 5.6), dpi=160)
        _titulos(fig, titulo, subtitulo)
        eixos = {
            "atlantico": fig.add_axes([0.02, 0.03, 0.46, 0.80]),
            "mediterraneo": fig.add_axes([0.50, 0.38, 0.48, 0.45]),
        }
        nomes = {"atlantico": "Atlântico oeste", "mediterraneo": "Mediterrâneo"}
        for chave, ax in eixos.items():
            parte = celulas[celulas["teatro"] == chave]
            _mapa(ax, parte, [_cor_do_ano(a) for a in parte["ano_primeiro_registro"]], costa, JANELAS[chave], nomes[chave])
        legenda = [Patch(facecolor=cor, label=f"{i} a {f}") for (i, f), cor in zip(FAIXAS_DE_ANO, CORES_DE_ANO)]
        legenda.append(Patch(facecolor=SEM_REGISTRO, label="plataforma sem registro"))
        fig.legend(handles=legenda, loc="lower left", bbox_to_anchor=(0.52, 0.05), ncols=2, fontsize=8.5, title="Ano do primeiro registro", title_fontsize=9, alignment="left")
    return fig


def area_no_tempo(curvas: dict[str, pd.DataFrame], inicios: dict[str, int], titulo: str, subtitulo: str) -> Figure:
    with plt.rc_context(ESTILO):
        fig, eixos = plt.subplots(1, 2, figsize=(8.2, 4.2), dpi=160, sharey=False)
        fig.subplots_adjust(top=0.76, left=0.07, right=0.98, bottom=0.12, wspace=0.18)
        _titulos(fig, titulo, subtitulo)
        nomes = {"atlantico": "Atlântico oeste", "mediterraneo": "Mediterrâneo"}
        for ax, (chave, curva) in zip(eixos, curvas.items()):
            ax.fill_between(curva["ano"], curva["celulas_com_registro"], color=AZUL, alpha=0.12, linewidth=0)
            ax.plot(curva["ano"], curva["celulas_com_registro"], color=AZUL)
            ax.axvline(inicios[chave], color=EIXO, linewidth=1)
            ax.annotate(f"expansão contada\na partir de {inicios[chave]}", (inicios[chave], curva["celulas_com_registro"].max() * 0.80), xytext=(-6, 0), textcoords="offset points", ha="right", fontsize=8.5, color=TINTA_SECUNDARIA)
            ultimo = curva.iloc[-1]
            ax.annotate(f"{int(ultimo['celulas_com_registro'])} células", (ultimo["ano"], ultimo["celulas_com_registro"]), xytext=(-4, 6), textcoords="offset points", ha="right", fontsize=9, color=TINTA)
            ax.set_title(nomes[chave], fontsize=9.5, color=TINTA_SECUNDARIA, loc="left")
            ax.set_ylim(0, None)
            ax.set_xlabel("ano")
        eixos[0].set_ylabel("células de 1° com registro (acumulado)")
    return fig


def distancia_x_ano(dados: dict[str, dict], titulo: str, subtitulo: str) -> Figure:
    """`dados[teatro]` = {"distancia", "ano", "nome"}. Reta laranja: média; reta azul: quantil 0,10 do ano."""
    with plt.rc_context(ESTILO):
        fig, eixos = plt.subplots(1, 2, figsize=(8.2, 4.4), dpi=160)
        fig.subplots_adjust(top=0.76, left=0.08, right=0.98, bottom=0.12, wspace=0.22)
        _titulos(fig, titulo, subtitulo)
        for ax, d in zip(eixos, dados.values()):
            distancia, ano = np.asarray(d["distancia"]), np.asarray(d["ano"])
            ax.scatter(ano, distancia, s=14, color=APAGADO, alpha=0.55, linewidths=0, zorder=2)
            anos = np.array([ano.min(), ano.max()])
            b = frente.minimos_quadrados(np.column_stack([np.ones(len(ano)), ano]), distancia)
            ax.plot(anos, b[0] + b[1] * anos, color=LARANJA, zorder=3, label=f"média: {numero(b[1], 0)} km/ano")
            X = np.column_stack([np.ones(len(ano)), distancia])
            q = frente.regressao_quantilica(X, ano, 0.10)
            faixa = np.array([0, distancia.max()])
            ax.plot(q[0] + q[1] * faixa, faixa, color=AZUL, zorder=3, label=f"frente: {numero(1 / q[1], 0)} km/ano")
            ax.set_title(d["nome"], fontsize=9.5, color=TINTA_SECUNDARIA, loc="left")
            ax.set_xlabel("ano do primeiro registro na célula")
            ax.set_xlim(ano.min() - 1, ano.max() + 1)
            ax.set_ylim(0, distancia.max() * 1.05)
            ax.legend(loc="lower right", fontsize=8.5)
        eixos[0].set_ylabel("distância pelo mar até a introdução (km)")
    return fig


def erro_dos_estimadores(simulacao: pd.DataFrame, titulo: str, subtitulo: str) -> Figure:
    """Erro relativo médio de cada estimador em cada cenário simulado, com a faixa de 5% a 95%."""
    cores = {
        "Média: distância contra ano (linha de base)": LARANJA,
        "Frente: quantil 0,10 do ano": AZUL,
        "Frente: envelope dos recordes": AQUA,
    }
    with plt.rc_context(ESTILO):
        cenarios = list(dict.fromkeys(simulacao["cenario"]))
        estimadores = list(dict.fromkeys(simulacao["estimador"]))
        fig, eixos = plt.subplots(1, len(cenarios), figsize=(8.2, 4.6), dpi=160, sharey=True)
        fig.subplots_adjust(top=0.72, left=0.33, right=0.985, bottom=0.12, wspace=0.10)
        _titulos(fig, titulo, subtitulo)
        for ax, cenario in zip(eixos, cenarios):
            parte = simulacao[simulacao["cenario"] == cenario].set_index("estimador")
            for k, nome in enumerate(estimadores):
                linha = parte.loc[nome]
                cor = cores.get(nome, APAGADO)
                real = linha["velocidade_real"]
                ax.plot([linha["p05"] / real - 1, linha["p95"] / real - 1], [k, k], color=cor, linewidth=2.5, alpha=0.45)
                ax.plot(linha["erro_relativo"], k, "o", color=cor, markersize=7)
            ax.axvline(0, color=TINTA_SECUNDARIA, linewidth=0.8)
            ax.set_xlim(-0.45, 0.45)
            ax.set_xticks([-0.3, 0, 0.3])
            ax.set_xticklabels(["−30%", "0", "+30%"])
            ax.grid(axis="x")
            ax.grid(axis="y", visible=False)
            ax.set_title("\n".join(_quebrar(cenario, 20)), fontsize=8.5, color=TINTA_SECUNDARIA, loc="left")
        eixos[0].set_yticks(range(len(estimadores)))
        eixos[0].set_yticklabels(estimadores, fontsize=8.5)
        eixos[0].invert_yaxis()
    return fig


def _quebrar(texto: str, largura: int) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        if len(atual) + len(palavra) + 1 > largura and atual:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    return linhas + [atual]


def validacao(paineis: list[dict], coluna: str, rotulo_y: str, titulo: str, subtitulo: str) -> Figure:
    """Previsto e realizado depois de cada corte. `coluna` é 'celulas' ou 'frente_km'."""
    with plt.rc_context(ESTILO):
        fig, eixos = plt.subplots(1, len(paineis), figsize=(8.2, 4.6), dpi=160)
        fig.subplots_adjust(top=0.75, left=0.08, right=0.98, bottom=0.20, wspace=0.25)
        _titulos(fig, titulo, subtitulo)
        for k, (ax, p) in enumerate(zip(np.atleast_1d(eixos), paineis)):
            c = pd.DataFrame(p["curvas"])
            ax.fill_between(c["ano"], c[f"modelo_{coluna}_p05"], c[f"modelo_{coluna}_p95"], color=AZUL, alpha=0.15, linewidth=0)
            ax.plot(c["ano"], c[f"modelo_{coluna}"], color=AZUL, label="modelo de espalhamento (faixa de 90%)")
            ax.plot(c["ano"], c[f"velocidade_constante_{coluna}"], color=LARANJA, label="velocidade constante")
            if f"vizinha_{coluna}" in c:
                ax.plot(c["ano"], c[f"vizinha_{coluna}"], color=AQUA, label="célula vizinha")
            ax.plot(c["ano"], c[f"observado_{coluna}"], color=TINTA, linewidth=2.2, label="o que aconteceu")
            ax.set_title(p["rotulo"], fontsize=9.5, color=TINTA_SECUNDARIA, loc="left")
            ax.set_xlabel("ano")
            ax.xaxis.set_major_locator(plt.MaxNLocator(5, integer=True))
            if k == 0:
                ax.set_ylabel(rotulo_y)
                marcas, textos = ax.get_legend_handles_labels()
        fig.legend(marcas, textos, loc="lower center", ncols=4, fontsize=8.5, bbox_to_anchor=(0.5, 0.0))
    return fig


def mapa_da_previsao(tabela: pd.DataFrame, costa: list, titulo: str, subtitulo: str) -> Figure:
    """Probabilidade de primeiro registro em 10 anos nas células ainda sem registro."""
    faixas = [(0.0, 0.05), (0.05, 0.2), (0.2, 0.5), (0.5, 0.8), (0.8, 1.01)]
    rotulos = ["menos de 5%", "5% a 20%", "20% a 50%", "50% a 80%", "mais de 80%"]

    def cor(linha) -> str:
        if linha["ocupada"]:
            return APAGADO
        for (inferior, superior), tom in zip(faixas, RAMPA_AZUL):
            if inferior <= linha["prob_10_anos"] < superior:
                return tom
        return SEM_REGISTRO

    with plt.rc_context(ESTILO):
        fig = plt.figure(figsize=(8.2, 5.6), dpi=160)
        _titulos(fig, titulo, subtitulo)
        eixos = {
            "atlantico": fig.add_axes([0.02, 0.03, 0.46, 0.80]),
            "mediterraneo": fig.add_axes([0.50, 0.38, 0.48, 0.45]),
        }
        nomes = {"atlantico": "Atlântico oeste", "mediterraneo": "Mediterrâneo"}
        for chave, ax in eixos.items():
            parte = tabela[tabela["teatro"] == chave]
            _mapa(ax, parte, [cor(linha) for _, linha in parte.iterrows()], costa, JANELAS[chave], nomes[chave])
        legenda = [Patch(facecolor=tom, label=texto) for tom, texto in zip(RAMPA_AZUL, rotulos)]
        legenda.append(Patch(facecolor=APAGADO, label="já tem registro"))
        fig.legend(handles=legenda, loc="lower left", bbox_to_anchor=(0.52, 0.05), ncols=2, fontsize=8.5, title="Probabilidade de primeiro registro em 10 anos", title_fontsize=9, alignment="left")
    return fig


def calibracao(linhas: list[dict], titulo: str, subtitulo: str) -> Figure:
    """Probabilidade prevista contra fração observada, por faixa (tamanho do ponto = número de células)."""
    with plt.rc_context(ESTILO):
        fig, ax = plt.subplots(figsize=(8.2, 4.2), dpi=160)
        fig.subplots_adjust(top=0.76, left=0.09, right=0.97, bottom=0.14)
        _titulos(fig, titulo, subtitulo)
        ax.plot([0, 1], [0, 1], color=GRADE, linewidth=1.5)
        for grupo, cor_grupo in zip(dict.fromkeys(linha["grupo"] for linha in linhas), [AZUL, AQUA, LARANJA]):
            parte = [linha for linha in linhas if linha["grupo"] == grupo]
            ax.plot([p["previsto"] for p in parte], [p["observado"] for p in parte], "-o", color=cor_grupo, label=grupo)
            for p in parte:
                ax.annotate(str(p["celulas"]), (p["previsto"], p["observado"]), xytext=(6, -10), textcoords="offset points", fontsize=8, color=TINTA_SECUNDARIA)
        ax.set_xlabel("probabilidade prevista (média da faixa)")
        ax.set_ylabel("fração das células em que aconteceu")
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.legend(loc="upper left", fontsize=8.5)
    return fig
