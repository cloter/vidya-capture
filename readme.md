# **Manual de Operação: Vidya Capture**

**Sistema Avançado de Digitalização e Preservação de Acervos Documentais**

## 

## **1\. Introdução**

O **Vidya Capture** é um software de código aberto desenvolvido especificamente para atender às demandas rigorosas de digitalização de patrimônio histórico, museológico e arquivístico. Em sua essência, o Vidya Capture atua como o "cérebro" de uma estação de digitalização (como scanners planetários em formato "V"), orquestrando múltiplas câmeras ou scanners simultaneamente.

Diferente de aplicativos genéricos de fotografia, o Vidya Capture foi desenhado para entender a anatomia de um livro ou processo documental: ele captura páginas duplas, processa a geometria do papel e preserva o contexto arquivístico, convertendo o objeto físico em um pacote digital pesquisável, imutável e padronizado para as futuras gerações.

### **1.1 Agradecimentos**

O autor deste software agradece a participação de todos que contribuíram com críticas construtivas e solicitações de melhorias. A equipe do LAMUHDI da Universidade Estadual de Ponta Grossa \- UEPG, foi, e continua sendo, fundamental para que este software tenha se tornado maduro o suficiente para ter uso diário na captura e tratamento de imagens assim como na produção dos documentos finais do nosso acervo que posteriormente são descritos por IA e enviados para nossos repositórios digitais.

## **2\. O Diferencial do Vidya Capture**

O que torna o Vidya Capture uma ferramenta de classe laboratorial?

1. **Edição Não-Destrutiva e Salvamento Implícito:** O Vidya Capture nunca destrói a captura original da sua câmera. Todas as ações de recorte (*crop*), alinhamento (*deskew*) ou planificação (*dewarp*) são registradas como instruções matemáticas em arquivos. Você pode alterar o recorte de uma página dias depois da captura, sem precisar manusear o documento físico novamente.  
2. **Geometria Computacional Avançada:** O sistema possui motores matemáticos proprietários para correção de anomalias físicas:  
   * **Deskew Adaptativo:** Utiliza análise estatística de regressão linear (*fitLine* e filtro MAD) para encontrar o horizonte exato das linhas de texto, corrigindo páginas sem causar cisalhamento.  
   * **Dewarp Inteligente:** Isola a deflexão (a "barriga" formada pela lombada do livro) linha por linha, achatando a página em um plano 2D perfeito, protegido por uma "Trava de Planicidade" que impede distorções em páginas já retas.  
3. **Preservação Arquivística (Proveniência):** Qualquer alteração feita na imagem (como a agressividade do Dewarp) é registrada permanentemente nos metadados do projeto e embutida no PDF final (Padrão ISO 19005 \- PDF/A), garantindo a rastreabilidade da intervenção.  
4. **Operação *Hands-Free* (Ergonomia):** A interface foi projetada para ser controlada integralmente pelo teclado ou pedais USB, permitindo que as mãos do operador nunca saiam do livro durante o fluxo de captura.

## **3\. Configuração Inicial (Preferências)**

Antes de iniciar um lote, pressione **F2** ou clique em **Preferências** para configurar o comportamento do laboratório.

###       

### **3.1. Aba Projeto**

* **Pasta de Trabalho Ativa:** Onde os arquivos brutos e JSONs serão salvos.  
* **Metadados Descritivos:** Preencha Título, Descrição, Editor e Coleção. Estes dados utilizam os padrões *Dublin Core* e *Schema.org* e viajarão de forma inseparável com as imagens e o PDF final.

###       

### **3.2. Aba Dispositivos**

* **Origem:** Escolha entre Câmeras (DSLR/PTP), V4L (Webcams/Câmeras Industriais USB) ou Scanners (SANE).  
* **Detecção Avançada V4L2:** Permite "forçar" o codec (ex: MJPEG) e a resolução direto no hardware, evitando engarrafamentos no barramento USB do computador.  
* Pode-se renomear os dispositivos (clique direito) e reordená-los arrastando.

