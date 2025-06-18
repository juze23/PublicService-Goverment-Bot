import json
import logging
from typing import List, Dict, Any
from rag_processor import RAGProcessor
import requests
import os
from pathlib import Path
import PyPDF2
import io

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CamMunPortoChatbot:
    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "llama2:latest"):
        """Initialize the chatbot with RAG and Ollama."""
        self.ollama_url = ollama_url
        self.model = model
        self.rag = RAGProcessor()
        
        # Load documents from JSON files if they exist
        self._load_documents()
        
        # Check if Ollama is running and model is available
        try:
            response = requests.get(f"{ollama_url}/api/tags")
            if response.status_code != 200:
                raise Exception("Ollama server is not running. Please start Ollama first.")
            
            available_models = [m['name'] for m in response.json()['models']]
            if model not in available_models:
                logger.warning(f"Model {model} not found. Available models: {available_models}")
                if 'llama2:latest' in available_models:
                    logger.info("Using llama2:latest as fallback model")
                    self.model = 'llama2:latest'
                else:
                    raise Exception(f"Model {model} not found and no fallback available. Please install a model using 'ollama pull llama2:latest'")
            
            logger.info(f"Using model: {self.model}")
        except requests.exceptions.ConnectionError:
            raise Exception("Could not connect to Ollama server. Please make sure Ollama is running.")
        
        logger.info("Chatbot initialized with RAG and Ollama")

    def _load_documents(self):
        """Load documents from existing vector store or process PDFs from downloads folder."""
        try:
            # Check if vector store already has documents loaded
            if self.rag.texts and len(self.rag.texts) > 0:
                logger.info(f"Vector store already contains {len(self.rag.texts)} documents")
                logger.info("Using existing processed documents from vector store")
                return
            
            # If no documents in vector store, try to load from JSON files first
            json_files = ['pdf_downloads.json']
            loaded_files = []
            
            for json_file in json_files:
                try:
                    if os.path.exists(json_file):
                        logger.info(f"Loading documents from {json_file}...")
                        self.rag.load_from_json(json_file)
                        loaded_files.append(json_file)
                        logger.info(f"Successfully loaded {json_file}")
                    else:
                        logger.info(f"File {json_file} not found, skipping...")
                except Exception as e:
                    logger.error(f"Error loading {json_file}: {str(e)}")
            
            # If still no documents, try processing PDFs directly
            if not self.rag.texts or len(self.rag.texts) == 0:
                logger.info("No documents loaded from JSON, trying to process PDFs directly...")
                self._process_pdfs_from_downloads()
            
            if self.rag.texts and len(self.rag.texts) > 0:
                logger.info(f"Successfully loaded {len(self.rag.texts)} documents")
            else:
                logger.warning("No documents were loaded. The chatbot will only respond to questions about the test documents.")
                
        except Exception as e:
            logger.error(f"Error in _load_documents: {str(e)}")
            logger.info("Continuing with existing vector store data...")

    def _process_pdfs_from_downloads(self):
        """Process PDFs directly from the downloads folder."""
        downloads_path = Path("downloads/pdfs")
        if not downloads_path.exists():
            logger.warning("Downloads folder not found")
            return
        
        documents = []
        
        # Walk through all subdirectories in downloads/pdfs
        for category_dir in downloads_path.iterdir():
            if category_dir.is_dir():
                category_name = category_dir.name
                logger.info(f"Processing PDFs from category: {category_name}")
                
                for pdf_file in category_dir.glob("*.pdf"):
                    try:
                        logger.info(f"Processing PDF: {pdf_file.name}")
                        
                        # Extract text from PDF
                        text_content = self._extract_text_from_pdf(pdf_file)
                        
                        if text_content.strip():
                            doc = {
                                'content': text_content,
                                'source': str(pdf_file),
                                'title': pdf_file.stem,
                                'date': 'unknown',
                                'category': category_name
                            }
                            documents.append(doc)
                            logger.info(f"Successfully processed {pdf_file.name}")
                        else:
                            logger.warning(f"No text extracted from {pdf_file.name}")
                            
                    except Exception as e:
                        logger.error(f"Error processing {pdf_file.name}: {str(e)}")
        
        if documents:
            logger.info(f"Processed {len(documents)} PDF documents")
            self.rag.process_documents(documents)
        else:
            logger.warning("No PDF documents were processed")

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text content from a PDF file."""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                
                return text.strip()
                
        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {str(e)}")
            return ""

    def reload_documents_from_pdfs(self):
        """Reload documents by processing PDFs from downloads folder."""
        logger.info("Reloading documents from PDFs...")
        self._process_pdfs_from_downloads()
        logger.info("Document reload completed")

    def _limit_context_length(self, context: str, max_length: int = 12000) -> str:
        """Limit the context length to avoid overly long prompts."""
        if len(context) <= max_length:
            return context
        
        # Truncate context while keeping document structure
        truncated = context[:max_length]
        # Try to end at a complete document boundary
        last_doc_marker = truncated.rfind("=== DOCUMENTO")
        if last_doc_marker > max_length * 0.8:  # If we can find a document boundary in the last 20%
            truncated = truncated[:last_doc_marker]
        
        truncated += "\n\n[Contexto truncado para otimizar a resposta]"
        return truncated

    def _format_context(self, results: List[Dict[str, Any]]) -> str:
        """Format search results into a context string."""
        context = "Documentos relevantes encontrados:\n\n"
        for i, result in enumerate(results, 1):
            context += f"=== DOCUMENTO {i} ===\n"
            context += f"Título: {result['metadata']['title']}\n"
            context += f"Fonte: {result['metadata']['source']}\n"
            context += f"Data: {result['metadata']['date']}\n"
            context += f"Conteúdo:\n{result['content']}\n\n"
        return context

    def _generate_prompt(self, query: str, context: str) -> str:
        """Generate a prompt for Ollama with the query and context."""
        return f"""Você é um assistente virtual do governo português especializado em responder perguntas sobre documentos e serviços governamentais.

