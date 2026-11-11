# Áudio para PDF

Script simples, no estilo de `analise_video`, com funções para argumentos, transcrição e PDF. Usa Azure Speech to Text com reconhecimento contínuo para transcrever todas as frases de cada arquivo.

Dentro de `trabalho4`, com o ambiente Python ativado:

```bash
python -m pip install -r requirements.txt
```

Preencha `SPEECH_KEY` e `SPEECH_REGION` em `trabalho4/.env`; o modelo está em
`trabalho4/.env.example`. O script carrega esse arquivo independentemente do diretório
atual. É possível indicar outro arquivo com `--env caminho/.env`. Variáveis já definidas
no ambiente têm precedência sobre o `.env`.

Para o PDF de `transcrever_audio.py`, preencha também `TEXT_ANALYTICS_ENDPOINT` e
`TEXT_ANALYTICS_KEY` com o endpoint HTTPS e a chave do recurso **Azure Language / Text
Analytics**. Essas configurações são separadas das credenciais de Azure Speech.

Arquivo de áudio:

```bash
python analise_audio/transcrever_audio.py \
  --audio consulta.wav --output analise_audio/outputs/consulta.pdf
```

Vários arquivos no mesmo PDF:

```bash
python analise_audio/transcrever_audio.py \
  --audio consulta1.wav consulta2.wav --output analise_audio/outputs/consultas.pdf
```

Microfone do notebook:

```bash
python analise_audio/transcrever_audio.py \
  --microfone --duracao 120 --output analise_audio/outputs/microfone.pdf
```

Execute no próprio notebook, com acesso ao microfone liberado. A captura termina após a duração informada (padrão: 60 segundos), e o PDF é gerado. O idioma padrão é `pt-BR`; use `--idioma en-US` para inglês.

Esta versão recebe arquivos WAV PCM mono de 16 bits, 8 ou 16 kHz, sem conversão automática de MP3 ou outros formatos. A chave e a região são carregadas do `.env`, com precedência das variáveis de ambiente existentes. É necessária conexão com o Azure. O PDF existente no destino é substituído.

## Pasta de vídeos e tradução

Instale FFmpeg e deixe o comando `ffmpeg` disponível no PATH. No macOS: `brew install ffmpeg`. Em Ubuntu/Debian: `sudo apt install ffmpeg`.

Todos os vídeos da pasta, com fala em inglês e PDF em português:

```bash
python analise_audio/transcrever_audio.py \
  --pasta analise_audio/inputs/videos \
  --idioma en-US --traduzir \
  --output analise_audio/outputs
```

Neste modo, `--output` é uma pasta. Será gerado um PDF por vídeo, como `consulta.mp4.pdf`. Os vídeos são processados sequencialmente, em ordem de nome, sem percorrer subpastas. Extensões aceitas: MP4, MOV, MKV, AVI, WEBM, M4V, MPEG, MPG e WMV (sem distinção de maiúsculas). O FFmpeg extrai a primeira faixa de áudio para um WAV temporário e o arquivo temporário é removido ao terminar. Um vídeo sem áudio ou com erro interrompe o comando; PDFs anteriores permanecem salvos.

Informe em `--idioma` o idioma falado nos vídeos. Não há detecção automática de idioma.
Sem `--traduzir`, o PDF contém a transcrição no idioma original. Com `--traduzir`,
`transcrever_audio.py` usa **Azure Speech Translation em tempo real**: o texto original
e a tradução para português são exibidos conforme cada frase é reconhecida, sem
aguardar o fim do áudio para iniciar a tradução. O PDF contém o texto traduzido.
Se o idioma já for português, usa apenas Speech to Text. Isso vale também para
`--audio` e `--microfone`.

Esse fluxo usa `SPEECH_KEY` e `SPEECH_REGION`, sem exigir `TRANSLATOR_KEY`.
A transcrição original é preservada ao lado do PDF, com o sufixo
`.transcricao_original.txt`. Ao término do reconhecimento, a análise de sentimento
usa o texto traduzido em português e aparece em uma nova página após a transcrição.
Sem tradução, a análise usa o texto e o idioma originais.