###        

### **3.3. Aba Marcadores**

Controla as sobreposições vetoriais que indicam a área de corte da página.

* Permite mudar cores (ex: Vermelho para Esquerda, Verde para Direita).  
* **Opacidade e Espessura Dinâmica:** O sistema ajusta a grossura da linha pontilhada com base na resolução de entrada para que ela fique sempre visível, sem ocultar detalhes críticos do documento.

###        

### **3.4. Abas Processar e OCR**

Configura o pipeline automático que rodará ao final da captura:

* **Agressividade Geométrica:** Deslizadores (*sliders*) que vão de 50% a 150% controlam a força dos algoritmos de *Deskew* e *Dewarp*.  
* **Fonte do PDF:** Escolha se o PDF será montado com as imagens em bruto, as corrigidas geometricamente (originais), ou as tratadas (binarizadas).  
* **OCR Heurístico:** Filtros pré-OCR ajustáveis (Cor do Papel, Intensidade de Impressão, Tamanho/Profundidade de Manchas). O Vidya Capture usa o motor *Tesseract 5* com controle estrito de *threads* para evitar travamentos de CPU, gerando um PDF/A-2b pesquisável.

## 

## **4\. O Fluxo de Captura**

Na janela principal, você verá a **Visualização ao Vivo (Live View)** das duas câmeras e a barra de **Miniaturas (Thumbnails)** das capturas já realizadas.

### 

### **4.1. Os Marcadores de Recorte (Crop)**

Os retângulos tracejados determinam o que será salvo no final.

* **Menu de Contexto (Clique Direito):**  
  * Expandir o recorte para o tamanho total da imagem (individual ou ambos).  
  * Copiar o formato do marcador do lado oposto (normal ou espelhado).  
  * **Habilitar Proporção (C):** Trava a proporção altura/largura ao arrastar as bordas.  
  * **Habilitar Replicação (R):** Tudo que você ajustar no marcador esquerdo será espelhado matematicamente em tempo real para o marcador direito.

### 

### **4.2. Modos Básicos de Captura**

Aperte **Tab** para alternar a ação do botão principal (ou pressione **Espaço** para disparar).

1. **Nova Captura:** Tira foto de ambas as páginas e adiciona o par ao final do lote.  
2. **Substituir:** Apaga os dois últimos arquivos capturados e sobrepõe com uma nova foto (ideal para quando acabou de errar a última virada de página).  
3. **Teste:** Não salva nada no disco, apenas atualiza o visor para checar o foco ou iluminação.

## 

## **5\. Edição, Inserção e "Máquina do Tempo"**

Se você perceber que um erro ocorreu 30 páginas atrás, clique na miniatura com defeito. O Vidya Capture entrará em **MODO DE EDIÇÃO** (textos em vermelho).

A partir daqui, alterne a ação com **Tab** para uma das seguintes funções:

* **Alterar Recorte:** Apenas reajuste as bordas pontilhadas. O sistema salva as coordenadas silenciosamente. Clique em "Parar Edição" (Esc) quando terminar.  
* **Substituir Par:** Abre o visor ao vivo. A nova captura substituirá fisicamente os dois arquivos antigos, mantendo a ordem do lote intacta.  
* **Substituir Esquerda / Direita:** Salva apenas a página danificada. O Vidya Capture instrui o hardware a fotografar, mas descarta a imagem do lado oposto, preservando a foto original intacta.  
* **Inserir Antes / Depois:** Se duas páginas ficaram coladas durante a digitalização, use esta função. O Vidya Capture executará um *Deslocamento em Cascata*, renomeando cronologicamente centenas de arquivos sucessores para abrir um "espaço" no banco de dados e inserir a página esquecida exatamente no lugar certo.

## 

## 

## **6\. Operação Profissional (Atalhos de Teclado)**

