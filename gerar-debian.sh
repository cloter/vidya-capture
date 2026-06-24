#!/bin/bash
# Script de automação para gerar o pacote .deb do Vidya Capture (via dpkg-deb)
# sudo dpkg -i vidya-capture_0.1.x_all.deb; sudo apt --fix-broken install

echo "=========================================="
echo " Iniciando empacotamento do Vidya Capture"
echo "=========================================="

PKG_NAME="vidya-capture"
ARCH="all"
BUILD_DIR="build_deb"

# ==========================================
# 0. LÓGICA DE AUTO-INCREMENTO DE VERSÃO
# ==========================================
VERSION_FILE="version.txt"

# Se o ficheiro não existir, inicializa com 0.1.0
if [ ! -f "$VERSION_FILE" ]; then
    echo "0.1.0" > "$VERSION_FILE"
fi

# Lê a versão atual do ficheiro
CURRENT_VERSION=$(cat "$VERSION_FILE")

incrementar_versao() {
    local versao=$1
    local x y z v novo_x novo_y novo_z

    # Separa a string "x.y.z" nas variáveis x, y e z usando o ponto como delimitador
    IFS='.' read -r x y z <<< "$versao"

    # Aplica a lógica matemática multiplicando por base 100 e já soma 1
    v=$(( (x * 10000) + (y * 100) + z + 1 ))

    # Extrai os novos valores usando divisão inteira e resto (agora em blocos de 100)
    novo_z=$(( v % 100 ))
    novo_y=$(( (v / 100) % 100 ))
    novo_x=$(( v / 10000 ))

    # Imprime o resultado
    echo "$novo_x.$novo_y.$novo_z"
}

# Monta a nova versão
VERSION=$(incrementar_versao "$CURRENT_VERSION")

sed -i "s/^VIDYA_VERSION.*/VIDYA_VERSION = \"$VERSION\"/" main.py

# Grava a nova versão no ficheiro
echo "$VERSION" > "$VERSION_FILE"

echo "-> Versão detectada: $CURRENT_VERSION | Nova versão gerada: $VERSION"
# ==========================================

PKG_DIR="${BUILD_DIR}/${PKG_NAME}_${VERSION}_${ARCH}"

# 1. Limpa builds anteriores e cria a arquitetura
rm -rf $BUILD_DIR
mkdir -p $PKG_DIR/DEBIAN
mkdir -p $PKG_DIR/opt/vidya-capture
mkdir -p $PKG_DIR/opt/vidya-capture/docs
mkdir -p $PKG_DIR/usr/bin
mkdir -p $PKG_DIR/usr/share/applications
mkdir -p $PKG_DIR/usr/share/doc/$PKG_NAME
mkdir -p $PKG_DIR/usr/share/pixmaps

echo "-> Copiando o código fonte para a pasta /opt/..."
# Copiamos também a pasta assets para o Python encontrá-la
cp -r core gui hardware assets main.py $PKG_DIR/opt/vidya-capture/
[ -f "LICENSE" ] && cp LICENSE $PKG_DIR/opt/vidya-capture/

echo "-> Copiando o manual do utilizador..."
# Copia o PDF da pasta docs para a raiz do software em /opt/
cp "docs/Vidya Capture - Manual.pdf" "$PKG_DIR/opt/vidya-capture/docs/"

echo "-> Copiando utilitários e atalhos..."
cp vidya-capture $PKG_DIR/usr/bin/
cp vidya-capture.desktop $PKG_DIR/usr/share/applications/
cp assets/vidya_capture_icon.png $PKG_DIR/usr/share/pixmaps/

echo "-> Gerando documentação OSS (copyright)..."
# Ficheiro padrão do Debian (DEP-5) declarando a licença
cat <<EOF > $PKG_DIR/usr/share/doc/$PKG_NAME/copyright
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Vidya Capture
Source: https://www.uepg.br

Files: *
Copyright: 2026 LAMUHDI / UEPG
License: GPL-3.0+

