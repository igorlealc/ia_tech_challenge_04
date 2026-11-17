# Análise e monitor simulado de PAM

Os notebooks `analisar_pressao_invasiva.ipynb` e `analisar_pressao_invasiva_por_intervalo.ipynb` fazem a análise retrospectiva por registro e por médias de intervalos configuráveis.

## Simulador de monitor

`simular_monitor_pam.py` lê um caso de uma pasta Parquet e reproduz a chegada dos dados em um gráfico Matplotlib. Eixo X: tempo relativo da gravação, em segundos. Eixo Y: PAM, em mmHg. A tela mostra leitura atual, situação e total de urgências. A reprodução padrão acrescenta **um registro a cada 1 segundo real** em uma janela nativa do sistema operacional. O eixo X mantém o tempo original (`tempo_s`) do registro: uma lacuna na gravação não causa espera adicional nem descarte de linhas. Por padrão, a reprodução começa no primeiro registro do caso, incluindo ausentes e valores fora da faixa normal. Use `--inicio-segundos` para selecionar um tempo inicial, sem seleção pela pressão. O primeiro registro aparece após o primeiro disparo do temporizador. Ao terminar, a janela permanece aberta no último estado, sem reiniciar o caso. O temporizador da interface não é um relógio de tempo real rígido: se a máquina atrasar, a reprodução desacelera, mas não pula nem agrupa registros.

Execute com Python 3.11 e as dependências de `trabalho4/requirements.txt`. A janela requer ambiente gráfico e backend Matplotlib nativo, como TkAgg ou QtAgg. Caso não haja suporte instalado, execute `python -m pip install PySide6`. O script seleciona uma janela nativa em vez de backends inline/web; em servidor sem display, use o modo sem interface apenas para validação. Exemplo executado a partir da raiz do projeto:

```bash
python trabalho4/deteccao_anomalias/simular_monitor_pam.py \
  --pasta trabalho4/deteccao_anomalias/vitaldb/vitaldb_200/sinais \
  --caso 5116 \
  --urgente-baixa 40 --normal-min 60 --normal-max 100 --urgente-alta 120 \
  --janela 120 --velocidade 1 \
  --saida-eventos /tmp/eventos_pam.json
```

**Os quatro valores desse comando são apenas exemplos para demonstrar as cinco faixas, não recomendações clínicas.** Os limites são obrigatórios e devem ser finitos, estritamente crescentes:

| Situação | Condição | Cor |
| --- | --- | --- |
| Urgente muito baixa | PAM < urgente-baixa | Vermelho |
| Atenção baixa | urgente-baixa ≤ PAM < normal-min | Laranja |
| Normal na faixa configurada | normal-min ≤ PAM ≤ normal-max | Azul |
| Atenção alta | normal-max < PAM ≤ urgente-alta | Laranja |
| Urgente muito alta | PAM > urgente-alta | Vermelho |
| Sem medição válida | Ausente, infinito ou intervalo sem dados | Cinza |

Há quatro limites porque eles delimitam cinco faixas contínuas, sem sobreposição. Não são os limites estatísticos IQR dos notebooks. O simulador não aprende limiares com o futuro do caso.

### Parâmetros opcionais

- `--inicio-segundos 5100`: começa na primeira leitura com `tempo_s >= 5100`, mantendo o eixo X original. Padrão `0`. Não é um atraso antes de abrir a janela. Aceita segundos fracionários; rejeita negativos, infinitos e trechos sem registros. Ausentes não são pulados. Com `--intervalo`, seleciona as médias pelo tempo de fechamento do bloco, mantendo sua composição original, que pode incluir medições anteriores ao início solicitado. Alertas são avaliados somente no trecho reproduzido.

