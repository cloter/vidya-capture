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

## **3\. Interface Principal e Edição**

A interface de captura do Vidya Capture é projetada para ser limpa, ergonômica e totalmente controlável por atalhos de teclado (ou pedais), garantindo que as mãos do operador permaneçam livres para manusear o acervo físico. A tela adapta-se dinamicamente ao modo de operação escolhido na criação do projeto. Abaixo, detalhamos os layouts, os fluxos de trabalho e as opções avançadas.

### 

### **3.1. Layouts e Tipos de Captura**

O sistema opera em duas topologias estruturais distintas, alterando a interface gráfica para corresponder ao laboratório físico:

#### 

#### **3.1.1 Câmera Simples (Mesa Plana)**

* **Layout Visual:** Apresenta uma única e grande área de visualização central, maximizando o espaço na tela para observar detalhes do documento.  
* **Equipamentos e Processos:** Utilizado com scanners de mesa (protocolo SANE), uma câmera DSLR única apontada verticalmente para a mesa, ou webcams industriais de alta resolução (V4L)\[cite: 1, 4\].  
* **Tipos de Acervos:** Ideal para digitalização de documentos soltos, processos avulsos, mapas ou conjuntos de fotografias que podem ser espalhados sobre a mesa de uma só vez (como demonstrado na interface onde várias fotos antigas são capturadas simultaneamente).

#### 

#### **3.1.2 Câmera Dupla (Berço em V)**

* **Layout Visual:** A tela é dividida ao meio, apresentando duas áreas de visualização lado a lado (Câmera Esquerda e Câmera Direita).  
* **Equipamentos e Processos:** Opera com duas câmeras fotográficas sincronizadas (DSLR ou industriais), montadas fisicamente em ângulos específicos para capturar páginas opostas simultaneamente\[cite: 1, 4\].  
* **Tipos de Acervos:** Desenvolvido estritamente para materiais encadernados, como livros raros, códices e processos espessos que não podem (ou não devem) ser abertos em um ângulo plano de 180 graus devido à fragilidade da lombada.

### 

### **3.2. O Painel de Miniaturas (Thumbnails)**

Localizado na lateral esquerda, o painel de miniaturas atua como o histórico visual e o ponto de acesso à "máquina do tempo" do projeto.

**Opções e Interações no Painel:**

* **Visualização:** Mostra as últimas capturas realizadas. No modo câmera dupla, exibe os recortes esquerdo e direito vinculados.  
* **Menu de Contexto (Clique com o Botão Direito):**  
  * *Criar recortes automaticamente (Auto Crop):* Aciona a Inteligência Artificial para buscar as bordas do papel na imagem selecionada. No modo Câmera Dupla, o sistema perguntará se você deseja aplicar a inteligência em *Somente Esquerda*, *Somente Direita* ou *Em Ambas*.  
  * *Remover esta imagem / este par:* Exclui fisicamente os arquivos do disco rígido de forma irreversível.  
  * *Reconstruir miniaturas:* Força o sistema a varrer a pasta do projeto e recriar os ícones visuais para economizar memória RAM.  
* **Entrada na Edição:** Clicar com o botão esquerdo do mouse sobre qualquer miniatura carrega aquela foto antiga de volta para o visor central, iniciando o Modo de Edição\[cite: 2, 4\]. A miniatura em edição ganha um destaque amarelo brilhante para orientar o operador.

### 

### **3.3. Modo de Edição (Máquina do Tempo)**

Quando uma miniatura é clicada, o texto das câmeras fica vermelho com a mensagem **MODO DE EDIÇÃO (ESC para voltar)** e o botão de "Reiniciar" transforma-se no botão laranja **Encerra**. Qualquer ajuste nas bordas pontilhadas neste modo é salvo silenciosamente no disco sem precisar clicar em nada \[cite: 2, 4\].

#### **3.3.1 Opções de Ação no Modo de Edição (Alternadas pela Tecla TAB):**

