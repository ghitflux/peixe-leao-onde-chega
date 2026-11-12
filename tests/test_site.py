"""Forma dos gráficos entregues ao site em reports/resultados.json (o arquivo é versionado)."""

import json
from pathlib import Path

import pytest

from peixe_leao import site

RESULTADOS = Path(__file__).resolve().parents[1] / "reports" / "resultados.json"
IDIOMAS = {"pt", "en", "es"}
PAPEIS = {"principal", "base", "alternativa", "neutro"}
LIMITE = {"linhas": 80, "barras": 80, "pontos": 300}


@pytest.fixture(scope="module")
def para_o_site() -> dict:
    return json.loads(RESULTADOS.read_text(encoding="utf-8"))["para_o_site"]


def _tres_idiomas(texto: dict) -> bool:
    return set(texto) == IDIOMAS and all(isinstance(v, str) and v.strip() for v in texto.values())


def _conferir(grafico: dict, exige_leitura: bool) -> None:
    assert grafico["tipo"] in LIMITE
    for campo in ("titulo", "eixo_x", "eixo_y"):
        assert _tres_idiomas(grafico[campo]), campo
    assert all(len(t) <= 90 for t in grafico["titulo"].values())
    if exige_leitura:
        assert _tres_idiomas(grafico["leitura"])
    assert grafico["formato_x"] in {"numero", "percentual", "data"}
    assert grafico["formato_y"] in {"numero", "percentual", "moeda"}
    assert 1 <= len(grafico["series"]) <= 4
    for serie in grafico["series"]:
        assert _tres_idiomas(serie["nome"])
        assert serie["papel"] in PAPEIS
        assert 1 <= len(serie["pontos"]) <= LIMITE[grafico["tipo"]]
        for x, y in serie["pontos"]:
            assert isinstance(y, (int, float))
            assert isinstance(x, str) if grafico["tipo"] == "barras" else isinstance(x, (int, float))
        if grafico["tipo"] == "barras":
            assert set(serie["rotulos"]) == IDIOMAS
            assert all(len(r) == len(serie["pontos"]) for r in serie["rotulos"].values())
            assert [p[0] for p in serie["pontos"]] == serie["rotulos"]["pt"]
        if grafico["formato_y"] == "percentual":
            assert all(-1 <= p[1] <= 1 for p in serie["pontos"])
    if "faixa" in grafico:
        assert grafico["tipo"] == "linhas"
        faixa, alvo = grafico["faixa"], grafico["series"][grafico["faixa"]["serie"]]["pontos"]
        assert len(faixa["inferior"]) == len(faixa["superior"]) == len(alvo)
        assert all(i[1] <= s[1] for i, s in zip(faixa["inferior"], faixa["superior"]))


def test_grafico_principal_tem_a_forma_combinada(para_o_site):
    _conferir(para_o_site["grafico"], exige_leitura=False)
    assert all(len(v) <= 12 for v in para_o_site["numero_chave"].values())


def test_graficos_extras_tem_a_forma_combinada(para_o_site):
    extras = para_o_site["graficos_extras"]
    assert 3 <= len(extras) <= 5
    for grafico in extras:
        _conferir(grafico, exige_leitura=True)
    assert {g["tipo"] for g in extras} == {"linhas", "barras", "pontos"}


def test_rotulo_da_celula_em_cada_idioma():
    assert site._celula(-6, -36, "pt") == "6°S 36°O"
    assert site._celula(-6, -36, "en") == "6°S 36°W"
    assert site._celula(36, 3, "pt") == "36°N 3°L"
    assert site._celula(36, 3, "es") == "36°N 3°E"