O Vidya Capture é otimizado para que **as mãos nunca precisem sair do documento ou do teclado**.

### 

### **Zona de Captura (Essencial)**

* **Espaço ou Enter:** Capturar / Confirmar Ação.  
* **Tab:** Alternar Modos (Nova Captura, Substituir, Inserir, etc).  
* **Delete ou Backspace:** Remover o último par (ou o par selecionado na revisão).  
* **F5 ou Esc:** Reiniciar vista / Parar Edição / Abortar ação.

### 

### **Visualização e Geometria**

* **F8** ou **\+:** Mais Zoom.  
* **F7** ou **\-:** Menos Zoom.  
* **F6** ou **0:** Ajustar imagens ao tamanho da tela (*Fit to Screen*).  
* **P:** Ligar/Desligar Trava de Proporção do Crop.  
* **R:** Ligar/Desligar Replicação bilateral do Crop.  
* **F3** ou **I:** Inverter o painel esquerdo com o direito (Útil se as portas USB mudarem no boot).

### 

### **Macros de Alta Velocidade (Com um thumbnail selecionado)**

Atalhos que selecionam a ação e engatilham a câmera em milissegundos:

* **Ctrl \+ Insert:** Macro \-\> Substituir Par.  
* **Ctrl \+ Seta Esquerda:** Macro \-\> Substituir Apenas a Esquerda.  
* **Ctrl \+ Seta Direita:** Macro \-\> Substituir Apenas a Direita.  
* **Ctrl \+ PageUp:** Macro \-\> Inserir Depois deste par.  
* **Ctrl \+ PageDown:** Macro \-\> Inserir Antes deste par.

### 

### **Exportação e Sistema**

* **F12:** Iniciar processamento e Exportação em Lote (Geração do PDF/A).  
* **F2:** Abrir Preferências.  
* **F10:** Alternar janela normal ou maximizada  
* **F11:** Alternar Modo Tela Cheia.  
* **F1:** Abrir este Manual em PDF.

## 

## 

## **7\. Processamento e Exportação**

Após digitalizar todo o acervo, pressione **F12 (Exportar)**. O *Worker* Assíncrono do Vidya Capture assumirá o controle:

1. Ele lerá todos os recortes de todas as páginas e isolará a área útil.  
2. Executará a extração de imagens retificadas  
3. Executará o *Deskew* e o *Dewarp* com a agressividade calibrada pelo operador.  
4. Aplicará os algoritmos OpenCV para limpeza de fundo (Clareamento) e realce de texto.  
5. Montará uma matriz bruta de imagens e passará para o motor *OCRmyPDF* ou *Ghostscript*.  
6. Embutirá os metadados bibliográficos e as ações de proveniência destrutivas diretamente nas propriedades do arquivo.

O resultado final repousará na pasta out do seu projeto: um PDF/A blindado, padronizado e pronto para ser ingerido por plataformas como o *Omeka S* ou repositórios digitais institucionais.

# **Adendo 1 \- Preferências \- Vidya Capture**

O módulo de Preferências do Vidya Capture é o centro de controle do projeto de digitalização. Aqui são definidos desde os metadados e dispositivos até o processamento final e as garantias de preservação digital. As configurações são organizadas em oito abas.

**Importante:** Após ajustar todas as preferências, clique no botão “**Aplicar**” no canto inferior direito para salvar as alterações, ou “**Cancelar**” para descartá-las.

## **1\. Aba Projeto (Configurações Gerais e Metadados)**