- `--intervalo 5`: opcional, substitui os registros individuais por médias da PAM em blocos de 5 segundos por caso; cada média ocupa um disparo do temporizador da tela. Padrão `0`: cada registro. Cada média fica disponível no fim de seu bloco `[início, fim)`; o último bloco parcial é finalizado ao encerrar a gravação. Os tempos não são contagens de linhas. Ausentes/infinitos não entram na média e blocos vazios permanecem sem dados. A média não é ponderada pelo tempo nem prova pressão sustentada no intervalo.
- `--velocidade 20`: solicita 20 registros por segundo real; o padrão `1` mostra um registro por segundo. Cada disparo consome apenas uma leitura, mesmo quando os tempos originais são irregulares. Essa opção controla a animação, não a agregação.
- `--janela 120`: exibe os últimos 120 segundos.
- `--manter-sinal-original`: desativa o valor absoluto. Por padrão, segue os notebooks e aplica `abs(PAM)`, preservando contagem de negativos convertidos. Isso não valida clinicamente valores negativos; uma conversão pode alterar a faixa do alerta.
- `--saida-eventos caminho.json`: salva os eventos de urgência ao fechar a janela ou concluir a execução sem interface.
- `--saida-figura caminho.png`: salva a tela ao encerrar.
- `--sem-interface --saida-figura /tmp/monitor_pam.png`: processa todo o caso sem espera e sem janela, salvando o estado final do gráfico para validação em servidor.

A pasta deve conter somente uma versão dos sinais, com as colunas `caseid`, `tempo_s` e `pressao_media_invasiva_mmhg`. Pode haver um caso por arquivo ou uma base unificada. O leitor filtra o caso e projeta as três colunas; rejeita tempos duplicados. Não misture dados brutos e agregados na mesma pasta. Ao fornecer dados já agregados, não ative nova agregação sem intenção.

### Urgências e envio de e-mail

O monitor gera um PDF com identificação do caso, motivo, PAM, limites e duração quando a urgência permanece por **mais de 10 segundos do tempo da série (`tempo_s`)**. Exatamente 10 segundos ainda não dispara. Leituras válidas fora da urgência reiniciam a contagem. Ausências preservam a contagem somente se o intervalo entre medições válidas não ultrapassar `--lacuna-alerta` (padrão: 5s); lacunas maiores reiniciam a contagem. O envio ocorre apenas ao receber uma nova medição urgente, nunca durante uma ausência; mudanças entre urgência baixa e alta mantêm a contagem. A duração é inferida das leituras disponíveis, tolerando somente lacunas dentro do limite configurado, inclusive quando não há registros intermediários.

O PDF fica em `deteccao_anomalias/outputs` e é anexado ao e-mail usando `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO` e opcionalmente `SMTP_TIMEOUT` do `trabalho4/.env`. Há **uma única tentativa por execução**, inclusive em modo `--sem-interface`. Novos episódios não reenviam. Em falhas, o monitor continua, preserva o PDF se já gerado e registra `envio: falha`; não tenta novamente para evitar duplicação. O JSON de eventos inclui o caminho do relatório e o status do envio.

O gráfico usa uma linha sem marcadores, contínua entre leituras válidas próximas, inclusive nas mudanças de faixa. A cor de cada segmento segue a situação da leitura de chegada. `--lacuna-max 5` conecta leituras válidas separadas por até 5 segundos, mesmo com linhas vazias intermediárias; lacunas maiores interrompem a linha. Essa conexão é somente visual: não preenche ausentes e não produz medições ou alertas intermediários. A tela continua indicando ausência quando o registro atual não tem PAM. Os alertas são disparados pela faixa de cada entrada, com o filtro de duração descrito acima, sem validação clínica ou comprovação de artefato. Na opção de médias, o alerta usa a média e pode ocultar extremos curtos.

### Verificação

```bash
python -m unittest discover -s trabalho4/deteccao_anomalias/tests -v
```

## Qualidade da PAM nos notebooks

Os dois notebooks usam `qualidade_pam.py`, que deve acompanhá-los. A primeira célula configura os parâmetros; a seção de qualidade documenta fórmulas, janelas, exemplos, limitações e instantes de decisão.