Ao pressionar a tecla TAB (ou clicar no botão de Modo no canto inferior direito), a ação principal do sistema muda para corrigir erros passados no lote\[cite: 2, 4\]:

* **Alterar Recorte:** Ação passiva; apenas permite reajustar as guias geométricas sem disparar o obturador da câmera.  
* **Substituir Imagem / Substituir Par:** O visor volta a mostrar o vídeo ao vivo. Ao capturar, a nova foto sobrescreve fisicamente a foto antiga que estava com defeito (ex: mão na frente da lente, página desfocada)\[cite: 2, 4\].  
* **Substituir Esquerda / Substituir Direita (Apenas Câmera Dupla):** O sistema aciona o hardware, mas descarta o lado oposto, salvando a nova foto apenas sobre a página que estava estragada, preservando a irmã intacta\[cite: 2, 4\].  
* **Inserir Antes / Inserir Depois:** Aciona o "Deslocamento em Cascata". Se uma página colou e foi pulada, o sistema renomeia todas as centenas de arquivos seguintes no disco rígido, abrindo um espaço cronológico para inserir a nova captura exatamente no lugar esquecido\[cite: 2, 4\].

**Nota de Segurança:** Nos modos de inserção e substituição, o botão "Capturar" fica colorido e exige dois cliques (Preparar \-\> Confirmar) para evitar destruição acidental do acervo.

### 

### **3.4. Menu de Contexto dos Recortes (Edição Avançada)**

Ao clicar com o **botão direito** diretamente sobre a linha pontilhada geométrica de um recorte (Crop) na área de visualização, um vasto menu de manipulação matemática é revelado\[cite: 4, 6\].

#### **3.4.1 Opções Disponíveis:**

* **Topologia e Formas (Documentos Complexos):**  
  * *Criar Topo nesta Aresta:* Adiciona vértices (degraus) para contornar perfeitamente colunas de jornais antigos ou livros danificados.  
  * *Unir arestas adjacentes (Simplificar):* Achata recortes complexos removendo degraus desnecessários.  
* **Sincronização (Apenas Câmera Dupla):**  
  * *Copiar Recorte do Lado Oposto:* Clona o polígono da câmera vizinha de forma idêntica ou matematicamente *Espelhada*.  
* **Homografia e Perspectiva:**  
  * *Iniciar alinhamento manual (Deskew de 4 pontos):* Troca o retângulo por uma mira de 4 pontos livres para corrigir fisicamente distorções severas de perspectiva.


* **Transformações e Escalonamento Rápidos:**  
  * *Espelhar:* Horizontalmente ou Verticalmente.  
  * *Girar:* 90° no sentido Horário ou Anti-horário.  
  * *Ajustar Tamanho:* Escala matematicamente o quadro de 100% até 25% com um clique.  
* **Múltiplos Recortes (Apenas Câmera Simples):**  
  * *Criar um quadro novo:* Adiciona caixas de corte extras na mesma imagem para capturar fotografias espalhadas na mesa de uma só vez.  
  * *Duplicar quadro atual:* Clona o polígono selecionado injetando um desvio visual.  
  * *Remover extras e resetar:* Apaga todos os recortes adicionais e força o quadro principal a ocupar 100% da fotografia nativa.

### 

### **3.5. Outras Opções da Interface (Barras de Controle)**

A interface abriga atalhos diretos para não interromper a fluidez da digitalização:

* **Barra Superior (Toolbar):**  
  * *Preferências:* Atalho para as configurações globais do sistema.  
  * *Inverter:* Espelha as câmeras de lado caso as portas USB sejam detectadas inversamente pelo computador.  
  * *Controles de Zoom:* Mais zoom, Menos zoom e enquadramento automático.  
  * *Checkboxes (Proporção e Replicar):* Travam o aspecto (Aspect Ratio) do retângulo ao arrastar ou forçam que qualquer movimento feito na câmera esquerda reflita automaticamente na direita\[cite: 2, 4\].  
  * *Exportar:* Aciona o Worker assíncrono para processar o lote, retificar a geometria e gerar o PDF final\[cite: 2, 4\].  
  * *Tema (C/E):* O pequeno botão quadrado altera instantaneamente a interface entre o Tema Claro e o Tema Escuro.  