Esta aba define a estrutura e a identidade do lote de digitalização. \* **Pasta de Trabalho Ativa:** Define o diretório raiz onde todas as capturas, metadados e arquivos JSON do projeto serão centralizados. (*Atenção: certifique-se de ter espaço em disco suficiente no caminho escolhido*). \* **Modo de Operação do Projeto:** Define a topologia de captura (ex.: *Berço em V (Página Dupla)*). \* ⚠️ **Aviso Crucial:** Esta opção **não pode ser alterada** após a criação do lote. Escolha corretamente antes de iniciar. \* **Verificação de Integridade dos Arquivos:** Permite ativar ou desativar a checagem de integridade (opção apresentada como “*Sem verificação*”). O sistema avisa que desativar acelera o processo, mas ignora alertas de adulteração física. \* **Metadados Descritivos:** Informações que serão gravadas no arquivo PDF/A final. \* *Nome do Projeto*, *Descrição* (campos de texto livre). \* *Data de Criação* (campo automático e não editável, preenchido com o timestamp ISO). \* *Editor/Instituição*, *Fundo/Coleção*, *Operador/Criador* (campos cruciais para a rastreabilidade documental em arquivos).

## **2\. Aba Dispositivos (Controle de Hardware)**

Gerencia quais equipamentos de captura o Vidya Capture irá utilizar. \* **Dispositivo de Origem:** Selecione o tipo de dispositivo no menu suspenso (Câmeras DSLR, Video For Linux 2 \- V4L, ou Scanners SANE). \* **Modo V4L (Câmeras):** Apresenta uma lista dos dispositivos V4L detectados no sistema (ex.: Webcam, USB Camera). Instruções do sistema: Arraste os itens para reordenar a lista ou clique com o botão direito para **Renomear**. Use os botões “*Varredura Rápida*” ou “*Detecção Avançada*” para listar os hardwares conectados. \* **Modo Scanners (SANE):** Lista os scanners de mesa/rede encontrados (ex.: HP Deskjet 2050). Após selecionar, configure os parâmetros de digitalização: \* *Resolução (DPI):* Defina a qualidade óptica (300 DPI no exemplo). \* *Modo de Cor:* Color, Gray, ou Black & White. \* *Alimentação e Formato da Página:* Ajuste para o tipo de alimentador (Flatbed/ADF) e o tamanho do papel (ex.: A4). \* *Brilho e Contraste (Hardware):* Ajuste numérico via sliders. \* ⚠️ **Aviso Importante:** O suporte avançado do SANE exige que o projeto esteja configurado no modo “**Mesa Plana (Câmera Única)**”.

## **3\. Aba Orientação (Rotação dos Sensores)**

Configura a orientação espacial da captura para scanners em formato de berço (V-cradle). \* Para garantir que as imagens fiquem na orientação correta sem precisar girar cada foto manualmente, o software permite definir a rotação de cada sensor. \* *Rotação do Sensor Esquerdo:* Ajustável (ex.: 270°). \* *Rotação do Sensor Direito:* Ajustável (ex.: 90°).

## **4\. Aba Marcadores (Auxílios Visuais de Recorte)**

Controla a aparência da interface de recorte manual. Ajustar essas cores ajuda o operador a visualizar melhor as bordas durante a captura. \* *Cor do Marcador Esquerdo / Direito:* Selecione as cores que definem as guias de corte (Verde e Ciano no exemplo). \* *Cor de Preenchimento de Recorte:* Transparência ou cor sólida da área a ser cortada. \* *Opacidade do Fundo:* Define a transparência do fundo atrás dos marcadores (1% no exemplo). \* *Intensidade da Borda Dinâmica:* Ajusta o contraste da borda que o software detecta automaticamente (100% no exemplo).

## **5\. Aba Imagens (Qualidade e Recorte Automático)**