IMPORTANTE: 
1. Você só deve responder perguntas que estejam relacionadas com os documentos e informações disponíveis no contexto fornecido.
2. Se a pergunta não estiver relacionada com os documentos carregados, responda educadamente que só pode ajudar com questões relacionadas aos serviços e documentos governamentais disponíveis.
3. Quando encontrar informações relevantes, forneça um resumo DETALHADO e COMPLETO das informações encontradas nos documentos. NÃO apenas referencie "está no documento X" - extraia e apresente as informações importantes de forma clara e organizada.
4. Organize a resposta de forma lógica, destacando os pontos principais e fornecendo detalhes específicos quando relevante.
5. Se houver múltiplos documentos com informações complementares, integre essas informações numa resposta coesa.
6. Inclua informações específicas como datas, números, objetivos, programas, atividades, resultados, etc. quando disponíveis nos documentos.
7. Estruture a resposta com títulos, subtítulos e listas quando apropriado para facilitar a leitura.
8. Seja específico e detalhado - o utilizador quer informações completas, não apenas um resumo superficial.

Contexto dos documentos disponíveis:
{context}

Pergunta: {query}

Resposta detalhada:"""

    def _enhance_response(self, response: str, results: List[Dict[str, Any]]) -> str:
        """Enhance the response with additional context about sources and reliability."""
        if not results:
            return response
        
        # Add source information
        sources_info = "\n\n--- Fontes dos Dados ---\n"
        for i, result in enumerate(results, 1):
            sources_info += f"• Documento {i}: {result['metadata']['title']}\n"
        
        # Add reliability note
        reliability_note = "\n\nNota: Esta informação foi extraída dos documentos oficiais da Câmara Municipal do Porto. Para informações mais atualizadas, consulte diretamente os serviços municipais."
        
        return response + sources_info + reliability_note

    def ask(self, query: str, k: int = 5, relevance_threshold: float = 0.3) -> str:
        """Ask a question to the chatbot."""
        try:
            # Search for relevant documents
            logger.info(f"Searching for relevant documents for query: {query}")
            results = self.rag.search(query, k=k)
            
            if not results:
                return "Desculpe, não encontrei informações relevantes nos documentos disponíveis para responder à sua pergunta. Só posso ajudar com questões relacionadas aos serviços e documentos governamentais que foram carregados."
            
            # Check if the best result is relevant enough
            if len(results) > 0:
                best_score = results[0]['score']
                logger.info(f"Best search result score: {best_score}")
                
                if best_score < relevance_threshold:
                    return "Desculpe, a sua pergunta não parece estar relacionada com os documentos e serviços governamentais disponíveis. Só posso responder a perguntas sobre os serviços e documentos que foram carregados no sistema."
            else:
                return "Desculpe, não encontrei informações relevantes nos documentos disponíveis para responder à sua pergunta."
            
            # Format context from search results
            context = self._format_context(results)
            
            # Limit context length
            limited_context = self._limit_context_length(context)
            
            # Generate prompt
            prompt = self._generate_prompt(query, limited_context)
            
            # Call Ollama API
            logger.info("Calling Ollama API...")
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Error from Ollama API: {response.text}")
                return "Desculpe, ocorreu um erro ao processar sua pergunta."
            
            # Extract response from Ollama
            answer = response.json()["response"]
            logger.info("Successfully generated answer")
            
            # Enhance response with additional context
            enhanced_answer = self._enhance_response(answer, results)
            
            return enhanced_answer.strip()
            
        except Exception as e:
            logger.error(f"Error in ask method: {str(e)}")
            return "Desculpe, ocorreu um erro ao processar sua pergunta."

if __name__ == "__main__":
    # Test the chatbot
    try:
        # Initialize chatbot
        chatbot = CamMunPortoChatbot()
        logger.info("Chatbot initialized")
        
        # Interactive mode
        print("\nBem-vindo ao Chatbot do Governo!")
        print("Este chatbot responde apenas a perguntas relacionadas aos documentos e serviços governamentais carregados.")
        print("Digite 'sair' para terminar a conversa.")
        print("Certifique-se que o Ollama está rodando em outro terminal com o comando: ollama run llama2:latest")
        
        while True:
            question = input("\nSua pergunta: ").strip()
            if question.lower() in ['sair', 'exit', 'quit']:
                print("Até logo!")
                break
                
            if not question:
                continue
                
            print("\nProcessando sua pergunta...")
            answer = chatbot.ask(question)
            print(f"\nResposta: {answer}")
            
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        print(f"\nErro: {str(e)}")
        print("Certifique-se que o Ollama está instalado e rodando.")
        print("Para instalar o Ollama, visite: https://ollama.ai")
        print("Para instalar o modelo, execute: ollama pull llama2:latest")
        print("Para rodar o modelo, execute em outro terminal: ollama run llama2:latest") 