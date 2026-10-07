"""Atualiza a Agenda setorial a partir do calendário mantido em config/calendario.json.

Sem IA não dá para extrair datas de eventos de dentro das notícias, então a Agenda vem de um
calendário em arquivo. Eventos com "recorrencia": "anual" passam para o ano seguinte quando a data passa.
Eventos já realizados saem da Agenda automaticamente.
"""
from datetime import date

from comum import CONFIG, gravar_dado, gravar_json, hoje_iso, ler_json, log, registrar_atualizacao


def proxima_data(iso, hoje):
    d = date.fromisoformat(iso)
    while d.isoformat() < hoje:
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:          # 29 de fevereiro
            d = d.replace(year=d.year + 1, day=28)
    return d.isoformat()


def main():
    hoje = hoje_iso()
    caminho = CONFIG / "calendario.json"
    cal = ler_json(caminho)
    mudou = False
    for e in cal["eventos"]:
        if e.get("recorrencia") == "anual" and e["data"] < hoje:
            e["data"] = proxima_data(e["data"], hoje)
            mudou = True
    if mudou:
        gravar_json(caminho, cal)
    agenda = sorted((e for e in cal["eventos"] if e["data"] >= hoje), key=lambda e: e["data"])
    gravar_dado("agenda", agenda)
    log(f"Agenda: {len(agenda)} entradas futuras de {len(cal['eventos'])} no calendário")
    registrar_atualizacao("agenda")


if __name__ == "__main__":
    main()
