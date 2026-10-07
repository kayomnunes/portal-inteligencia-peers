"""Atualiza o Radar e os Movimentos estratégicos a partir dos feeds RSS das fontes.

Sem IA: a indústria, a divisão, os temas e a offering de cada notícia vêm de palavras-chave
(config/classificacao.json). Resumo, "Por que importa", Ângulo Peers e Leitura Peers ficam vazios.
"""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from comum import (CONFIG, FUSO_BR, agora, baixar, gravar_dado, identificador, ler_dado,
                   ler_json, log, normalizar, registrar_atualizacao)

JANELA_DIAS = 3          # notícias publicadas nos últimos N dias entram como candidatas
TETO_POR_DIVISAO = 3     # regra editorial: até 3 itens por divisão no Radar
RADAR_VALIDADE = 30      # itens mais antigos que isso saem do Radar
MOVIMENTOS_VALIDADE = 730  # Movimentos guardam até 24 meses de histórico

ATOM = "{http://www.w3.org/2005/Atom}"


def texto_limpo(bruto, limite=None):
    t = re.sub(r"<[^>]+>", " ", html.unescape(bruto or ""))
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s*(The post|O post|Leia mais|Continue lendo).*$", "", t)
    if limite and len(t) > limite:
        corte = t[:limite]
        fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
        t = corte[:fim + 1] if fim > limite * 0.5 else corte.rsplit(" ", 1)[0] + "…"
    return t


def data_do_item(texto):
    if not texto:
        return None
    try:
        return parsedate_to_datetime(texto).astimezone(FUSO_BR)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(FUSO_BR)
    except ValueError:
        return None


def ler_feed(fonte, tentativas=3, timeout=25):
    """Devolve as notícias de um feed RSS ou Atom como dicionários simples."""
    bruto = baixar(fonte["url"], tentativas=tentativas, timeout=timeout)
    # alguns feeds trazem lixo depois do fechamento do XML: corta no último </rss> ou </feed>
    for fim in (b"</rss>", b"</feed>"):
        pos = bruto.rfind(fim)
        if pos != -1:
            bruto = bruto[:pos + len(fim)]
            break
    raiz = ET.fromstring(bruto.strip())
    itens = []
    for it in raiz.iter("item"):
        itens.append({"titulo": it.findtext("title"), "link": it.findtext("link"),
                      "data": it.findtext("pubDate"), "resumo": it.findtext("description")})
    for it in raiz.iter(ATOM + "entry"):
        link = it.find(ATOM + "link")
        itens.append({"titulo": it.findtext(ATOM + "title"), "link": link.get("href") if link is not None else None,
                      "data": it.findtext(ATOM + "published") or it.findtext(ATOM + "updated"),
                      "resumo": it.findtext(ATOM + "summary")})
    return itens


_REGEX = {}


def _padrao(palavra):
    """Palavra-chave como palavra inteira ("agua" não casa com "aguarda")."""
    p = palavra.strip()
    if p not in _REGEX:
        _REGEX[p] = re.compile(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])")
    return _REGEX[p]


def pontuar(texto_titulo, texto_resumo, palavras):
    pontos = 0
    for p in palavras:
        rx = _padrao(p)
        pontos += 2 * len(rx.findall(texto_titulo)) + len(rx.findall(texto_resumo))
    return pontos


def melhor(titulo, resumo, dicionario):
    placar = {k: pontuar(titulo, resumo, v) for k, v in dicionario.items()}
    chave = max(placar, key=placar.get)
    return (chave, placar[chave]) if placar[chave] > 0 else (None, 0)


PONTUACAO_MINIMA_GERAL = 2   # fontes gerais: a palavra-chave precisa estar no título ou aparecer 2 vezes no resumo


def classificar(noticia, fonte, cfg):
    t, r = normalizar(noticia["titulo"]), normalizar(noticia["resumo"])
    if any(_padrao(p).search(t) for p in cfg["excluir"]):
        return None  # política partidária, crime, esporte etc.
    if fonte["padrao"]:
        # fonte setorial: a indústria é a da fonte; as palavras-chave só escolhem a divisão dentro dela
        industria = fonte["padrao"][0]
        da_industria = {k: v for k, v in cfg["industrias"].items() if k.startswith(industria + "|")}
        chave, _ = melhor(t, r, da_industria)
        divisao = chave.split("|")[1] if chave else fonte["padrao"][1]
    else:
        chave, pontos = melhor(t, r, cfg["industrias"])
        if not chave or pontos < PONTUACAO_MINIMA_GERAL:
            return None  # fonte geral sem sinal setorial claro: fica de fora
        industria, divisao = chave.split("|")
    temas = [tema for tema, pal in cfg["temas"].items() if pontuar(t, r, pal) > 0][:3]
    offering, _ = melhor(t, r, cfg["offerings"])
    alta = any(_padrao(p).search(t) for p in cfg["relevancia_alta"])
    return industria, divisao, temas, offering or "", "alta" if alta else "media"


def coletar(fontes, cfg):
    limite = agora() - timedelta(days=JANELA_DIAS)
    futuro = agora() + timedelta(hours=12)   # alguns feeds trazem eventos e webinars com data futura
    candidatos = []
    for fonte in fontes:
        try:
            itens = ler_feed(fonte)
        except Exception as e:
            log(f"  falha em {fonte['nome']}: {str(e)[:80]}")
            continue
        novos = 0
        for n in itens:
            quando = data_do_item(n["data"])
            if not n["titulo"] or not n["link"] or not quando or quando < limite or quando > futuro:
                continue
            n["titulo"] = texto_limpo(n["titulo"])
            n["resumo"] = texto_limpo(n["resumo"], 320)
            n["quando"] = quando
            n["fonte"] = fonte
            candidatos.append(n)
            novos += 1
        log(f"  {fonte['nome']}: {novos} notícias recentes")
    return candidatos