* **Barra Inferior (Rodapé):**  
  * Exibe atalhos rápidos do teclado (F1, F4), a pasta de destino exata em que o acervo está sendo salvo no momento, e a contagem total de imagens capturadas para a volumetria diária.

## **4\. Configuração Inicial e Criação de Projeto**

A aba **Projeto** na janela de Preferências do Vidya Capture é o ponto de partida do seu fluxo de digitalização. É nesta etapa que você define a estrutura de pastas, a topologia do seu hardware de captura e a identidade arquivística do lote documental. Abaixo, detalhamos cada uma das configurações presentes nesta seção.

#### 

### **4.1. Criação do Projeto e Importação de Pastas (aba Projeto)**

O primeiro passo para qualquer digitalização é definir onde os arquivos físicos e lógicos vão residir.  
Na seção **Pasta de Trabalho Ativa**, clique no botão **Selecionar/Importar/Criar**:

* **Para criar um novo projeto:** Navegue até o diretório raiz desejado no seu computador, crie uma nova pasta (por exemplo, work\_dir dentro de teste-crop) e selecione-a. O Vidya Capture passará a centralizar todas as capturas de imagem e arquivos de configuração JSON exatamente neste local.  
* **Para importar/retomar um projeto:** Se você precisar continuar um lote não finalizado, basta selecionar a pasta do projeto existente. O sistema identificará automaticamente o arquivo manifesto (project.json) e carregará todo o seu progresso anterior, incluindo marcações de recorte e metadados.

#### 

### **4.2. Tipos de Projetos (Topologia de Captura)**

Logo abaixo da pasta de trabalho, encontra-se o **Modo de Operação do Projeto**. O Vidya Capture foi desenhado para entender diferentes arquiteturas físicas de laboratório, oferecendo dois modos principais:

* **Mesa Plana (Câmera Única):** Ideal para digitalização de documentos soltos, fotografias, processos avulsos ou utilização de scanners de mesa (SANE). Toda a interface gráfica e o recorte automático serão otimizados para um único fluxo de imagem.  
* **Berço em V (Página Dupla):** Configuração voltada para a captura de livros e códices encadernados, em que duas câmeras operam simultaneamente fotografando as páginas da esquerda e da direita.

⚠️ **Atenção Estrutural:** O modo de operação define toda a topologia de captura e o banco de dados do projeto. Portanto, **ele não pode ser alterado após a criação do lote**. (Observe que, quando um projeto já está em andamento, como no exemplo da captura de tela, o menu suspenso fica bloqueado/acinzentado, protegendo a integridade do trabalho).

#### 

### **4.3. Preenchimento de Metadados e Sua Utilização**

A digitalização de preservação exige que a proveniência do objeto físico viaje junto com a sua representação digital. A seção **Metadados Descritivos do Projeto** serve para catalogar o acervo no momento zero da captura.  
Preencha os seguintes campos:

* **Nome do Projeto:** O título da sua campanha ou lote de digitalização (ex: *Teste Crop*).  
* **Descrição:** Detalhes sobre o escopo do projeto, estado de conservação ou objetivos específicos.  
* **Editor/Instituição:** A organização custodiadora responsável pelo acervo (ex: *MCG \- Museu Campos Gerais*).  
* **Fundo/Coleção:** O conjunto documental arquivístico a que o material pertence (ex: *Coleções de teste do MCG*).  
* **Operador (Criador):** O nome do técnico responsável por realizar a captura (ex: *cloter*).  
* *Nota: O campo **Data de Criação** é gerado e travado automaticamente pelo sistema assim que o projeto é salvo pela primeira vez.*

