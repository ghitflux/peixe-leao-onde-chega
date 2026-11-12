import numpy as np
import pytest

from peixe_leao import espalhamento as esp


def _costa_reta(n: int = 60, passo_km: float = 100.0) -> np.ndarray:
    posicao = np.arange(n) * passo_km
    return np.abs(posicao[:, None] - posicao[None, :])


def test_risco_de_duas_celulas_bate_com_a_conta_a_mao():
    distancias = np.array([[0.0, 100.0], [100.0, 0.0]])
    theta = np.array([np.log(0.5), np.log(100.0), 1.0, np.log(0.01)])
    h = esp.risco(theta, distancias, ocupada=np.array([[True, False]]), esforco=np.array([[0.0, 3.0]]))
    # célula 1: pressão = exp(-100/100); risco = (0,01 + 0,5 * e^-1) * (1 + 3)^1
    assert h[0, 1] == pytest.approx((0.01 + 0.5 * np.exp(-1.0)) * 4.0)
    # célula 0 (ela mesma ocupada): pressão = exp(0) = 1
    assert h[0, 0] == pytest.approx(0.01 + 0.5)


def _painel_minimo(primeiro_da_celula_1: float) -> esp.Painel:
    """A célula 0 é a semente (registro em 2000); a célula 1 fica em risco em 2001 e 2002."""
    return esp.Painel(
        anos=np.array([2001, 2002]),
        distancias=np.array([[0.0, 100.0], [100.0, 0.0]]),
        primeiro=np.array([2000.0, primeiro_da_celula_1]),
        esforco=np.zeros((2, 2)),
        habitat=np.array([0.0, 2.0]),
    )


def test_log_verossimilhanca_de_um_caso_minimo():
    theta = np.array([np.log(0.5), np.log(100.0), 0.0, np.log(0.01)])
    h = 0.01 + 0.5 * np.exp(-1.0)
    # passa 2001 sem registro e é registrada em 2002
    assert esp.log_verossimilhanca(theta, _painel_minimo(2002.0)) == pytest.approx(-h + np.log(1 - np.exp(-h)))
    # nunca é registrada: sobrevive aos dois anos
    assert esp.log_verossimilhanca(theta, _painel_minimo(np.nan)) == pytest.approx(-2 * h)


def test_log_verossimilhanca_com_fracao_suscetivel():
    forma = esp.Forma(suscetivel=True)
    theta = np.array([np.log(0.5), np.log(100.0), 0.0, np.log(0.01), -1.0, 0.5])  # pi = logística(-1 + 0,5 * 2) = 0,5
    h = 0.01 + 0.5 * np.exp(-1.0)
    com_registro = esp.log_verossimilhanca(theta, _painel_minimo(2002.0), forma)
    assert com_registro == pytest.approx(np.log(0.5) - h + np.log(1 - np.exp(-h)))
    sem_registro = esp.log_verossimilhanca(theta, _painel_minimo(np.nan), forma)
    assert sem_registro == pytest.approx(np.log(0.5 + 0.5 * np.exp(-2 * h)))


def test_suscetibilidade_atualizada_e_a_regra_de_bayes():
    forma = esp.Forma(suscetivel=True)
    theta = np.array([np.log(0.5), np.log(100.0), 0.0, np.log(0.01), -1.0, 0.5])
    h = 0.01 + 0.5 * np.exp(-1.0)
    sobrevivencia = np.exp(-2 * h)
    atualizada = esp.suscetibilidade_atualizada(theta, _painel_minimo(np.nan), forma)
    assert atualizada[0] == 1.0  # a semente tem registro
    assert atualizada[1] == pytest.approx(0.5 * sobrevivencia / (0.5 + 0.5 * sobrevivencia))
    assert atualizada[1] < 0.5  # dois anos ao lado de uma célula ocupada sem registro: menos provável que seja suscetível