Centraliza os ajustes pós-captura e os algoritmos de inteligência de corte. \* **Formato e Qualidade das Imagens de Saída:** Define o formato do arquivo (ex.: JPG) e a taxa de compressão (ex.: Qualidade 85%). Ajuste para um bom equilíbrio entre tamanho de arquivo e qualidade do PDF final. \* **Controle da Imagem Capturada:** Ajustes numéricos aplicados via software (brilho e contraste, ambos em 0%). Há um botão “*Restaurar padrões de fábrica*” para estes controles. \* **Inteligência de Recorte Automático (Auto Crop):** Algoritmo avançado que identifica as bordas da página. \* *Perfil de Detecção:* (ex.: Fundo Muito Escuro). \* *Desfoque de Fusão, Dilatação de Fissuras, Margem de Segurança e Área Mínima:* Sliders que refinam a sensibilidade do algoritmo para não cortar acidentalmente o conteúdo da página. \* *Cálculo de Contraste:* Define como o software mede as bordas (ex.: *Forçar Fundo Preto*). \* *Número Máximo de Quadros:* Limite de processamento (ex.: Ilimitado).

## **6\. Aba Processar (Ações de Lote e Geração de PDF)**

Define as operações que serão executadas automaticamente ao finalizar a captura e gerar o lote. \* **Ações para Executar em Lote:** Marque os algoritmos desejados: \* *Cortar (Crop).* \* *Alinhamento (Deskew OpenCV) e Planificação Geométrica (Dewarp):* Ajusta a inclinação e a curvatura natural da página (100% de intensidade). \* *Produzir PDF Unificado:* Cria o arquivo final. \* *Ignorar primeira e última imagens:* Útil em berço em V para remover capas vazias digitalizadas de forma automática. \* **Fonte de Imagens para o PDF Final:** Permite escolher entre “Imagens de Entrada” (brutas), “Imagens Originais” ou “Imagens Tratadas” (pós-processadas). \* **Destino Final do PDF e Limpeza:** Define a pasta para onde o PDF é movido automaticamente após a geração. \* ⚠️ **Aviso:** Existe uma opção para “*Depois de copiar o PDF com sucesso, remover todos os arquivos temporários*”. Habilite com cuidado, pois isso apagará todo o conteúdo da pasta ‘out’ caso o PDF seja gerado.

## **7\. Aba OCR (Reconhecimento Óptico de Caracteres)**

Responsável por extrair o texto das imagens para tornar os PDFs pesquisáveis. \* **Ativação:** Marque a caixa “*Habilitar Extração de Texto (Tesseract 5 \+ PDF/A)*”. \* **Pré-processamento (Binarização OpenCV):** Melhora o contraste entre texto e fundo para aumentar a precisão do OCR. Ative os filtros de realce e ajuste os sliders de *Cor do Papel*, *Intensidade da Impressão*, *Tamanho* e *Profundidade das Manchas*. \* **Motor OCRmyPDF (Tesseract):** \* *Idiomas Base:* Selecione os idiomas do documento (ex.: por+eng para português e inglês). \* *Núcleos CPU (Jobs):* Defina quantos núcleos do processador o software pode usar para acelerar o OCR (ex.: 2 núcleos). \* *Arquivamento Extra:* Opção para “Gerar TXT Separado (.txt)” contendo todo o texto extraído para uso em indexação.

## **8\. Aba Custódia (Preservação e Padrões Arquivos)**

Configura os padrões internacionais de preservação digital, essenciais para bibliotecas e arquivos. \* **Garantia de Fixidez e Origem:** “*Calcular e selar Hash SHA-256*”. Esta opção cria uma prova criptográfica em tempo real. Embora possa atrasar levemente a captura em discos lentos, é vital para comprovar a integridade dos arquivos. \* **Rastreabilidade de Transformações (Padrão PREMIS):** “*Registrar eventos de processamento no manifesto do projeto*”. Anexa ao arquivo project.json todo o histórico de alterações (Deskew, Dewarp, OCR), seguindo o padrão arquivístico PREMIS. \* **Estruturas de Distribuição e Repositório:** \* *Empacotar em padrão internacional BagIt:* Gera manifestos de integridade exigidos por repositórios como AtoM, Archivematica e DSpace. \* *Exportar metadados tabulares (.TSV):* Gera um arquivo TSV para importação em planilhas (Excel), Tainacan, Omeka S etc. Inclui a opção de adicionar a coluna de integridade SHA-256 e a coluna com o texto integral do OCR. \* *Granularidade:* Permite escolher se o registro é feito ao nível do livro ou da página (ex.: “*1\. Registro Global (Ao nível do Livro)*”).