O `avaliar_audio.py` mantém seu fluxo próprio: transcreve o áudio e depois traduz
com Azure Translator, preservando o original e a tradução no relatório médico.
Para esse script, configure `TRANSLATOR_ENDPOINT`, `TRANSLATOR_KEY` e
`TRANSLATOR_REGION` no `.env`. A região é exigida para recursos regionais ou de
múltiplos serviços. A URL base padrão é `https://api.cognitive.microsofttranslator.com`;
para endpoint personalizado, use a base com o caminho `/translator/text/v3.0`.

Referência: [tradução contínua com Azure Speech](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-translate-speech).

## Atributos acústicos para Parquet

Se aparecer `ImportError: pyarrow requires NumPy 2.0 or newer`, instale uma versão compatível com o NumPy 1.26 no mesmo ambiente do script:

```bash
python -m pip install --upgrade "pyarrow>=14,<26"
```

Reinicie o kernel se estiver usando um notebook. Esse limite também está em `requirements.txt`.

O script `extrair_atributos_audio.py` usa openSMILE com eGeMAPSv02/Functionals para obter 88 atributos por segmento. Instale as dependências com `python -m pip install -r requirements.txt` e execute dentro de `trabalho4`:

```bash
python analise_audio/extrair_atributos_audio.py \
  --pasta analise_audio/inputs/training \
  --duracao 180 \
  --output analise_audio/outputs/atributos.parquet
```

Também aceita `--audio caminho1.wav caminho2.wav` no lugar de `--pasta`. A duração padrão é 180 segundos. Os segmentos são consecutivos, sem sobreposição, e incluem a sobra final: 900 segundos geram 5 segmentos de 180 segundos; para gerar 3, use `--duracao 300`. Um áudio menor que o limite gera uma única linha. A divisão ocorre em memória, sem salvar WAVs intermediários; áudio multicanal é convertido para mono pela média dos canais.

Cada linha contém os atributos, `arquivo`, `parte` (a partir de 1), `inicio_s`, `fim_s` e três colunas inteiras de classificação, herdadas do nome do arquivo:

| Prefixo do arquivo | cansaco | falta_ar | doenca_respiratoria |
| --- | --- | --- | --- |
| `consulta_cansaco_` | 1 | 0 | 0 |
| `consulta_falta_ar_` | 0 | 1 | 0 |
| `consulta_tosse_`, `consulta_respiratorio_` ou `consulta_doenca_respiratoria_` | 0 | 0 | 1 |
| `consulta_sem_relacao_` | 0 | 0 | 0 |

Esses rótulos representam a classificação fornecida, não uma classificação inferida pelo openSMILE. Nomes desconhecidos, arquivos inválidos ou áudios vazios interrompem a execução. O Parquet é escrito após o processamento de todos os arquivos e substitui o destino existente. Os WAVs precisam conter áudio real: ponteiros Git LFS devem ser substituídos pelos arquivos baixados do repositório de origem.