def test_aptidao_termica_entra_na_suscetibilidade():
    forma = esp.Forma(suscetivel=False, termico=True)
    theta = np.array([0.0, 0.0, 0.0, 0.0, 14.0])
    pi = esp.suscetibilidade(theta, forma, habitat=None, tmin=np.array([5.0, 14.0, 25.0]), celulas=3)
    assert pi[0] < 0.001 and pi[1] == pytest.approx(0.5) and pi[2] > 0.999


def test_hessiana_numerica_de_uma_quadratica():
    A = np.array([[2.0, 0.5], [0.5, 1.0]])
    H = esp.hessiana_numerica(lambda x: 0.5 * x @ A @ x, np.array([0.3, -0.2]))
    assert np.allclose(H, A, atol=1e-5)


def _invasao_simulada(real: np.ndarray, celulas: int, gerador: np.random.Generator, suscetivel=None, habitat=None) -> esp.Painel:
    distancias = _costa_reta(celulas)
    esforco = gerador.lognormal(1.0, 1.0, celulas)
    inicio = np.zeros(celulas, bool)
    inicio[0] = True
    anos = np.arange(2001, 2031)
    primeiro = esp.simular(real, distancias, inicio, esforco, anos, 1, gerador, suscetivel=suscetivel)[0]
    primeiro[0] = 2000.0
    return esp.Painel(anos=anos, distancias=distancias, primeiro=primeiro, esforco=np.tile(esforco, (len(anos), 1)), habitat=habitat)


def test_ajuste_recupera_os_parametros_de_uma_invasao_simulada():
    real = np.array([np.log(0.6), np.log(150.0), 0.5, np.log(0.002)])
    painel = _invasao_simulada(real, 120, np.random.default_rng(0))
    ajuste = esp.ajustar(painel)
    assert ajuste["log_verossimilhanca"] >= esp.log_verossimilhanca(real, painel) - 1e-6
    assert np.exp(ajuste["theta"][1]) == pytest.approx(150.0, rel=0.5)  # alcance, em km
    assert ajuste["theta"][2] == pytest.approx(0.5, abs=0.3)  # elasticidade do esforço
    erro_padrao = np.sqrt(np.diag(ajuste["covariancia"]))
    assert abs(ajuste["theta"][1] - real[1]) < 3 * erro_padrao[1]


def test_ajuste_recupera_a_fracao_suscetivel():
    """Metade das células tem habitat ruim e quase nunca é suscetível; o ajuste precisa enxergar isso."""
    gerador = np.random.default_rng(1)
    celulas = 300
    habitat = np.where(gerador.random(celulas) < 0.5, 0.0, 4.0)
    pi = 1 / (1 + np.exp(-(-2.0 + 1.0 * habitat)))  # 0,12 no habitat ruim e 0,88 no bom
    real = np.array([np.log(0.6), np.log(300.0), 0.0, np.log(0.002)])
    painel = _invasao_simulada(real, celulas, gerador, suscetivel=pi, habitat=habitat)
    ajuste = esp.ajustar(painel, esp.Forma(suscetivel=True))
    estimado = esp.suscetibilidade(ajuste["theta"], esp.Forma(suscetivel=True), habitat, None, celulas)
    assert estimado[habitat == 0.0][0] == pytest.approx(0.12, abs=0.10)
    assert estimado[habitat == 4.0][0] == pytest.approx(0.88, abs=0.12)
    sem_fracao = esp.ajustar(painel)
    assert ajuste["aic"] < sem_fracao["aic"] - 10  # o termo se paga com folga


def test_simulacao_sem_contagio_e_sem_fundo_nao_registra_nada():
    theta = np.array([-16.0, np.log(100.0), 0.0, -20.0])
    inicio = np.zeros(10, bool)
    inicio[0] = True
    primeiro = esp.simular(theta, _costa_reta(10), inicio, np.zeros(10), np.arange(2001, 2011), 50, np.random.default_rng(1))
    assert np.isnan(primeiro).all()


