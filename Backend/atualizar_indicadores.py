"""Atualiza os Indicadores setoriais ligados a séries públicas (config/indicadores_fontes.json).

Conectores: Banco Central (SGS) e IBGE (SIDRA). O valor mais recente vira o número do card, e a
variação é calculada contra o mesmo período do ano anterior. Indicadores sem série configurada
continuam com valor de exemplo; os sem fonte pública ficam marcados como sem atualização automática.
"""
from datetime import date, timedelta

from comum import CONFIG, agora, baixar_json, gravar_dado, ler_dado, ler_json, log, registrar_atualizacao

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def serie_sgs(codigo, n):
    """Últimos n valores mensais de uma série do Banco Central: [(date, valor)].

    A API limita "ultimos" a 20 pontos, então a consulta usa uma janela de datas.
    """
    inicio = agora().date().replace(day=1)
    for _ in range(n + 2):
        inicio = (inicio - timedelta(days=1)).replace(day=1)
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json"
           f"&dataInicial={inicio:%d/%m/%Y}&dataFinal={agora():%d/%m/%Y}")
    pontos = []
    for p in baixar_json(url):
        d, m, a = p["data"].split("/")
        pontos.append((date(int(a), int(m), int(d)), float(p["valor"])))
    return sorted(pontos)[-n:]


def serie_sidra(consulta, n):
    """Últimos n valores de uma consulta SIDRA do IBGE: [(date, valor)]."""
    dados = baixar_json(f"https://apisidra.ibge.gov.br/values/{consulta}/p/last%20{n}")
    cabecalho, linhas = dados[0], dados[1:]
    chave_periodo = next(k for k, v in cabecalho.items() if k.endswith("C") and v.startswith(("Mês", "Trimestre", "Ano")))
    pontos = []
    for l in linhas:
        cod = l[chave_periodo]          # ex.: 202608
        try:
            valor = float(l["V"])
        except ValueError:              # "..." ou "-": sem dado no período
            continue
        pontos.append((date(int(cod[:4]), int(cod[4:6]) if len(cod) >= 6 else 12, 1), valor))
    return sorted(pontos)


def calcular(cfg):
    precisa = 24 if cfg.get("acumular_12m") else 13
    pontos = serie_sgs(cfg["codigo"], precisa) if cfg["conector"] == "sgs" else serie_sidra(cfg["consulta"], precisa)
    if not pontos:
        raise ValueError("a fonte não devolveu valores para o período")
    if cfg.get("acumular_12m"):
        def acumulado(fim):
            fator = 1.0
            for _, v in pontos[fim - 11:fim + 1]:
                fator *= 1 + v / 100
            return (fator - 1) * 100
        atual, anterior = acumulado(len(pontos) - 1), acumulado(len(pontos) - 13)
    else:
        atual, anterior = pontos[-1][1], pontos[-13][1] if len(pontos) >= 13 else None
    escala = cfg.get("escala", 1)
    atual /= escala
    var = None
    if anterior is not None:
        anterior = anterior / escala if not cfg.get("acumular_12m") else anterior
        var = (atual - anterior) if cfg["var"] == "pp" else ((atual / anterior - 1) * 100 if anterior else None)
    d = pontos[-1][0]
    return atual, var, f"{ABREV[d.month - 1]}/{d.year}"


def arredondar(v):
    return round(v, 0 if abs(v) >= 100 else 1 if abs(v) >= 10 else 2)


def main():
    series = ler_json(CONFIG / "indicadores_fontes.json")["series"]
    segmentos = ler_dado("indicadores")
    indice = {(s["segmento"], i["nome"]): i for s in segmentos for i in s["indicadores"]}
    ok = falhas = 0
    for cfg in series:
        alvo = indice.get((cfg["segmento"], cfg["indicador"]))
        if not alvo:
            log(f"  não encontrado no portal: {cfg['segmento']} / {cfg['indicador']}")
            falhas += 1
            continue
        try:
            valor, var, periodo = calcular(cfg)
        except Exception as e:
            log(f"  falha em {cfg['indicador']}: {str(e)[:100]}")
            falhas += 1
            continue
        alvo.update({"valor": arredondar(valor), "periodo": periodo, "status": "real",
                     "atualizadoEm": agora().strftime("%Y-%m-%d")})
        if var is not None:
            alvo["var"] = round(var, 1)
        ok += 1
    gravar_dado("indicadores", segmentos)
    log(f"Indicadores: {ok} atualizados com a fonte, {falhas} com falha")
    registrar_atualizacao("indicadores")


if __name__ == "__main__":
    main()
