"""Roda as atualizações do portal respeitando a cadência de cada tipo de dado.

Chamado todo dia pelo GitHub Actions. Cada tipo de dado só é atualizado quando passou o intervalo
definido em CADENCIA (poupa chamadas às fontes). Use --forcar para atualizar tudo de uma vez.

    python Backend/atualizar_portal.py            # respeita a cadência
    python Backend/atualizar_portal.py --forcar   # atualiza tudo agora
"""
import sys
from datetime import datetime, timedelta

import atualizar_agenda
import atualizar_indicadores
import atualizar_noticias
from comum import agora, ler_dado, log

# intervalo mínimo entre duas atualizações de cada tipo de dado
CADENCIA = {
    "noticias": timedelta(hours=20),     # Radar e Movimentos: diária
    "agenda": timedelta(hours=20),       # Agenda: diária (só tira o que passou e roda os eventos anuais)
    "indicadores": timedelta(days=7),    # Indicadores: semanal (as fontes publicam mensalmente)
}
TAREFAS = {
    "noticias": atualizar_noticias.main,
    "agenda": atualizar_agenda.main,
    "indicadores": atualizar_indicadores.main,
}


def vencido(chave, ultimas):
    if chave not in ultimas:
        return True
    return agora() - datetime.fromisoformat(ultimas[chave]) >= CADENCIA[chave]


def main():
    forcar = "--forcar" in sys.argv
    ultimas = ler_dado("edicao").get("atualizadoEm", {})
    erros = 0
    for chave, tarefa in TAREFAS.items():
        if forcar or vencido(chave, ultimas):
            log(f"== {chave}")
            try:
                tarefa()
            except Exception as e:   # uma fonte fora do ar não impede as outras atualizações
                erros += 1
                log(f"ERRO em {chave}: {e}")
        else:
            log(f"== {chave}: ainda dentro da cadência, nada a fazer")
    sys.exit(1 if erros == len(TAREFAS) else 0)


if __name__ == "__main__":
    main()
