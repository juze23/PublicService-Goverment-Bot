from flask import Flask, render_template, request, jsonify
from chatbot import GovernmentChatbot
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize chatbot globally
chatbot = None

def initialize_chatbot():
    """Initialize the chatbot with error handling."""
    global chatbot
    try:
        chatbot = GovernmentChatbot()
        logger.info("Chatbot initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize chatbot: {str(e)}")
        return False

@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat requests."""
    try:
        data = request.get_json()
        question = data.get('message', '').strip()
        
        if not question:
            return jsonify({'error': 'Mensagem vazia'}), 400
        
        if chatbot is None:
            return jsonify({'error': 'Chatbot não inicializado. Verifique se o Ollama está rodando.'}), 500
        
        logger.info(f"Processing question: {question}")
        answer = chatbot.ask(question)
        
        return jsonify({
            'response': answer,
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@app.route('/api/status')
def status():
    """Check chatbot status."""
    if chatbot is None:
        return jsonify({'status': 'error', 'message': 'Chatbot não inicializado'})
    return jsonify({'status': 'ready', 'message': 'Chatbot pronto'})

@app.route('/api/reload', methods=['POST'])
def reload_documents():
    """Reload documents from PDFs."""
    try:
        if chatbot is None:
            return jsonify({'error': 'Chatbot não inicializado'}), 500
        
        chatbot.reload_documents_from_pdfs()
        return jsonify({'message': 'Documentos recarregados com sucesso'})
        
    except Exception as e:
        logger.error(f"Error reloading documents: {str(e)}")
        return jsonify({'error': f'Erro ao recarregar documentos: {str(e)}'}), 500

if __name__ == '__main__':
    # Initialize chatbot on startup
    if initialize_chatbot():
        print("✅ Chatbot inicializado com sucesso!")
        print("🌐 Servidor web iniciando em http://localhost:5000")
        print("📝 Certifique-se que o Ollama está rodando com: ollama run llama2:latest")
    else:
        print("❌ Falha ao inicializar o chatbot")
        print("🔧 Verifique se o Ollama está instalado e rodando")
        print("📖 Para instalar: https://ollama.ai")
        print("🚀 Para rodar: ollama run llama2:latest")
    
    # Run the Flask app
    app.run(debug=True, host='0.0.0.0', port=5000) 