### **Dica Final**

Utilize sempre o botão “**Restaurar padrões de fábrica**” presente nas abas *Imagens, Processar, OCR e Custódia* se você realizar muitas alterações e desejar voltar à configuração original recomendada pelo software.

# **Adendo 2 \- Recortes \- Vidya Capture**

No universo da preservação digital, a captura da imagem é apenas o primeiro passo de um fluxo de trabalho rigoroso. O verdadeiro desafio operacional começa quando nos deparamos com a diversidade física dos acervos: jornais históricos de grandes dimensões com colunas desalinhadas, documentos encadernados capturados em berços bi-câmara, páginas fotografadas com distorções de perspetiva ou a necessidade de processar múltiplos itens dispostos numa única mesa de captura.

O objetivo desta sessão é capacitá-los no domínio absoluto das ferramentas geométricas do Vidya. Vamos explorar de que forma a interface gráfica traduz interações simples do utilizador — como o arrastar de um nó ou o clique em um menu de contexto — em transformações matriciais complexas e automatizadas via OpenCV, sem nunca comprometer a integridade e a cadeia de custódia dos metadados estruturais.

Ao longo desta apresentação, abordaremos detalhadamente quatro pilares práticos:

1. **Controle de Recortes Base**: A inclusão, ajuste milimétrico e eliminação de quadros de *crop*, mantendo a consistência visual e a proporção de aspeto.  
2. **Segmentação Avançada de Layouts (Topos Ortogonais)**: Como quebrar a rigidez de um retângulo para contornar artigos de jornais e páginas complexas, isolando apenas a informação útil.  
3. **Deskew Manual e Correção de Perspetiva**: O uso da homografia de 4 pontos para retificar e planificar digitalmente documentos capturados sob ângulos desfavoráveis ou não-ortogonais.  
4. **Automação Multi-Crop**: Estratégias para duplicar, espelhar e processar múltiplos recortes simultâneos, maximizando a produtividade de projetos de digitalização em larga escala.

Nas páginas seguintes aprenda sobre a lógica visual e os fluxos operacionais que garantem ao Vidya um padrão de excelência arquivística. Vamos dar início à sessão.

## **1\. Inclusão, Modificação e Remoção de Retângulos de Recorte**

A interface de recorte padrão do Vidya utiliza marcações poligonais dinâmicas que podem ser controladas via mouse ou Menu de Contexto (botão direito).

* **Inclusão de Novos Quadros**: Para adicionar áreas de recorte extras, clique com o botão direito na área de trabalho e selecione "Criar um quadro novo (tamanho da imagem)". Você também pode clonar o marcador selecionando "Duplicar o quadro atual" ou "Duplicar o polígono atual".  
* **Modificação por Arraste**: Posicione o mouse sobre qualquer aresta da marcação. O cursor mudará para indicar a direção de redimensionamento permitida (horizontal, vertical ou livre). Clique e arraste para redimensionar.  
* **Ajuste Rápido de Tamanho**: Pelo Menu de Contexto, acesse "Ajustar Tamanho do Recorte..." para aplicar proporções exatas pré-definidas em relação à imagem original, variando de 100% até 25%.  
* **Trava de Proporção**: Para manter o aspecto visual sem distorções ao arrastar, clique com o botão direito e ative "Habilitar Trava de Proporção".  
* **Empilhamento Visual**: Em imagens com múltiplos recortes, use "Trazer para Frente" ou "Enviar para Trás" para organizar quais quadros se sobrepõem na interface.  
* **Remoção**: Para deletar um recorte específico, clique com o botão direito sobre ele e selecione "Remover este Quadro" (ou Polígono). Para limpar rapidamente todo o progresso e voltar à estaca zero, selecione "Remover extras e resetar o quadro principal".