def montar_radar(candidatos, cfg):
    itens = []
    for n in candidatos:
        c = classificar(n, n["fonte"], cfg)
        if not c:
            continue
        industria, divisao, temas, offering, relevancia = c
        itens.append({
            "manchete": n["titulo"], "resumo": n["resumo"], "porQueImporta": "", "anguloPeers": "",
            "industria": industria, "divisao": divisao, "offering": offering, "temas": temas,
            "relevancia": relevancia, "fonte": n["fonte"]["nome"], "url": n["link"],
            "data": n["quando"].strftime("%Y-%m-%d"), "id": identificador("r", n["link"]), "ia": False,
        })
    return itens


def empresas_conhecidas(cfg):
    """Nomes de empresas (Valor 1000 e companhias abertas) para identificar o player de um movimento."""
    valor = ler_dado("valor1000")
    campos = valor["campos"]
    i_nome, i_ind, i_div = campos.index("nome"), campos.index("ind"), campos.index("div")
    nomes = {}
    for linha in valor["linhas"]:
        nomes[linha[i_nome]] = (linha[i_ind], linha[i_div])
    for e in ler_dado("companhias_abertas")["empresas"]:
        nomes[e["nome"]] = (e["ind"], e["div"])
    ambiguos = set(cfg["nomes_ambiguos"])
    padroes, vistos = [], set()
    for nome, (ind, div) in nomes.items():
        # a manchete costuma usar o nome curto: "Grupo Carrefour Brasil" aparece como "Carrefour"
        curto = re.sub(r"^Grupo\s+", "", nome)
        curto = re.sub(r"\s+(Brasil|do Brasil|Brazil|Participações|Holding|S\.A\.)$", "", curto)
        for variante in {nome, curto}:
            if variante in ambiguos or len(variante) < 3 or variante in vistos:
                continue
            vistos.add(variante)
            padroes.append((re.compile(r"(?<![\w-])" + re.escape(variante) + r"(?![\w-])"), curto, ind, div))
    padroes.sort(key=lambda x: -len(x[1]))  # nomes mais longos primeiro ("Banco do Brasil" antes de "Brasil")
    return padroes


def montar_movimentos(candidatos, cfg):
    padroes = empresas_conhecidas(cfg)
    itens = []
    for n in candidatos:
        titulo_norm = normalizar(n["titulo"])
        tipo = next((t for t, pal in cfg["movimentos"].items() if any(_padrao(p).search(titulo_norm) for p in pal)), None)
        if not tipo:
            continue
        achado = next(((nome, ind, div) for rx, nome, ind, div in padroes if rx.search(n["titulo"])), None)
        if not achado:
            continue
        nome, ind, div = achado
        valor = re.search(r"(?:R\$|US\$)\s?[\d.,]+\s?(?:mil|mi|milh[õo]es|bi|bilh[õo]es|bilhão|milhão)", n["titulo"] + " " + n["resumo"])
        itens.append({
            "player": nome, "industria": ind, "divisao": div,
            "offering": cfg["offering_por_tipo_de_movimento"].get(tipo, ""),
            "data": n["quando"].strftime("%Y-%m-%d"), "tipo": tipo, "tese": n["titulo"],
            "valor": valor.group(0) if valor else "Não divulgado", "fonte": n["fonte"]["nome"],
            "url": n["link"], "leitura": "", "id": identificador("m", n["link"]), "ia": False,
        })
    return itens


def juntar(antigos, novos, validade_dias):
    """Une os itens já publicados com os novos, sem repetir a mesma notícia."""
    por_url = {i.get("url") or i["id"]: i for i in antigos}
    for i in novos:
        por_url.setdefault(i["url"], i)
    corte = (agora() - timedelta(days=validade_dias)).strftime("%Y-%m-%d")
    return [i for i in por_url.values() if i["data"] >= corte]


def aplicar_teto(itens):
    """Mantém os itens mais recentes de cada divisão, até o teto editorial."""
    ordem = sorted(itens, key=lambda i: (i["data"], i.get("relevancia") == "alta"), reverse=True)
    contagem, final = {}, []
    for i in ordem:
        k = (i["industria"], i.get("divisao"))
        if contagem.get(k, 0) < TETO_POR_DIVISAO:
            contagem[k] = contagem.get(k, 0) + 1
            final.append(i)
    return final


def main():
    fontes = ler_json(CONFIG / "fontes_noticias.json")["fontes"]
    cfg = ler_json(CONFIG / "classificacao.json")
    log(f"Lendo {len(fontes)} feeds")
    candidatos = coletar(fontes, cfg)

    radar_novo = montar_radar(candidatos, cfg)
    radar = aplicar_teto(juntar(ler_dado("radar"), radar_novo, RADAR_VALIDADE))
    gravar_dado("radar", radar)
    log(f"Radar: {len(radar_novo)} notícias classificadas, {len(radar)} publicadas")

    mov_novos = montar_movimentos(candidatos, cfg)
    movimentos = juntar(ler_dado("movimentos"), mov_novos, MOVIMENTOS_VALIDADE)
    movimentos.sort(key=lambda m: m["data"], reverse=True)
    gravar_dado("movimentos", movimentos[:400])
    log(f"Movimentos: {len(mov_novos)} candidatos novos, {len(movimentos[:400])} no histórico")

    edicao = ler_dado("edicao")
    edicao["hoje"] = agora().strftime("%Y-%m-%d")
    gravar_dado("edicao", edicao)
    registrar_atualizacao("noticias")


if __name__ == "__main__":
    main()