License: GPL-3.0+
 Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo
 sob os termos da Licença Pública Geral GNU (GNU GPL) como publicado pela
 Free Software Foundation, quer a versão 3 da Licença, quer (a seu critério)
 qualquer versão posterior.
 .
 Este programa é distribuído na esperança de que seja útil,
 mas SEM QUALQUER GARANTIA; nem sequer a garantia implícita de
 COMERCIALIZAÇÃO ou ADEQUAÇÃO A UM DETERMINADO FIM. Consulte a
 Licença Pública Geral GNU para obter mais detalhes.
 .
 Nos sistemas Debian, o texto completo da Licença Pública Geral GNU 
 versão 3 pode ser encontrado no ficheiro \`/usr/share/common-licenses/GPL-3'.
EOF

echo "-> Gerando ficheiro de controle Debian..."
cat <<EOF > $PKG_DIR/DEBIAN/control
Package: $PKG_NAME
Version: $VERSION
Section: graphics
Priority: optional
Architecture: $ARCH
Depends: python3, python3-pyqt5, python3-opencv, python3-numpy, python3-sane, sane-utils, tesseract-ocr, tesseract-ocr-por, tesseract-ocr-eng, ocrmypdf, v4l2loopback-utils, v4l-utils, python3-gphoto2, python3-psutil
Maintainer: LAMUHDI / UEPG <coordenacao@uepg.br>
Description: O Vidya Capture é um OSS GPL-3.0+ para digitalização
 O Vidya Capture é uma solução técnica desenvolvida pelo
 LAMUHDI/UEPG para a digitalização profissional e preservação de
 acervos. O sistema orquestra a captura simultânea de imagens
 através de dispositivos como câmeras DSLR, scanners SANE ou
 interfaces V4L2, gerenciando fluxos de trabalho que incluem a
 substituição de páginas e inserções em cascata.
 .
 Para garantir a qualidade arquivística, o software integra
 algoritmos de visão computacional para correção de inclinação
 (deskew), planificação de curvaturas (dewarp) e recorte
 inteligente. Além do processamento de imagem, a ferramenta
 automatiza a geração de arquivos PDF/A-2b com metadados
 estruturados no padrão Dublin Core e suporte a OCR via
 Tesseract.
 .
 A interface gráfica, construída em PyQt5, oferece recursos
 avançados como visualização em tempo real, painel de miniaturas
 para auditoria e atalhos de teclado otimizados para
 laboratórios de digitalização. No núcleo do sistema, módulos de
 configuração e gerenciamento de projetos asseguram a
 integridade dos dados e a persistência das preferências do
 utilizador.
EOF

echo "-> Aplicando permissões corretas de instalação..."
chmod +x $PKG_DIR/usr/bin/vidya-capture
chmod +x $PKG_DIR/opt/vidya-capture/main.py
find $PKG_DIR/opt/vidya-capture -type d -exec chmod 755 {} \;
# Aplica permissões de leitura (644) ao PDF para que qualquer utilizador consiga abri-lo
chmod 644 "$PKG_DIR/opt/vidya-capture/docs/Vidya Capture - Manual.pdf"
chmod 644 $PKG_DIR/usr/share/doc/$PKG_NAME/copyright
# Garante a permissão de leitura para a pasta assets e o ícone
find $PKG_DIR/opt/vidya-capture/assets -type f -exec chmod 644 {} \;
chmod 644 $PKG_DIR/usr/share/pixmaps/vidya_capture_icon.png

echo "-> Construindo o pacote (dpkg-deb)..."

rm vidya-capture*_all.deb
dpkg-deb --build $PKG_DIR

if [ $? -eq 0 ]; then
    echo "-> Movendo o pacote final para a raiz..."
    mv ${BUILD_DIR}/*.deb ./
    rm -rf $BUILD_DIR
    echo "✅ SUCESSO: Pacote Debian gerado com as licenças OSS integradas!"
    echo "-> Instalando novo pacote..."
    sudo dpkg -i vidya-capture_"${VERSION}"_all.deb
    echo "-> Atualizando para instalação nas VMs..."
    rm ../Vidya/vidya-capture*_all.deb
    cp vidya-capture_"${VERSION}"_all.deb ../Vidya
    echo "✅ COPIADO: vidya-capture_${VERSION}_all.deb copiado para pasta do Vidya Pipeline"
else
    echo "❌ ERRO: Falha ao gerar o pacote com o dpkg-deb."
fi