A heurística usa a PAM original com sinal e agrupa extremos por caso, respeitando lacunas. Possível flush exige pico acima de 200, duração observada de até 10s, subida de pelo menos 50 mmHg sobre a mediana anterior e retorno a até 15 mmHg dela. Contextos anterior/posterior de 10s precisam conter pelo menos três observações, extensão de pelo menos 5s e lacunas de no máximo 5s, incluindo distância até a borda. A gravação precisa alcançar o fim da janela posterior para classificar um flush breve.

Para sinal baixo, procura-se uma janela móvel recente de até 10s dentro do episódio, com mediana abaixo de 30, amplitude de até 2 mmHg e queda de pelo menos 40 mmHg em relação ao contexto anterior. Essa suspeita pode ser calculada com o passado, mas **não confirma desconexão** nem elimina o alerta clínico de pressão baixa.

Esses números são parâmetros exploratórios, não critérios clínicos validados. Ausência de contexto produz `inconclusivo`, preservando o registro. Extremos sustentados ou sem evidências da regra permanecem disponíveis. Os dados originais nunca são alterados.

**Não há exclusão automática por padrão.** `EXCLUIR_POSSIVEL_FLUSH = True` permite excluir da PAM analítica apenas os pontos de possíveis flushes, depois de revisão. Sinais baixos e episódios inconclusivos nunca são excluídos automaticamente. As análises estatísticas continuam usando PAM absoluta para comparação com os notebooks anteriores; a anotação de qualidade sempre consulta a original.

`pam_tratada.parquet` preserva todas as linhas e anotações; `episodios_qualidade_pam.csv/.parquet` registra as medidas e decisões; `resumo_qualidade_pam.csv` separa contagens de episódios e registros. `registros_excluidos_artefatos.parquet` é vazio por padrão. Os gráficos `qualidade_exemplo_*.png` ajudam na revisão. Os dicionários continuam descrevendo a fonte, com notas sobre as saídas derivadas.

A anotação por episódio é retrospectiva e não deve ser usada antes de `instante_decisao_qualidade_s`. Flush exige contexto futuro; médias revisadas podem exigir espera adicional. O simulador Python não foi alterado para usar automaticamente estas heurísticas.


### Caso selecionado para demonstrar a subida

O caso **1341** começa com a primeira PAM válida de **80 mmHg em 2s**. Mais adiante, registra **65 mmHg em 516s**, **116 mmHg em 518s** e **142 mmHg em 522s**. Com a faixa demonstrativa normal 60–100 e urgência alta acima de 120, o trecho muda de azul para laranja e vermelho. Isso descreve os valores observados, não confirma a causa clínica da subida. Há linhas ausentes intercaladas, preservadas na reprodução.

A 1 registro por segundo, a subida em 518s aparece após aproximadamente 8 minutos e 39 segundos de reprodução desde a primeira linha (tempo zero). Para inspecionar mais rapidamente, altere `--velocidade`, por exemplo para `10`; o padrão continua 1.


### Caso que começa com PAM válida normal e apresenta elevação sustentada

Use **`--caso 5116`** para reproduzir o caso completo. A primeira PAM válida é **88 mmHg em 4s**, dentro da faixa demonstrativa 60–100. De **5151s a 5229s**, todas as 40 medições válidas ficam acima de 120 mmHg: **122–139 mmHg**, mediana **133 mmHg**, espaçamento de **2s**, extensão observada de **78s**. Isso não significa que todas as leituras anteriores ao episódio sejam normais. As linhas iniciais sem medição e os demais dados são preservados na reprodução. O monitor não recorta o caso nem modifica os valores para obter essa trajetória.

Exemplo: acrescente `--inicio-segundos 5100` ao comando do caso 5116 para começar próximo da subida sustentada de 5151s, sem esperar a reprodução dos dados anteriores.

No caso **1341**, começando em 500s, as medições urgentes de 522s a 534s disparam a tentativa em **534s** (12s de duração), mesmo com NaN intercalados. Com `--velocidade 5`, isso ocorre após aproximadamente 7 segundos reais. Os limites considerados são os do exemplo (urgência alta acima de 120 mmHg).
