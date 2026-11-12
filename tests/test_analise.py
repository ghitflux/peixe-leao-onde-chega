import numpy as np
import pandas as pd

from peixe_leao import analise, site
from peixe_leao import espalhamento as esp


def _teatro_sintetico(celulas: int = 40) -> analise.Teatro:
    """Costa reta no Mediterrâneo fictício: uma célula a cada 100 km, invasão de 1 célula por ano a partir de 2012."""
    posicao = np.arange(celulas) * 100.0
    primeiro = np.where(np.arange(celulas) <= 13, 2012.0 + np.arange(celulas), np.nan)
    tabela = pd.DataFrame(
        {
            "celula": [f"M_{k}" for k in range(celulas)],
            "lat_c": 35.0,
            "lon_c": 15.0 + np.arange(celulas) * 0.5,
            "ano_primeiro_registro": pd.array(np.where(np.isnan(primeiro), pd.NA, primeiro), dtype="Int64"),
            "ano_bruto": pd.array(np.where(np.isnan(primeiro), pd.NA, primeiro), dtype="Int64"),
        }
    )
    anos = np.arange(1990, analise.ANO_FINAL + 1)
    return analise.Teatro(
        chave="mediterraneo",
        nome="Mediterrâneo",
        celulas=tabela,
        distancias=np.abs(posicao[:, None] - posicao[None, :]),
        distancia_origem=posicao,
        primeiro=primeiro,
        anos_esforco=anos,
        esforco=np.ones((len(anos), celulas)),
        habitat=np.ones((len(anos), celulas)),
        tmin=np.full(celulas, 20.0),
        isolada=np.zeros(celulas, bool),
        ramo=np.ones(celulas, bool),
    )


def test_area_e_frente_acompanha_a_invasao():
    curva = analise.area_e_frente(_teatro_sintetico()).set_index("ano")
    assert curva.loc[2012, "celulas_com_registro"] == 1
    assert curva.loc[2020, "celulas_com_registro"] == 9
    assert curva.loc[2020, "frente_km"] == 800.0
    assert curva.loc[2025, "frente_km"] == 1300.0
    assert curva["novas_celulas"].sum() == 14


def test_dados_da_frente_excluem_as_sementes_e_respeitam_o_corte():
    t = _teatro_sintetico()
    distancia, ano, esforco = analise.dados_da_frente(t, ate=2018)
    assert ano.min() == 2013 and ano.max() == 2018  # a semente de 2012 fica fora
    assert len(distancia) == 6 and len(esforco) == 6


def test_velocidade_recuperada_na_costa_sintetica():
    v = analise.velocidades(_teatro_sintetico(), repeticoes=30)
    assert np.allclose(v["km_por_ano"], 100.0, rtol=0.02)  # uma célula de 100 km por ano, sem ruído


def test_painel_esconde_o_que_veio_depois_do_corte():
    t = _teatro_sintetico()
    p = analise.painel(t, 2018)
    assert p.anos.tolist() == [2013, 2014, 2015, 2016, 2017, 2018]
    assert np.nanmax(p.primeiro) == 2018  # registros de 2019 em diante viram "sem registro"
    assert np.isnan(p.primeiro[7:]).all()


def test_ano_previsto_e_a_mediana_das_simulacoes_em_que_a_celula_chega():
    simulado = np.array(
        [
            [2020.0, np.nan, np.nan],
            [2022.0, 2021.0, np.nan],
            [2024.0, np.nan, np.nan],
            [np.nan, np.nan, np.nan],
        ]
    )
    previsto = analise._ano_previsto(simulado, teto=2026)
    assert previsto.tolist() == [2022.0, 2021.0, 2026.0]
    raro = np.full((100, 1), np.nan)
    raro[:3, 0] = 2020.0  # chega em 3% das simulações: conta como "não chega"
    assert analise._ano_previsto(raro, teto=2026).tolist() == [2026.0]


def test_escolha_da_forma_exige_melhora_em_todos_os_cortes():
    def validacao(corte, sem, com):
        return {"corte": corte, "horizontes": {"5": {"modelo": {"brier": com}, "modelo_sem_temperatura": {"brier": sem}}}}

    sempre = {"atlantico_2010": validacao(2010, 0.10, 0.09), "atlantico_2018": validacao(2018, 0.06, 0.05), "mediterraneo_2018": validacao(2018, 0.2, 0.3)}
    assert analise.escolha_da_forma(sempre, "atlantico")["usa_temperatura"] is True
    assert analise.escolha_da_forma(sempre, "mediterraneo")["usa_temperatura"] is False
    as_vezes = {"atlantico_2010": validacao(2010, 0.10, 0.09), "atlantico_2018": validacao(2018, 0.05, 0.06)}
    assert analise.escolha_da_forma(as_vezes, "atlantico")["usa_temperatura"] is False


def test_validacao_roda_de_ponta_a_ponta_e_nao_olha_o_futuro():
    t = _teatro_sintetico()
    v = analise.validar(t, 2018, sorteios=4, por_sorteio=10)
    assert v["celulas_com_registro_no_corte"] == 7
    assert v["horizontes"]["5"]["colonizadas"] == 5  # 2019 a 2023
    assert set(analise.ROTULOS) <= set(v["horizontes"]["5"])
    assert v["curvas"][0]["modelo_celulas"] == 7.0  # no ano do corte, o previsto é o que já existia
    # numa invasão que anda uma célula por ano, a regra da vizinha ordena as células sem erro
    assert v["horizontes"]["5"]["vizinha"]["auc"] > 0.99  # só os empates no ano previsto tiram do 1
    assert v["erro_no_ano"]["vizinha"]["erro_absoluto_medio"] <= 2.0


def test_numeros_do_site_no_formato_de_cada_idioma():
    assert site._n(13349, 0, "pt") == "13.349"
    assert site._n(13349, 0, "en") == "13,349"
    assert site._n(0.84, 2, "es") == "0,84"
    assert site._pct(0.876, "pt") == "88%"


def test_formas_do_modelo():
    assert analise.FORMAS["modelo"] == esp.Forma(suscetivel=True, termico=True)
    assert esp.Forma(suscetivel=True, termico=True).parametros == 7
    assert len(esp.Forma(suscetivel=False).limites()) == 4
