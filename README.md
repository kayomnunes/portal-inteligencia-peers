# Portal de Inteligência Peers

Protótipo do portal da área de Research & Insights: Radar, Finanças dos players, Indicadores setoriais,
Movimentos estratégicos, Acervo Peers e Agenda setorial, filtráveis por indústria e offering.

O portal se atualiza sozinho: o GitHub Actions roda os scripts em Python todo dia, busca os dados em fontes
públicas (feeds de notícias, Banco Central, IBGE) e grava no **Supabase**. O GitHub Pages publica só a
página. Para ver os dados, a pessoa entra com um **código enviado ao e-mail @peers.com.br**; e-mails de
outros domínios não recebem código nem dados.

## Estrutura

```
Frontend/
  index.html            a página do portal: tela de login + interface (os dados vêm do Supabase)
  dados/                cópia local dos dados (fora do repositório; usada pela carga inicial e por Finanças)
Backend/
  atualizar_portal.py   roda as atualizações respeitando a cadência de cada tipo de dado
  atualizar_noticias.py Radar e Movimentos, a partir dos feeds RSS
  atualizar_agenda.py   Agenda, a partir do calendário
  atualizar_indicadores.py  Indicadores setoriais, a partir do Banco Central (SGS) e do IBGE (SIDRA)
  enviar_dados.py       envia arquivos de Frontend/dados para o Supabase (carga inicial e Finanças)
  validar_fontes.py     testa se cada fonte de notícias tem feed ativo (rodar uma vez por mês)
  relatorio_fontes.md   resultado da última validação
  comum.py              funções compartilhadas, inclusive a leitura e gravação no Supabase
  config/               o que a R&I pode ajustar sem mexer no código (ver abaixo)
Supabase/
  configuracao.sql      tabela, regras de acesso e trava do domínio (rodar uma vez no Supabase)
.github/workflows/portal.yml  o agendamento e a publicação
```

## Como o acesso funciona

- Os dados ficam na tabela `secoes` do Supabase, uma linha por seção (radar, agenda, valor1000...).
- A página pede os dados ao Supabase; as regras do banco (RLS) só entregam a quem fez login com e-mail
  `@peers.com.br`. A URL e a chave pública no `index.html` podem ser vistas por qualquer um: sozinhas não
  abrem nada.
- O cadastro é automático no primeiro login; uma trava no banco recusa e-mails de outros domínios.
- A sessão fica salva no navegador: o código só é pedido no primeiro acesso de cada navegador, depois de
  "Sair" ou com os dados do navegador limpos.
- Para tirar o acesso de alguém na hora: Supabase > Authentication > Users > apagar o usuário.
- Para trocar o domínio: `Supabase/configuracao.sql` (função `dominio_permitido`) e `DOMINIO` no `index.html`.

## O que se atualiza e quando

| Dado | Fonte | Cadência |
|---|---|---|
| Radar e Movimentos | Feeds RSS de 54 veículos validados (`config/fontes_noticias.json`) | Diária |
| Agenda | Calendário em `config/calendario.json` | Diária (tira o que passou) |
| Indicadores setoriais | Banco Central e IBGE (`config/indicadores_fontes.json`) | Semanal |
| Finanças · companhias abertas | Reports trimestrais da R&I | Manual, a cada trimestre |
| Finanças · Valor 1000 | Planilha do ranking | Manual, uma vez por ano |
| Acervo | Ilustrativo | — |

Sem IA, Radar e Movimentos não têm resumo próprio, "Por que importa", Ângulo Peers nem Leitura Peers; a
indústria, a divisão, os temas e a offering de cada notícia vêm de palavras-chave.

## Ajustes sem programar (pasta Backend/config)

- `fontes_noticias.json`: incluir ou tirar um veículo (precisa ter feed RSS ativo).
- `fontes_candidatas.json`: fontes testadas por `validar_fontes.py`; inclua aqui uma fonte nova para testá-la antes.
- `classificacao.json`: palavras-chave de indústrias, temas, offerings, tipos de movimento e exclusões.
- `calendario.json`: eventos da Agenda; use `"recorrencia": "anual"` para eventos que se repetem.
- `indicadores_fontes.json`: ligar um indicador a uma série do Banco Central ou do IBGE.

Depois de editar um arquivo pelo site do GitHub, rode a atualização manualmente: aba **Actions** >
**Atualizar e publicar o portal** > **Run workflow**.

## Rodar os scripts no computador

Os scripts gravam no Supabase quando as duas variáveis abaixo estão definidas (no PowerShell, valem até
fechar a janela). Pegue os valores em Supabase > Project Settings > API (a chave é a **secreta**:
`service_role` ou `secret`; nunca a coloque no `index.html` nem no repositório).

```
$env:SUPABASE_URL = "https://<seu-projeto>.supabase.co"
$env:SUPABASE_SERVICE_KEY = "<chave secreta>"
cd Backend
python atualizar_portal.py --forcar
```

Sem as variáveis, os scripts leem e gravam os arquivos de `Frontend/dados` (bom para testar sem mexer no
Supabase).

**Atualizar Finanças** (trimestral / anual): edite `Frontend/dados/companhias_abertas.json` ou
`Frontend/dados/valor1000.json` e envie só o arquivo alterado, com as variáveis definidas:

```
python enviar_dados.py companhias_abertas
```

## Testar a página no computador

Rode um servidor local na pasta Frontend e acesse http://localhost:8000:

```
cd Frontend
python -m http.server 8000
```

Inclua `http://localhost:8000` em Supabase > Authentication > URL Configuration > Redirect URLs.

## Observações

- O repositório é público (exigência do GitHub Pages no plano gratuito), mas os dados não estão nele: só
  o código e as configurações em `Backend/config`.
- O GitHub pausa agendamentos de repositórios públicos sem atividade por 60 dias. Se a pausa acontecer,
  reative em Actions.
- O plano gratuito do Supabase pausa projetos sem uso por cerca de uma semana; as atualizações diárias
  mantêm o projeto ativo. Se pausar, reative no painel do Supabase.
