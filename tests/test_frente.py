import numpy as np
import pytest

from peixe_leao import frente


def test_regressao_quantilica_so_com_constante_devolve_o_quantil():
    y = np.array([1.0, 2.0, 3.0, 4.0, 100.0])
    X = np.ones((5, 1))
    assert frente.regressao_quantilica(X, y, 0.5)[0] == pytest.approx(3.0)  # a mediana ignora o valor extremo
    assert frente.regressao_quantilica(X, y, 0.9)[0] == pytest.approx(100.0)
    assert frente.regressao_quantilica(X, y, 0.1)[0] == pytest.approx(1.0)


def test_regressao_quantilica_recupera_reta_exata():
    x = np.linspace(0, 10, 30)
    X = np.column_stack([np.ones(30), x])
    for tau in (0.1, 0.5, 0.9):
        intercepto, inclinacao = frente.regressao_quantilica(X, 2.0 + 3.0 * x, tau)
        assert intercepto == pytest.approx(2.0, abs=1e-6)
        assert inclinacao == pytest.approx(3.0, abs=1e-6)


def test_regressao_quantilica_deixa_a_fracao_certa_abaixo_da_reta():
    gerador = np.random.default_rng(0)
    x = gerador.uniform(0, 10, 400)
    y = 1.0 + 2.0 * x + gerador.normal(0, 1, 400)
    X = np.column_stack([np.ones(400), x])
    b = frente.regressao_quantilica(X, y, 0.9)
    assert np.mean(y <= X @ b + 1e-9) == pytest.approx(0.9, abs=0.01)
    assert b[1] == pytest.approx(2.0, abs=0.15)  # ruído igual em todo x: a inclinação é a mesma em qualquer quantil


def test_todos_os_estimadores_acertam_sem_ruido():
    gerador = np.random.default_rng(1)
    distancia = gerador.uniform(0, 5000, 200)
    ano = distancia / 250.0  # frente de 250 km por ano, registro no instante da chegada
    esforco = gerador.lognormal(0, 1, 200)
    for nome, funcao in frente.ESTIMADORES.items():
        assert funcao(distancia, ano, esforco) == pytest.approx(250.0, rel=0.02), nome


def test_envelope_so_guarda_os_recordes():
    anos, maximo = frente.envelope([10, 5, 30, 20, 40], [2000, 2001, 2002, 2003, 2004])
    assert anos.tolist() == [2000, 2002, 2004]
    assert maximo.tolist() == [10, 30, 40]


def test_preenchimento_engana_a_media_mas_nao_o_quantil_do_ano():
    """Com células sendo ocupadas atrás da frente, a média da distância por ano subestima a frente."""
    gerador = np.random.default_rng(2)
    media, quantil = [], []
    for _ in range(30):
        s = frente.simular_invasao(250.0, gerador, preenchimento=3.0)
        media.append(frente.velocidade_media(s["distancia"], s["ano"]))
        quantil.append(frente.velocidade_quantil_ano(s["distancia"], s["ano"]))
    assert np.mean(media) < 0.95 * 250.0
    assert abs(np.mean(quantil) / 250.0 - 1) < 0.03


def test_simulacao_com_deteccao_perfeita_registra_no_ano_da_chegada():
    s = frente.simular_invasao(200.0, np.random.default_rng(3), celulas=100, distancia_maxima=2000.0, anos=30)
    assert s["celulas_vistas"] == 100
    assert np.all(s["ano"] == np.ceil(s["distancia"] / 200.0))


def test_bootstrap_contem_a_velocidade_real():
    s = frente.simular_invasao(250.0, np.random.default_rng(4), preenchimento=3.0)
    inferior, superior = frente.bootstrap(s["distancia"], s["ano"], s["esforco"], frente.ESTIMADORES["Frente: quantil 0,10 do ano"], repeticoes=120)
    assert inferior < 250.0 < superior
