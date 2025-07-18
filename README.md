# Chatbot da Câmara Municipal do Porto

Um chatbot inteligente especializado em responder perguntas sobre documentos da Câmara Municipal do Porto, utilizando processamento de linguagem natural e RAG (Retrieval-Augmented Generation).

### Como usar a interface web:

1. **Instalar dependências:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Iniciar o Ollama (em um terminal separado):**
   ```bash
   ollama run llama2:latest
   ```

3. **Executar o servidor web:**
   ```bash
   python app.py
   ```

4. **Abrir no navegador:**
   ```
   http://localhost:5000
   ```

### Funcionalidades da Interface Web:

- ✅ Interface moderna e responsiva
- ✅ Chat em tempo real
- ✅ Indicador de status do chatbot
- ✅ Exemplos de perguntas
- ✅ Suporte a Enter para enviar mensagens
- ✅ Design adaptável para mobile
- ✅ Feedback visual durante processamento

## 📋 Pré-requisitos

- Python 3.12+
- Ollama instalado e configurado
- Modelo llama2:latest baixado

## 🔧 Instalação

1. **Instalar Ollama:**
   - Visite: https://ollama.ai
   - Siga as instruções de instalação

2. **Baixar o modelo:**
   ```bash
   ollama pull llama2:latest
   ```

3. **Instalar dependências Python:**
   ```bash
   pip install -r requirements.txt
   ```

## 🎯 Como usar

### Interface Web (Recomendado)
```bash
# Terminal 1: Iniciar Ollama
ollama run llama2:latest

# Terminal 2: Iniciar servidor web
python app.py

# Abrir http://localhost:5000 no navegador
```

### Modo Console
```bash
# Terminal 1: Iniciar Ollama
ollama run llama2:latest

# Terminal 2: Executar chatbot
python chatbot.py
```

## 📁 Estrutura do Projeto

```
├── app.py                 # Servidor Flask para interface web
├── chatbot.py            # Classe principal do chatbot
├── rag_processor.py      # Processamento RAG
├── templates/
│   └── index.html        # Interface web
├── requirements.txt      # Dependências Python
├── downloads/           # PDFs 
├── vector_store/        # Armazenamento de vetores
└── README.md           # Este arquivo
```

## 🔍 Funcionalidades

- **RAG (Retrieval-Augmented Generation)**: Busca em documentos relevantes
- **Processamento de PDFs**: Extração automática de texto
- **Interface Web**: Interface moderna e responsiva
- **API REST**: Endpoints para integração
- **Logging**: Sistema de logs detalhado
- **Tratamento de Erros**: Gestão robusta de erros

## 🌐 Endpoints da API

- `GET /` - Interface web
- `POST /api/chat` - Enviar mensagem
- `GET /api/status` - Status do chatbot
- `POST /api/reload` - Recarregar documentos

## ⚠️ Limitações e Observações Importantes

- O chatbot **só responde perguntas relacionadas ao conteúdo dos ficheiros PDF presentes no diretório `downloads`**. Perguntas fora desse escopo não serão respondidas.
- O **tempo de resposta pode variar entre 1 e 3 minutos**, dependendo da complexidade da pergunta e do processamento dos documentos.

