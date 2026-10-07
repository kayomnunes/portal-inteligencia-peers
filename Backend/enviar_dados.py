"""Envia arquivos de Frontend/dados para o Supabase, substituindo a versão que está lá.

Usos:
  - Carga inicial, uma vez, logo depois de rodar Supabase/configuracao.sql:
        python enviar_dados.py --todos
  - Atualizações manuais (Finanças a cada trimestre, Valor 1000 uma vez por ano): edite o arquivo em
    Frontend/dados e envie só ele:
        python enviar_dados.py companhias_abertas
        python enviar_dados.py valor1000

Cuidado com --todos depois da carga inicial: radar, movimentos, agenda, indicadores e edicao são
atualizados todo dia pelo GitHub, e a cópia do seu computador provavelmente está desatualizada.

Precisa das variáveis SUPABASE_URL e SUPABASE_SERVICE_KEY (ver README).
"""
import sys

from comum import DADOS, gravar_dado, ler_json, log, usa_supabase


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    if not usa_supabase():
        sys.exit("Defina SUPABASE_URL e SUPABASE_SERVICE_KEY antes de rodar (ver README).")
    nomes = sorted(p.stem for p in DADOS.glob("*.json")) if args == ["--todos"] else args
    for nome in nomes:
        caminho = DADOS / f"{nome}.json"
        if not caminho.exists():
            sys.exit(f"Arquivo não encontrado: {caminho}")
        gravar_dado(nome, ler_json(caminho))
        log(f"enviado: {nome}")


if __name__ == "__main__":
    main()