def test_simulacao_chega_antes_as_celulas_proximas_e_respeita_a_suscetibilidade():
    inicio = np.zeros(30, bool)
    inicio[0] = True
    suscetivel = np.where(np.arange(30) < 15, 1.0, 0.0)  # a metade distante não pode ter registro
    theta = np.array([np.log(1.0), np.log(150.0), 0.0, -20.0])
    primeiro = esp.simular(theta, _costa_reta(30), inicio, np.zeros(30), np.arange(2001, 2041), 200, np.random.default_rng(2), suscetivel=suscetivel)
    chegou = ~np.isnan(primeiro)
    assert chegou[:, 1].mean() > 0.95
    assert np.nanmedian(primeiro[:, 3]) < np.nanmedian(primeiro[:, 10])
    assert not chegou[:, 15:].any()


def test_pressao_incremental_bate_com_a_conta_direta():
    """A simulação atualiza a pressão só com as células novas; o resultado tem de ser o da conta completa."""
    distancias = _costa_reta(25)
    inicio = np.zeros(25, bool)
    inicio[[0, 7]] = True
    theta = np.array([np.log(0.4), np.log(200.0), 0.0, np.log(0.01)])
    anos = np.arange(2001, 2011)
    primeiro = esp.simular(theta, distancias, inicio, np.zeros(25), anos, 40, np.random.default_rng(5))

    # a mesma simulação, com os mesmos sorteios, recalculando a pressão inteira a cada ano
    gerador = np.random.default_rng(5)
    registrada = np.tile(inicio, (40, 1))
    referencia = np.full(registrada.shape, np.nan)
    for ano in anos:
        p = 1 - np.exp(-esp.risco(theta, distancias, registrada, np.zeros(registrada.shape)))
        nova = ~registrada & (gerador.random(registrada.shape) < p)
        referencia[nova] = ano
        registrada |= nova
    assert np.array_equal(primeiro, referencia, equal_nan=True)
    assert np.isfinite(primeiro).sum() > 100


def test_celula_que_nao_e_fonte_nao_espalha():
    inicio = np.array([True, False, False, False, False, False])
    theta = np.array([np.log(5.0), np.log(100.0), 0.0, -20.0])
    primeiro = esp.simular(theta, _costa_reta(6), inicio, np.zeros(6), np.arange(2001, 2021), 100, np.random.default_rng(3), fonte=np.zeros(6, bool))
    assert np.isnan(primeiro).all()


def test_linhas_de_base():
    distancia_origem = np.array([0.0, 100.0, 200.0, 450.0, 1000.0])
    com_registro = np.array([True, True, False, False, False])
    previsto = esp.base_velocidade_constante(distancia_origem, com_registro, velocidade=100.0, corte=2010)
    # frente em 100 km; 200 km fica a 1 ano, 450 km a 4 anos (3,5 arredonda para cima), 1000 km a 9 anos
    assert previsto[2:].tolist() == [2011.0, 2014.0, 2019.0]
    distancias = np.abs(distancia_origem[:, None] - distancia_origem[None, :])
    vizinha = esp.base_vizinha(distancias, com_registro, corte=2010)
    assert vizinha[2:].tolist() == [2011.0, 2013.0, 2016.0]  # 100, 350 e 900 km da célula ocupada mais próxima


def test_auc_casos_conhecidos():
    assert esp.auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert esp.auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == 0.0
    assert esp.auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]) == 0.5
    assert esp.auc([0, 1, 0, 1], [0.1, 0.4, 0.35, 0.8]) == 1.0
    assert esp.auc([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]) == 0.75  # exemplo clássico
    assert np.isnan(esp.auc([1, 1], [0.2, 0.3]))


def test_brier_e_calibracao():
    assert esp.brier([1, 0], [1.0, 0.0]) == 0.0
    assert esp.brier([1, 0], [0.5, 0.5]) == 0.25
    linhas = esp.calibracao([0, 0, 1, 1], [0.05, 0.05, 0.9, 0.7])
    assert [linha["celulas"] for linha in linhas] == [2, 2]
    assert linhas[0]["observado"] == 0.0 and linhas[1]["observado"] == 1.0
    assert linhas[1]["previsto"] == pytest.approx(0.8)
