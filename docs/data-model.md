# Modelo de dados

## Tabelas

### `rides`

| Coluna | Tipo | Descrição |
| --- | --- | --- |
| `ride_id` | TEXT PK | SHA-1 de (pessoa, nome, sobrenome, data, hora original, valor, serviço, cidade) |
| `employee_id` | TEXT | Nome completo normalizado (sem acentos, caixa alta, espaços únicos) |
| `first_name`, `last_name` | TEXT | Como vieram do portal, apenas sem espaços nas pontas |
| `ride_date` | TEXT | `YYYY-MM-DD` |
| `request_hour` | INTEGER | 0 a 23, ou NULL quando a hora não pôde ser lida |
| `amount` | REAL | Valor total em BRL |
| `service`, `city` | TEXT | Categoria e cidade informadas pelo portal |
| `pickup_address`, `dropoff_address` | TEXT | Endereços, NULL quando ausentes |
| `company` | TEXT | Empresa lida do bloco de metadados do arquivo |
| `source_file` | TEXT | Nome do arquivo de origem, para auditoria |
| `loaded_at` | TEXT | Timestamp da carga |

### `employees`

| Coluna | Tipo | Descrição |
| --- | --- | --- |
| `employee_id` | TEXT PK | Mesma regra de `rides.employee_id` |
| `first_name`, `last_name` | TEXT | Nome como consta na planilha |

### `assignment_history`

| Coluna | Tipo | Descrição |
| --- | --- | --- |
| `id` | INTEGER PK | |
| `employee_id` | TEXT FK | Referência a `employees` |
| `cost_center` | TEXT | Centro de custo |
| `store` | TEXT | Loja ou setor |
| `valid_from` | TEXT | Início da vigência (`YYYY-MM-DD`). `1900-01-01` quando a planilha não informa |
| `valid_to` | TEXT | Fim da vigência, NULL para a lotação atual |

Restrição única em (`employee_id`, `cost_center`, `store`, `valid_from`).

## Por que o identificador da pessoa é o nome

O portal exporta a coluna "ID do funcionário", mas ela chega vazia na maioria das
organizações. A planilha de lotação é mantida por pessoas usando nome e sobrenome. O único
elo confiável entre as duas fontes é o nome, então ele é normalizado (sem acentos, caixa
alta, espaços únicos) e usado como chave. Homônimos são uma limitação conhecida e devem
ser resolvidos na planilha (por exemplo, com o sobrenome completo).

## Join temporal

Para cada corrida, a vigência escolhida é a que satisfaz
`valid_from <= ride_date <= valid_to` (ou `valid_to` nulo). Se mais de uma satisfizer, vence
a de `valid_from` mais recente. O `LIMIT 1` na subconsulta garante que o join nunca
multiplica corridas. Corridas de pessoas sem lotação recebem `Não mapeado`, o que as
mantém visíveis no dashboard como pendência de cadastro.

## Formato dos relatórios do portal

```text
Empresa:;NOME DA EMPRESA
Administrador:;
Data do relatório:;2026-08-03 18:01:06 +0000 UTC

Transações
Nome;Sobrenome;ID do funcionário;Serviço;Cidade;Endereço de partida;Endereço de destino;Data da solicitação (local);Hora da solicitação (local);Várias paradas;Valor total: BRL;Nome do convidado;Sobrenome do convidado
```

O leitor não depende do número de linhas de metadados: ele procura a primeira linha que
contenha "Nome" e "Sobrenome" e usa o separador dessa linha. Aceita `;`, `,` e tabulação,
CSV ou XLSX.