## **2\. Contornos Ortogonais para Jornais e Layouts Complexos**

O sistema suporta a conversão do retângulo básico em polígonos complexos, ideal para capturar artigos de jornais não-lineares ou isolar colunas específicas.

* **Criando um Recorte Complexo (Topos)**: Clique com o botão direito exatamente sobre a aresta que deseja quebrar e selecione "Criar Topo nesta Aresta". O sistema calculará as proporções geométricas e injetará quatro novos vértices (formando uma espécie de degrau ou reentrância) que podem ser arrastados independentemente.  
* **Simplificando Contornos (União)**: Caso os degraus fiquem curtos demais (arestas de 100 pixels ou menos), você pode clicar com o botão direito sobre eles e selecionar "Unir arestas adjacentes (Simplificar)". O algoritmo do Vidya moverá inteligentemente a aresta mais curta em direção à mais longa para achatar o polígono e remover vértices inúteis, garantindo que a forma nunca tenha menos que 4 pontas.  
* **Preenchimento Automático do Fundo**: Durante o processamento, a área que ficar **fora** desse polígono será ocultada. O sistema utilizará a forma ortogonal como uma máscara de corte. A parte descartada será automaticamente substituída por uma cor de fundo personalizável (Transparente, Branco, Preto ou um código HEX específico) de acordo com suas configurações.

### 

## **3\. Alinhamento Manual e Correção de Perspectiva**

Quando os documentos são fotografados com forte angulação, ondulações extremas ou desvios que a inteligência automática não consiga resolver, o Vidya permite o uso da Retificação de Perspectiva através da marcação de um quadrilátero livre (Homografia).

* **Iniciando a Correção**: Clique com o botão direito e selecione "Iniciar alinhamento manual (Deskew de 4 pontos)".  
* **Marcação Visual**: Na tela, você criará um traçado marcando as extremidades exatas do documento. O sistema unirá os 4 pontos com uma linha amarela tracejada de alto contraste e aplicará nós circulares amarelos nos cantos. Esses nós podem ser arrastados individualmente para ajuste fino.  
* **Processamento da Transformação**: Durante a exportação, o motor do Vidya detectará os 4 pontos independentemente da ordem em que você os clicou. Ele ordenará matematicamente os cantos (Superior-Esquerdo, Superior-Direito, Inferior-Direito, Inferior-Esquerdo) e esticará essa área de volta para formar um retângulo perfeito.  
* **Preservação da Resolução**: A imagem final retificada terá a perspectiva corrigida, mas será exportada forçando as dimensões da fotografia original, garantindo a ausência de perdas na área legível.  
* **Cancelamento**: A qualquer momento, você pode abortar o ajuste clicando com o botão direito e selecionando "Cancelar alinhamento manual" ou "Remover pontos de alinhamento manual".

### 

## **4\. Geração de Múltiplos Recortes (Multi-Crop)**

O sistema foi preparado para acelerar o fluxo em projetos onde mais de um documento/página é capturado na mesma foto.

* **Modo Berço em V (Câmera Dupla)**: O Menu de Contexto oferece opções dinâmicas como "Copiar Recorte do Lado Oposto" e "Copiar Recorte do Lado Oposto (Espelhado)". Essa função permite que um layout de recorte ajustado na câmera da esquerda seja perfeitamente refletido na câmera da direita.  
* **Replicação de Configurações**: Você pode "Habilitar Replicação" para que, em fluxos de trabalho emparelhados, as edições de um marcador sejam refletidas sistematicamente.  
* **Câmera Única Múltiplos Itens**: Se você tirar foto de múltiplas fotos/documentos espalhados numa mesa, basta usar o comando "Criar um quadro novo" para colocar um marcador sobre cada item isolado. O motor de processamento separará matematicamente cada quadro na imagem final, adicionando um sufixo rotulado (clip) ao nome de arquivo gerado de cada recorte.