**Como estes metadados serão utilizados?** O sistema os processa e os mapeia para padrões arquivísticos internacionais (como o padrão *Dublin Core*). Quando a captura é finalizada e você aciona a exportação, o motor do Vidya Capture injeta essas informações diretamente na estrutura interna (XMP) do **PDF/A** final\[cite: 3, 4\]. Isso garante que o documento gerado possua prova de autoria nativa e esteja padronizado para ingestão em repositórios digitais.

### **4.4. Controle e Escolha dos Dispositivos (Aba Dispositivos)**

Na aba **Dispositivos**, você gerencia qual equipamento de hardware o Vidya Capture irá utilizar para extrair as imagens.

No campo **Dispositivo de Origem**, você deve selecionar a tecnologia apropriada no menu suspenso:

* **Câmeras:** Para uso de equipamentos fotográficos DSLR/Mirrorless\[cite: 1, 4\].  
* **V4L (Video for Linux 2):** Para uso de webcams e câmeras industriais USB\[cite: 1, 4\].  
* **Scanners:** Para uso de scanners de mesa ou de rede via protocolo SANE\[cite: 1, 4\].  
* **Classe Mock:** Uma classe de testes virtuais e simulação do sistema (conforme mostrado na interface).

### **4.5. Rotação das Câmeras ou Sensores (Aba Orientação)**

Na aba **Orientação**, você configura a orientação espacial da captura. Esta etapa é especialmente crítica para *book scanners* montados com **Berço em V**, onde as câmeras costumam ser fixadas de lado ou de cabeça para baixo\[cite: 1, 4\].

Para garantir que as imagens fiquem na orientação correta na tela (sem precisar girar cada foto manualmente após a captura), você pode definir a rotação base:

* **Rotação do Sensor Esquerdo:** Selecione entre 0°, 90°, 180° ou 270°\[cite: 1, 4\].  
* **Rotação do Sensor Direito:** Selecione entre 0°, 90°, 180° ou 270°\[cite: 1, 4\].

## **5\. Recortes, Imagens e Exportação**

Este módulo detalha as configurações avançadas de processamento de imagens e demarcação de recortes do Vidya Capture. As opções aqui definidas garantem que o documento digitalizado seja extraído com precisão do fundo da mesa de captura e exportado com a melhor relação entre qualidade e tamanho de arquivo. Abaixo, detalhamos o funcionamento das abas **Imagens** e **Marcadores**, conforme as configurações apresentadas.

### 

### **5.1 Aba Imagens: Inteligência e Processamento**

A aba "Imagens" centraliza os algoritmos de detecção automatizada e as regras de compressão final dos arquivos\[cite: 1, 4\].

#### 

#### **5.1.1 Inteligência de Recorte Automático (Auto Crop) e Múltiplos Recortes**

O motor de Auto Crop do Vidya atua analisando matematicamente o contraste da imagem para encontrar as bordas do papel, substituindo a necessidade de ajustar os polígonos de corte manualmente.