Referência: [uso do openSMILE em Python](https://audeering.github.io/opensmile-python/usage.html).

## Treinamento SVM com análise de correlação

Para executar extração, treinamento e avaliação em sequência, use
`bash parte2.sh --idioma en-US --sem-email` a partir de `trabalho4`.
O fluxo completo está na [parte 2 do README principal](../README.md#parte-2--treinamento-svm-e-avaliação-de-consultas-por-áudio).
Somente `inputs/training` alimenta o treinamento; `inputs/patients` é usado após a
exportação dos modelos, para gerar as avaliações.

O executor `treinar_svm_audio.py` reutiliza o notebook abaixo, sem duplicar seu
algoritmo. Recebe `--parquet`, `--output` e `--duracao`, salva a cópia executada e
valida os modelos exportados antes de liberar a etapa de avaliação.

Os textos e as tabelas das células são exibidos no terminal ao final de cada célula.
Para visualizar as tabelas formatadas e os gráficos, abra
[`outputs/svm/treinamento_executado.ipynb`](outputs/svm/treinamento_executado.ipynb).
O notebook original é o modelo de execução e não recebe essas saídas.
Se definir `PARTE2_OUTPUT`, a cópia executada estará em `svm/` dentro dessa pasta.

O notebook [`treinar_svm_audio.ipynb`](treinar_svm_audio.ipynb) usa
`trabalho/trabalho_parte_3.ipynb` como referência e treina três `LinearSVC` independentes,
na ordem `cansaco`, `falta_ar` e `doenca_respiratoria`, a partir de
`outputs/atributos.parquet`. Ele contém análise de correlação de Pearson, heatmaps,
remoção de atributos redundantes, SVM base, tuning por recall e avaliação por segmento
e por consulta. `svm_audio.py` implementa o transformador persistido com os modelos.

Dentro de `trabalho4`, com Python 3.11:

```bash
python -m pip install -r requirements.txt
python -m jupyterlab analise_audio/treinar_svm_audio.ipynb
```

Selecione o kernel do ambiente em que instalou as dependências e execute todas as
células em ordem. `RAIZ_AUDIO`, `PARQUET` e `SAIDA` podem ser ajustados na primeira célula.
A execução substitui os artefatos anteriores em `outputs/svm/`.

Os segmentos de uma consulta ficam sempre juntos: 16 consultas no treino e 4 no teste
na base atual. Os quatro folds internos também separam consultas. Imputação, correlação
e escala são ajustadas dentro de cada fold. Os nomes dos arquivos, tempos, números dos
segmentos e todos os targets são excluídos das entradas. A escolha dos hiperparâmetros
usa somente validação; os modelos exportados permanecem ajustados apenas no treino.

Saídas em `outputs/svm/`:

- `modelos/svm_cansaco.joblib`, `svm_falta_ar.joblib` e `svm_doenca_respiratoria.joblib`:
  pipelines completos com tratamento de ausentes, seleção, escala e SVM.
- `modelos/svm_audio.py`, `manifesto.json` e `requirements_inferencia.txt`: módulo
  necessário à recarga, esquema de entrada, parâmetros, versões, métricas e hashes.
- CSVs com correlações, divisão de consultas, resultados de validação cruzada,
  atributos selecionados, métricas e previsões do teste; gráficos na pasta `figuras/`.

Para reutilizar, copie a pasta `modelos` inteira, instale o seu
`requirements_inferencia.txt` e disponibilize o módulo `svm_audio.py` no caminho de importação:

```python
from pathlib import Path
import sys
import joblib
import pandas as pd

pasta = Path('analise_audio/outputs/svm/modelos').resolve()
sys.path.insert(0, str(pasta))
novos = pd.read_parquet('novos_atributos.parquet')
for target in ['cansaco', 'falta_ar', 'doenca_respiratoria']:
    modelo = joblib.load(pasta / f'svm_{target}.joblib')
    print(target, modelo.predict(novos))
```

Use os mesmos 88 atributos eGeMAPSv02/Functionals e a mesma segmentação do treinamento.
Não são necessários rótulos para inferência. `decision_function` fornece margens, não
probabilidades; a agregação por consulta usa a média das margens dos segmentos.

São apenas 20 consultas, com uma consulta positiva por target no teste. Os resultados
são exploratórios; `doenca_respiratoria` corresponde ao grupo de tosse informado e não
confirma diagnóstico. Como não há identificador de pessoa, o split garante separação
por consulta, mas não necessariamente por participante. As saídas em `outputs/` são
ignoradas pelo Git: copie os artefatos para reutilizá-los fora deste checkout.

## Avaliação completa: áudio/microfone, transcrição, SVM, PDF e e-mail

O script `avaliar_audio.py` reutiliza `transcrever_audio.py` para transcrição e
`extrair_atributos_audio.py` para os atributos. Carrega os três modelos exportados,
produz um relatório PDF e envia o PDF por SMTP se qualquer um dos três modelos
(`cansaco`, `falta_ar` ou `doenca_respiratoria`) sinalizar positivo.
Quando há cansaço, o PDF e o e-mail incluem a possibilidade de atenção psicológica
e avaliação da necessidade de terapia para investigar possível desmotivação,
sem inferir desmotivação apenas pela sinalização do modelo.
A transcrição não é uma entrada dos modelos acústicos.

Instalação das dependências unificadas, dentro de `trabalho4` (Python 3.11):

```bash
python -m pip install -r requirements.txt
```

Preencha o arquivo `.env` na raiz de `trabalho4`, usando `.env.example` como modelo:

| Variável | Conteúdo |
| --- | --- |
| `SPEECH_KEY` | Chave do recurso Azure Speech |
| `SPEECH_REGION` | Região do mesmo recurso Azure Speech |
| `SMTP_HOST` | Servidor SMTP do provedor |
| `SMTP_PORT` | Porta SMTP, normalmente 587 ou 465 |
| `SMTP_SECURITY` | `starttls` para 587 ou `ssl` para 465, conforme o provedor |
| `SMTP_USERNAME` | Usuário para autenticação SMTP |
| `SMTP_PASSWORD` | Senha SMTP ou senha de aplicativo do provedor |
| `EMAIL_FROM` | Endereço de remetente autorizado pelo provedor |
| `EMAIL_TO` | Um endereço de destinatário do alerta |
| `SMTP_TIMEOUT` | Timeout da conexão SMTP em segundos, padrão 30 |

O `.env` é ignorado pelo Git; não coloque credenciais em `.env.example`.
Preencha senhas que contenham espaços ou `#` entre aspas. Variáveis do processo
têm precedência. Ambos os scripts que acessam o Azure aceitam `--env`.

Arquivo de áudio:

```bash
python analise_audio/avaliar_audio.py \
  --audio analise_audio/inputs/patients/consulta_doenca_respiratoria_dia3_04.wav \
  --paciente "Paciente 001" \
  --idioma en-US \
  --output analise_audio/outputs/avaliacao.pdf
```

Microfone, em português:

```bash
python analise_audio/avaliar_audio.py \
  --microfone --duracao 120 --idioma pt-BR \
  --paciente "Paciente 001" \
  --output analise_audio/outputs/avaliacao_microfone.pdf
```

No modo microfone, a gravação é feita uma única vez e salva como
`avaliacao_microfone.audio.wav`; esse mesmo áudio é transcrito e classificado.
`--duracao` controla somente o tempo de captura. `--dispositivo "nome"` permite
selecionar o microfone; `python -m sounddevice` lista os dispositivos disponíveis.
É necessário acesso ao microfone no computador local. Se PortAudio estiver ausente,
instale-o pelo gerenciador do sistema (`brew install portaudio` no macOS ou
`sudo apt install libportaudio2` no Linux).

Os atributos usam o áudio original, convertido para mono pela média dos canais como
no treinamento. Somente a cópia enviada ao Azure é convertida para WAV PCM mono de
16 bits e 16 kHz. WAV, FLAC e outros formatos suportados pelo SoundFile são lidos
diretamente; formatos adicionais precisam de FFmpeg instalado. Áudio vazio, silêncio
digital e ponteiros Git LFS interrompem o processamento.

Na avaliação, o openSMILE extrai os atributos do áudio inteiro em uma única chamada,
gerando uma linha enviada a cada SVM, sem divisão por duração. `--duracao` controla
apenas a gravação pelo microfone. A decisão usa a margem do áudio completo:
**margem maior que zero** sinaliza positivo. A margem não é uma probabilidade de doença.
O JSON identifica esse processamento como `modo_analise: "audio_inteiro"`.
Os modelos existentes continuam sendo os treinados com segmentos; esta alteração
não realiza um novo treinamento.
Os três modelos são independentes e podem sinalizar mais de um grupo.

São gerados, com o mesmo prefixo do PDF:

- `.pdf`: identificação do paciente, data e sinais indicados para avaliação médica,
  transcrição original completa, tradução automática para português quando o idioma
  informado for diferente de português e,
  em uma nova página após os textos, análise de sentimento em linguagem não técnica;
- `.atributos.parquet`: atributos sem targets ou rótulos inferidos do nome do arquivo;
- `.transcricao.txt`: texto reconhecido pelo Azure;
- `.json`: resultados, margens, hash do modelo respiratório e estado do envio;
- `.audio.wav`: gravação original, apenas no modo microfone.

Use `--sem-email` para executar sem envio, inclusive quando houver sinalização positiva.
Use `--modelos caminho/da/pasta` para outra exportação completa dos três modelos.
Arquivos de saída com o mesmo nome são substituídos. Uma nova execução positiva pode
enviar outro e-mail; não há reenvio automático dentro da execução.

O PDF e o e-mail usam linguagem voltada ao médico: os modelos preditivos indicam
possível risco associado ao paciente e solicitam avaliação clínica. Não exibem
margens, contagens de segmentos, parâmetros, hashes ou estatísticas do treinamento.
Os dados técnicos permanecem no JSON. A transcrição original aparece tanto no PDF
quanto no arquivo de texto.
Use `--paciente` para informar o nome ou identificador; se omitido, o documento
mostra "Paciente: Não informado", sem deduzir a identidade pelo nome do áudio.
A sinalização não confirma diagnóstico e sua ausência não exclui sintomas ou doença.

O `avaliar_audio.py` também chama Azure Text Analytics após a transcrição, usando
`TEXT_ANALYTICS_ENDPOINT` e `TEXT_ANALYTICS_KEY` do `.env`. O PDF e o e-mail incluem
um resumo do sentimento do relato, sem percentuais de confiança ou detalhes técnicos.
Quando há diferentes sentimentos ao longo de um texto extenso, o resumo informa
essa variedade, sem calcular uma classificação global por média. As respostas
detalhadas ficam em `analise_sentimento` no JSON.

O sentimento não altera a classificação respiratória nem a regra de envio de e-mail.
Se essa análise falhar, o PDF informa que ela está indisponível e a avaliação
respiratória e seu alerta são preservados; o processo retorna código 2.
Sem fala reconhecida, o relatório informa que não houve relato para análise.

Dentro de `trabalho4`, para gerar o relatório com resumo médico, transcrição original,
tradução automática para português e análise de sentimento, sem enviar e-mail:

```bash
python analise_audio/avaliar_audio.py \
  --audio consulta.wav \
  --idioma en-US \
  --paciente "Paciente 001" \
  --output relatorio.pdf \
  --sem-email
```

Preencha `TRANSLATOR_ENDPOINT`, `TRANSLATOR_KEY` e, quando exigida pelo recurso,
`TRANSLATOR_REGION` no `.env`. O fluxo transcreve primeiro, preserva o original e
depois traduz. O PDF apresenta o resumo médico, a transcrição original, a tradução
e a análise de sentimento, nessa ordem. Cada seção pode ocupar mais de uma página.
O sentimento usa o texto traduzido quando disponível. Sem tradução, usa o original.
No `avaliar_audio.py`, a tradução é automática para idiomas diferentes de português,
sem necessidade de `--traduzir`. A opção continua aceita para compatibilidade com
comandos anteriores. Informe em `--idioma` a língua realmente falada na consulta;
não há detecção automática do idioma. O `transcrever_audio.py` mantém sua opção
explícita `--traduzir`.
Se o idioma já for português, o PDF informa que não foi necessária tradução.
Se a tradução falhar, o PDF mantém a transcrição original e indica que a tradução
está indisponível; a avaliação respiratória e o alerta continuam, com código de saída 2.
No JSON, `transcricao` preserva o original e `traducao` contém o texto traduzido e seu estado.

O envio utiliza TLS e autenticação e anexa o relatório destinado ao médico. O JSON
registra `aceito_pelo_servidor_smtp` quando o servidor aceita a mensagem, o que não
confirma entrega na caixa de entrada. Em caso de falha SMTP, o PDF e os demais resultados
permanecem salvos, o JSON registra `falha` e o processo termina com código 2.
Falhas de transcrição/extração interrompem a análise e não enviam alerta. Não ocorre
envio quando os três modelos têm classificação negativa.

O resultado é experimental: `doenca_respiratoria` representa o grupo rotulado como
tosse, não diagnóstico confirmado. Ausência de sinalização não exclui doença.

Referências: [entrada de áudio no Azure Speech](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-use-audio-input-streams),
[configuração com python-dotenv](https://bbc2.github.io/python-dotenv/reference/).

## Envio de e-mail de teste

Para enviar somente uma mensagem de teste para `EMAIL_TO`, usando as configurações
SMTP do `.env`, execute dentro de `trabalho4`:

```bash
python analise_audio/enviar_email_teste.py
```

Também aceita `--env caminho/.env`. Não acessa Azure, microfone ou modelos e não envia
anexos. Requer `python-dotenv` e `certifi` além da biblioteca padrão, já incluídos no
`requirements.txt`. Cada execução envia uma mensagem. O sucesso indica aceitação
pelo servidor SMTP; confira a caixa de entrada ou spam para confirmar o recebimento.

Para Gmail, configure `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587` e
`SMTP_SECURITY=starttls`. Use o endereço Gmail completo em `SMTP_USERNAME` e
`EMAIL_FROM`, e uma senha de aplicativo em `SMTP_PASSWORD`, quando disponível para
a conta. A alternativa é porta 465 com `SMTP_SECURITY=ssl`.

Os dois scripts de envio complementam os certificados do sistema com `certifi`,
mantendo a validação do certificado e do nome do servidor. Em caso de
`CERTIFICATE_VERIFY_FAILED`, atualize no mesmo ambiente que executa o script:

```bash
python -m pip install --upgrade certifi
```

Se o erro persistir, a cadeia apresentada pela conexão precisa ser investigada,
inclusive eventual inspeção TLS da rede. Não desative a verificação de certificados.

Referências: [SMTP do Gmail](https://developers.google.com/workspace/gmail/imap/imap-smtp),
[senhas de aplicativo Google](https://support.google.com/accounts/answer/185833).

## Sentimento no PDF de transcrição

O `transcrever_audio.py` agora gera a transcrição completa e, **na página seguinte ao
fim da transcrição**, inicia a seção de análise de sentimento com Azure Text Analytics.
Uma transcrição com três páginas terá a análise começando na quarta. O comportamento
vale para arquivo, vários arquivos, microfone e cada vídeo processado com `--pasta`.

Além de `SPEECH_KEY` e `SPEECH_REGION`, configure no `.env`:

```dotenv
TEXT_ANALYTICS_ENDPOINT=https://seu-recurso.cognitiveservices.azure.com/
TEXT_ANALYTICS_KEY=sua_chave_do_recurso_language
```

Instale as dependências atualizadas com `python -m pip install -r requirements.txt`.
Os comandos de transcrição permanecem os mesmos. O PDF mostra o sentimento retornado
pelo Azure (positivo, neutro, negativo ou misto) e a confiança nas classes positiva,
neutra e negativa. O idioma é derivado de `--idioma`; com `--traduzir`, a análise usa o
texto traduzido em português.

Transcrições longas são divididas em trechos de até 4.000 caracteres, enviados em lotes
de no máximo 10. Os resultados são apresentados por trecho, sem inventar um sentimento
global pela média dos índices. O texto inteiro é analisado, e a transcrição inteira é
preservada no PDF. Sem fala reconhecida, o serviço de sentimento não é chamado e o PDF
informa que a análise não foi realizada.

Falhas do serviço aparecem na seção de sentimento e fazem o processo retornar código 2,
mantendo a transcrição no PDF. Configuração local ausente ou inválida interrompe o fluxo
antes da transcrição. A análise de sentimento utiliza somente o texto: não mede entonação,
risco respiratório ou diagnóstico psicológico. O relatório SVM de `avaliar_audio.py`
apresenta a análise em uma página após a transcrição e eventual tradução, com linguagem voltada
ao médico, sem os índices de confiança exibidos por `transcrever_audio.py`.

Referências: [SDK Azure Text Analytics](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-textanalytics-readme),
[limites de documentos e lotes](https://learn.microsoft.com/en-us/azure/ai-services/language-service/concepts/data-limits).

