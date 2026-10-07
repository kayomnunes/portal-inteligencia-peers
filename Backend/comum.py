"""Funções compartilhadas pelos scripts de atualização do portal. Só usa a biblioteca padrão do Python."""
import gzip
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "Frontend" / "dados"
CONFIG = Path(__file__).resolve().parent / "config"
FUSO_BR = timezone(timedelta(hours=-3))

# Banco de dados do portal. Com as duas variáveis definidas (no GitHub, pelos Secrets), os dados ficam no
# Supabase; sem elas (teste no computador), ficam nos arquivos de Frontend/dados.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_CHAVE = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
TABELA = "secoes"


def agora():
    return datetime.now(FUSO_BR)


def hoje_iso():
    return agora().strftime("%Y-%m-%d")


def ler_json(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def gravar_json(caminho, obj):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def baixar(url, tentativas=3, timeout=40):
    """Baixa uma URL e devolve bytes; tenta de novo em caso de falha passageira."""
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (PortalInteligenciaPeers; atualizacao automatica)",
                "Accept-Encoding": "gzip",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                bruto = r.read()
            if bruto[:2] == b"\x1f\x8b":
                bruto = gzip.decompress(bruto)
            return bruto
        except Exception as e:  # rede instável: espera e tenta de novo
            erro = e
            time.sleep(3 * (i + 1))
    raise erro


def baixar_json(url, **kw):
    return json.loads(baixar(url, **kw).decode("utf-8"))


def normalizar(texto):
    """Minúsculas e sem acentos, para comparar com as palavras-chave."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " " + re.sub(r"\s+", " ", texto.lower()) + " "


def identificador(prefixo, texto):
    return prefixo + hashlib.sha1(texto.encode("utf-8")).hexdigest()[:10]


def usa_supabase():
    if SUPABASE_URL and SUPABASE_CHAVE:
        return True
    if os.environ.get("GITHUB_ACTIONS"):   # no GitHub os dados não ficam em arquivo: falta configurar
        raise RuntimeError("SUPABASE_URL e SUPABASE_SERVICE_KEY não estão nos Secrets do repositório")
    return False


def _supabase(metodo, caminho, corpo=None, cabecalhos=None):
    """Chama a API do Supabase com a chave secreta (ignora as regras de acesso: só para o Backend)."""
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{caminho}", method=metodo,
        data=None if corpo is None else json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
        headers={
            "apikey": SUPABASE_CHAVE,
            "Authorization": f"Bearer {SUPABASE_CHAVE}",
            "Content-Type": "application/json",
            "User-Agent": "PortalInteligenciaPeers (atualizacao automatica)",
            **(cabecalhos or {}),
        })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            bruto = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase respondeu {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None
    return json.loads(bruto) if bruto else None


def ler_dado(nome):
    """Lê uma seção do portal (radar, agenda, valor1000...)."""
    if not usa_supabase():
        return ler_json(DADOS / f"{nome}.json")
    linhas = _supabase("GET", f"{TABELA}?nome=eq.{nome}&select=conteudo")
    if not linhas:
        raise KeyError(f"a seção '{nome}' não existe no Supabase (rode enviar_dados.py para criá-la)")
    return linhas[0]["conteudo"]


def gravar_dado(nome, obj):
    """Grava uma seção do portal, substituindo a versão anterior."""
    if not usa_supabase():
        gravar_json(DADOS / f"{nome}.json", obj)
        return
    _supabase("POST", f"{TABELA}?on_conflict=nome",
              [{"nome": nome, "conteudo": obj, "atualizado_em": agora().isoformat()}],
              {"Prefer": "resolution=merge-duplicates,return=minimal"})


def registrar_atualizacao(chave):
    """Guarda em edicao quando cada tipo de dado foi atualizado pela última vez."""
    edicao = ler_dado("edicao")
    edicao.setdefault("atualizadoEm", {})[chave] = agora().isoformat(timespec="minutes")
    gravar_dado("edicao", edicao)


def log(msg):
    print(f"[{agora():%H:%M:%S}] {msg}", flush=True)
