# Arquitetura

## Visão geral

O sistema tem três camadas que se comunicam apenas por arquivos e pelo banco:

1. **Automação** (`uber_reports.automation`): produz arquivos de relatório em
   `data/downloads/`. Não sabe nada sobre o banco.
2. **ETL** (`uber_reports.etl`): lê arquivos (relatórios e planilha de lotação) e escreve no
   SQLite. Não sabe nada sobre navegador nem sobre apresentação.
3. **Dashboard** (`uber_reports.dashboard`): lê o SQLite e escreve um HTML. Não sabe de onde
   os dados vieram.

`cli.py` amarra as camadas em subcomandos e `config.py` fornece um objeto `Settings`
imutável a todas elas.

## Fluxo da extração

```text
save-session uber ──► data/sessions/uber.session.json   (uma vez)
save-session mail ──► data/sessions/mail.session.json   (uma vez)

extract
  ├─ contexto Uber (storage_state)
  │    para cada empresa:
  │      go_home → select_company → open_reports → request_report(período)
  └─ contexto webmail (storage_state)
       para cada empresa, até wait_max_seconds:
         search(assunto, hoje) → open_matching_message(palavras-chave)
           → download_report (remove target=_blank, expect_download)
```

O período padrão é o mês fechado anterior (`report.period = previous_month`), que é o
ciclo natural de conciliação de despesas. `last_n_days` cobre reprocessos parciais.

Quando qualquer etapa falha, uma screenshot é salva em `data/downloads/error_screenshot.png`
e a exceção sobe com a mensagem do ponto exato da falha (qual botão, qual empresa).

### Por que sessões e não credenciais

- Login automatizado esbarra em 2FA, captcha e bloqueio por comportamento suspeito.
- Guardar senha em configuração é um risco desnecessário.
- O `storage_state` do Playwright captura cookies e storage de um login feito por uma
  pessoa e vale por semanas. Renovar é rodar `save-session` de novo.

### Por que normalizar todo texto lido

O portal alterna idioma e acentuação nos rótulos ("Relatórios", "Relatorios", "Reports").
Comparar `normalize_text(texto_da_pagina)` com `normalize_text(rótulo_esperado)` torna os
seletores por texto estáveis. Quando o texto não basta, há fallback por papel (`role`), por
`data-testid` e por URL direta.

## Fluxo do ETL

```text
ingest
  find_report_files(data/downloads) → read_report (detecta cabeçalho e separador)
    → normalize_rides (parse BRL, hora, data; person_id; ride_id = SHA-1)
    → load_reports (concatena, remove ride_id repetido)
    → upsert_rides (INSERT ... ON CONFLICT DO UPDATE)

load-mapping
  read_mapping_workbook → normalize_assignments (aba de pessoas + aba de histórico)
    → replace_assignments (recria employees e assignment_history)
```

Idempotência: `ride_id` é a chave primária, calculada a partir de pessoa, data, hora,
valor, serviço e cidade. Rodar `ingest` duas vezes com os mesmos arquivos deixa o banco
igual. O teste `test_ingest_is_idempotent` garante isso.

## Fluxo do dashboard

`queries.load_enriched_rides` executa um único SQL com o join temporal e enriquece o
resultado (nome apresentável, mês, período do dia). `render.build_dashboard` embute os
registros como JSON no template e inclui CSS e JavaScript inline, produzindo um arquivo
autossuficiente. Toda a interatividade (filtros cruzados, gráficos, tabelas) acontece no
navegador, em `assets/app.js`.

## Tratamento de erros

- Configuração inválida: `ConfigError` com mensagem apontando o campo. A CLI encerra com
  código 2.
- Arquivo ou sessão ausente, cabeçalho não encontrado, aba obrigatória ausente: exceções
  com mensagem específica. A CLI registra e encerra com código 1.
- Linhas de relatório sem nome, data ou valor são descartadas e contadas no log de debug,
  nunca inseridas parcialmente.