* **Perfil de Detecção:** Permite carregar pré-definições (ex: *Fundo Muito Escuro*) ou usar o modo *Customizado* para controle total dos algoritmos\[cite: 1, 4\].  
* **Desfoque de Fusão e Dilatação de Fissuras:** O desfoque (ex: ajustado em 21\) suaviza a imagem para ignorar pequenos defeitos na mesa, enquanto a dilatação (ex: ajustada em 4\) une virtualmente papéis rasgados ou bordas desbotadas antes do cálculo do corte.  
* **Margem de Segurança e Área Mínima:** A margem (ex: 1.00%) adiciona um respiro ao redor do documento cortado para não perder caracteres rentes à borda, e a área mínima (ex: 1.00%) instrui o sistema a ignorar manchas pequenas no fundo da mesa.  
* **Cálculo de Contraste e Múltiplos Recortes:** O contraste define como o software lê a borda (ex: *Forçar Fundo Preto*), enquanto o campo *Número Máximo de Quadros* (ajustado para *Ilimitado*) permite que o sistema identifique e separe múltiplos documentos que estejam espalhados na mesma foto, gerando recortes individuais para cada um\[cite: 1, 4, 7\].  
* **Controle de cor de fundo para auto-crop:** Ao marcar "Usar cor de fundo customizada para os recortes", você pode definir um código hexadecimal exato (como \#252526). O algoritmo de inteligência utilizará esta cor estática específica para encontrar e mascarar o fundo com maior precisão.

#### 

#### **5.1.2 Controle de Cor de Fundo (Remoção)**

Esta seção atua fisicamente nos pixels de fundo da imagem final exportada.

* **Detectar e converter a cor de fundo:** Quando ativada, o sistema isola o documento e substitui ativamente a cor da mesa de captura.  
* **Substituição e Sensibilidade:** Você pode optar por substituir o fundo da mesa por uma cor sólida ou torná-lo *Transparente*, ajustando a agressividade da detecção através do controle de *Sensibilidade* (ex: \+20).

#### 

#### **5.1.3 Configuração do Controle das Exportações das Imagens**

Define o formato de arquivo que será gerado e inserido no PDF/A.

* **Formato de Saída:** O sistema suporta formatos como JPG, TIFF e PNG.  
* **Nível de Compressão/Qualidade:** Se você optar por PNG, poderá definir o nível de compressão (ex: nível 6). Se optar por JPG, controlará a qualidade percentual (ex: 95%). Estes ajustes afetam diretamente o peso do pacote BagIt e do PDF final.

#### **5.1.4 Controles Adicionais de Imagens**

* **Brilho e Contraste:** Sliders numéricos (ex: 0%) que aplicam ajustes globais de iluminação via software logo após o clique da câmera, antes da imagem ser salva no projeto.

### 

### **5.2 Aba Marcadores: Configuração Visual**

A aba "Marcadores" não altera os arquivos físicos exportados, mas customiza a interface de operação vetorial para garantir conforto visual e precisão durante o uso dos recortes manuais ou avaliação do Auto Crop\[cite: 1, 4\].

#### 

#### **5.2.1 Transparência e Largura dos Marcadores**

* **Cor do Marcador:** Define as cores das linhas de recorte para cada câmera. Exemplo: *Verde* para o marcador Esquerdo e *Ciano* para o marcador Direito.  
* **Cor de Preenchimento de Recorte:** Permite aplicar uma cor sólida ou manter a área útil *Transparente*\[cite: 1, 4\].  
* **Opacidade do Fundo:** Escurece ou clareia a parte da imagem que será "descartada" pelo recorte (ex: 3% de opacidade para um escurecimento muito suave).  
* **Espessura da Borda Dinâmica:** Controla a grossura da linha pontilhada de corte (ex: 75%), que se autoajusta conforme o zoom da imagem para nunca sumir da tela.

#### 

#### **5.2.2 Bordas nas Visualização das Imagens**

* **Controle da Moldura:** Permite desenhar uma borda virtual ao redor dos limites originais da fotografia na interface gráfica.  
* **Parâmetros da Borda:** Você pode configurar a *Largura* (ex: 3 px), a *Cor* (ex: Preto), a *Opacidade* (ex: 50%) e o tipo de *Traço* (ex: Pontos).

### 

### **5.3 Como Estes Ajustes Afetam a Exportação Final**

Durante a captura (ao pressionar Espaço ou Enter), o Vidya armazena os recortes poligonais (manuais ou calculados pelo Auto Crop) no arquivo project.json e nos manifestos \_clip\_N.json sem destruir a fotografia original em alta resolução.

O impacto real destas configurações acontece quando você pressiona **F12 (Exportar)**:

* O *Worker Assíncrono* do sistema intercepta a imagem original e lê as coordenadas de geometria gravadas.  
* O sistema fisicamente recorta as imagens, removendo o lixo indesejado da mesa (inclusive gerando vários arquivos isolados se o Auto Crop ilimitado identificou múltiplos documentos).  
* O algoritmo de Remoção de Fundo converte os pixels externos ao documento em transparência (conforme configurado na sensibilidade \+20).  
* Por fim, a imagem resultante é comprimida usando o motor do OpenCV no formato selecionado (ex: PNG compressão 6\) e enviada para o empacotamento PDF/A.  
* Toda esta cadeia de transformações destrutivas é registrada nos metadados PREMIS para garantir a rastreabilidade arquivística\[cite: 4, 5\].

## **6\. Calibração Preditiva e Geração de OCR**

Este módulo orienta o operador na utilização das ferramentas de otimização automatizada por Inteligência Artificial e na configuração do pipeline de Reconhecimento Óptico de Caracteres (OCR) do Vidya Capture.

### 

#### **Calibração Preditiva (Motor IA Optuna)**

A calibração preditiva substitui o ajuste manual de tentativa e erro por uma otimização matemática baseada em estatística, garantindo o comportamento ideal dos algoritmos para o lote inteiro de documentos.

#### **Quando Fazer a Calibração Preditiva**

A calibração por IA deve ser realizada assim que o projeto ativo possuir um volume inicial de capturas válidas. O sistema exige essa base de dados prévia para que o amostrador consiga realizar um sorteio estratificado e gerar um pool de imagens representativo das variações de iluminação e tipografia do lote.

#### 

### **6.1 O Que Calibrar (Escopo da Otimização)**

O motor de IA avalia e calibra simultaneamente dois grandes blocos operacionais pós-captura:

#### **Inteligência de Recorte (Auto Crop):**

Encontra os valores ideais para o *Desfoque de Fusão* (ac\_blur), a *Dilatação Morfológica* (ac\_dilate) e o método de *Cálculo de Contraste* (ac\_invert).

#### **Pré-processamento de OCR:**

Refina os limites matemáticos da limpeza de imagem, ajustando os hiperparâmetros de *Remoção de Ruído (h)* (ocr\_denoise\_h), *Realce de Contraste (CLAHE)* (ocr\_clahe\_clip), tamanho de janela adaptativa (*Binarização \- Block Size*, ocr\_block\_size) e o fator de corte constante (*Binarização \- C Value*, ocr\_c\_val).

#### 

### **6.1.1 Controles e Número de Interações**

O processo é gerenciado diretamente através do painel de calibração nas configurações do sistema:

* **Configuração do Sorteio:** O operador define o número de sessões e a quantidade de amostras coletadas por sessão que formarão a base de testes.  
* **Gabarito (Ground Truth):** O sistema abre uma interface de marcação visual para que o operador aponte manualmente o recorte e o alinhamento perfeito sobre o pool sorteado, servindo de alvo para a máquina.  
* **Ciclo de Iterações:** Ao dar partida no treinamento, a thread executa de forma assíncrona o número de ciclos estipulado na configuração. Uma janela modal ("Calibração Preditiva") exibe o progresso em tempo real e disponibiliza um controle de interrupção imediata ("Abortar Treinamento").  
* **Gravação do Manifesto:** Ao finalizar as interações, a IA injeta os parâmetros calculados nas preferências, assume o "Perfil Otimizado por IA" e grava permanentemente os coeficientes no arquivo project.json do lote atual.

### 

### **6.2 Reconhecimento Óptico de Caracteres (OCR)**

O módulo de OCR é o responsável por transformar a matriz de imagens capturadas em um documento PDF/A pesquisável, indexável e em conformidade com as normas internacionais de preservação digital.

#### 

#### **Quando Realizar o Pré-processamento**

O pré-processamento (Binarização OpenCV) ocorre imediatamente após as correções geométricas (como *Deskew* e *Dewarp*) e antes de os dados serem encaminhados para o motor de OCR. Ele atua isolando os caracteres de texto do fundo do papel, eliminando sombras e manchas físicas que degradam a precisão do reconhecimento textual.

#### **6.2.1 Manual Versus Calibração por IA**

* **Modo Manual:** O operador utiliza a interface visual de preferências para arrastar os sliders de filtragem base (Cor do Papel, Intensidade da Impressão, Tamanho e Profundidade das Manchas). Exige constante validação visual do técnico a cada mudança de tipografia ou cor de documento.  
* **Otimização por IA:** O motor assume o controle dos limiares de binarização a partir da matemática preditiva gerada no treinamento, aplicando os filtros de forma uniforme e precisa para todas as páginas do lote sem intervenção humana.

#### **6.2.2 Como Escolher os Parâmetros Manuais para o Pré-processamento**

Caso opte pela operação manual, o ajuste dos parâmetros de binarização deve buscar o equilíbrio estrito entre legibilidade e eliminação de ruído:

* O tamanho do bloco e o valor C devem ser configurados de forma a não "esvaziar" o corpo das letras (binarização agressiva) e, simultaneamente, não transformar manchas escuras de umidade ou dobras da lombada em blocos pretos de falso texto.

#### **6.2.3 Parâmetros do Tesseract**

Ao habilitar a extração de texto via Tesseract 5, três parâmetros fundamentais governam o desempenho e a saída do sistema no momento da exportação em lote (F12):

* **Idiomas Base (**ocr\_lang**):** Define os dicionários linguísticos aplicados na varredura. Permite a combinação de múltiplos idiomas (ex: por+eng para processar documentos que mesclam termos em português e inglês), refinando a precisão do reconhecimento de caracteres especiais.  
* **Núcleos CPU (**ocr\_jobs**):** Controla o limite de threads paralelos alocados para o processamento do OCR. Configurar este limite impede que o motor consuma toda a capacidade de processamento da estação de trabalho, protegendo o sistema contra travamentos de CPU.  
* **Arquivamento Extra (**ocr\_sidecar**):** Diretiva que instrui o software a gerar e salvar um arquivo de texto limpo e isolado (.txt) contendo o conteúdo integral do lote. Este arquivo gerado via *sidecar* serve como ferramenta de preservação complementar e facilita a indexação automática em bancos de dados e repositórios digitais como o Omeka S.

## **7\. Exportação Final e Cadeia de Custódia Digital**

Este módulo orienta o operador na configuração das políticas de pós-processamento, consolidação do arquivo final e nos parâmetros de conformidade arquivística que garantem a autenticidade e a integridade do acervo digitalizado.

### 

### **7.1. Aba Processar: Diretivas de Lote e Exportação Final**

A aba **Processar** define o pipeline de transformações geométricas e a lógica de montagem do pacote digital final. É nesta etapa que as instruções matemáticas salvas nos arquivos JSON durante a captura ou edição são convertidas em modificações físicas sobre as matrizes de imagem.

#### **7.1.1 Ações para Executar em Lote**

O operador pode marcar e desmarcar quais módulos do motor de processamento assíncrono serão ativados ao acionar a exportação:

* **Cortar (Crop):** Trunca fisicamente a imagem limitando-a à área útil delimitada pelos marcadores. Em cenários de múltiplos recortes na mesma foto, o motor gera arquivos independentes contendo o sufixo rotulado (*clip*).  
* **Alinhamento (Deskew OpenCV) e Planificação Geométrica (Dewarp):** Aplica a retificação do horizonte textual por regressão linear e corrige a deflexão gerada pela curvatura da lombada dos livros. Ambas as ações utilizam o nível de intensidade parametrizado pelo operador (padrão 100%).  
* **Produzir PDF Unificado:** Consolida todas as páginas processadas do projeto em um arquivo final indexado.

#### **7.1.2 Filtros de Escopo e Estrutura**

* **Ignorar Primeira e Última Imagens:** Útil em fluxos com berço em V (página dupla) para descartar automaticamente capturas de capas vazias ou contra-capas que não demandam processamento textual.  
* **Fonte de Imagens para o PDF Final:** Permite ao laboratório escolher o nível de intervenção visual que comporá o documento distribuído:  
  1. *Imagens de Entrada (Brutas):* Compila o PDF com as capturas originais do sensor, ignorando correções geométricas e limpezas.  
  2. *Imagens Originais:* Utiliza as fotografias com retificação geométrica aplicada (Deskew/Dewarp), preservando as cores e texturas nativas do papel.  
  3. *Imagens Tratadas:* Inclui as imagens que passaram pelo pipeline completo, incluindo a binarização adaptativa de alto contraste do OCR, otimizando o peso do arquivo e a leitura em telas.

#### **7.1.3 Destino e Governança de Arquivos**

* **Diretório de Destino:** O documento final consolidado é gravado por padrão na pasta out configurada no diretório raiz do projeto.  
* **⚠️ Regra de Limpeza Temporária:** A opção *"Depois de copiar o PDF com sucesso, remover todos os arquivos temporários"* deve ser ativada com cautela. Se marcada, o software apagará as imagens isoladas binarizadas e as matrizes intermediárias após a validação do PDF/A, preservando apenas o arquivo unificado e poupando espaço de armazenamento na estação.

### **7.2. Aba Custódia: Garantias de Preservação e Cadeia de Custódia**

A aba **Custódia** implementa os controles e padrões arquivísticos internacionais essenciais para assegurar o valor legal, a imutabilidade e a fixidez dos documentos digitais.

#### 

#### **7.2.1 Garantia de Fixidez e Prova de Origem**

* **Calcular e Selar Hash SHA-256:** Cria uma assinatura matemática criptográfica exclusiva para cada arquivo de imagem gerado no lote em tempo real. O hash funciona como um lacre digital: qualquer tentativa posterior de adulteração física nos pixels ou metadados quebrará a correspondência matemática, alertando o sistema de custódia. Embora adicione um leve overhead de processamento em discos lentos, sua ativação é vital para fins de auditoria e preservação permanente.

#### 

#### **7.2.2 Rastreabilidade de Transformações (Padrão PREMIS)**

* **Registrar Eventos de Processamento no Manifesto:** Incorpora uma trilha de auditoria completa dentro do arquivo central project.json do lote, mapeada sob o padrão arquivístico internacional PREMIS (*Preservation Metadata: Implementation Strategies*). Cada intervenção (como a intensidade do Deskew, aplicação de Auto Crop ou falhas de binarização) ganha um registro de evento imutável associado à página, detalhando o algoritmo e o operador responsável.

#### **7.2.3 Estruturas de Distribuição e Ingestão em Repositórios**

O Vidya Capture prepara os metadados e os pacotes digitais para conversão e diálogo com plataformas institucionais através de duas diretivas de exportação:

* **Empacotar em Padrão Internacional BagIt:** Estrutura o diretório final criando manifestos de carga estruturados (tag manifests), exigidos para a transferência segura e ingestão automatizada em softwares de preservação digital e repositórios como Archivematica, AtoM e DSpace.  
* **Exportar Metadados Tabulares (.TSV):** Consolida um arquivo com delimitadores por tabulação contendo os campos descritivos preenchidos na criação do projeto (padrão *Dublin Core* e *Schema.org*). O operador pode configurar o arquivo TSV para incluir duas colunas adicionais de alta relevância:  
  1. *Coluna de Integridade:* Associa o Hash SHA-256 correspondente a cada linha/página.  
  2. *Coluna de Texto Integral:* Injeta o texto bruto extraído pelo OCR (Tesseract), permitindo a indexação em massa e importação direta em repositórios como o Omeka S e Tainacan.

#### 

  #### **Granularidade da Auditoria**

* **Nível do Registro:** O operador define a profundidade da fiscalização do manifesto, variando entre o *Registro Global (Ao nível do Livro)* — que gera um sumário unificado das operações do volume — e o *Registro por Página*, que detalha as coordenadas isoladas de cada folha do acervo.

