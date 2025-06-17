from typing import List, Dict, Any, Optional
import json
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
import re
import pickle
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleTextSplitter:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", ".", "!", "?", ",", " ", ""]

    def split_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap."""
        if not text:
            return []
            
        # First split by paragraphs
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = []
        current_length = 0
        
        for paragraph in paragraphs:
            # If paragraph is too long, split it into sentences
            if len(paragraph) > self.chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                for sentence in sentences:
                    if current_length + len(sentence) > self.chunk_size:
                        if current_chunk:
                            chunks.append(' '.join(current_chunk))
                            # Keep overlap
                            overlap_start = max(0, len(current_chunk) - self.chunk_overlap)
                            current_chunk = current_chunk[overlap_start:]
                            current_length = sum(len(s) for s in current_chunk)
                    current_chunk.append(sentence)
                    current_length += len(sentence)
            else:
                if current_length + len(paragraph) > self.chunk_size:
                    if current_chunk:
                        chunks.append(' '.join(current_chunk))
                        # Keep overlap
                        overlap_start = max(0, len(current_chunk) - self.chunk_overlap)
                        current_chunk = current_chunk[overlap_start:]
                        current_length = sum(len(s) for s in current_chunk)
                current_chunk.append(paragraph)
                current_length += len(paragraph)
        
        # Add the last chunk if it exists
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks

class RAGProcessor:
    def __init__(self, persist_directory: str = "vector_store"):
        """Initialize the RAG processor with vector store and embedding model."""
        try:
            # Ensure absolute path
            self.persist_directory = Path(os.path.abspath(persist_directory))
            logger.info(f"Initializing RAG processor with directory: {self.persist_directory}")
            
            # Create directory if it doesn't exist
            self.persist_directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created/verified directory: {self.persist_directory}")
            
            # Initialize the embedding model
            logger.info("Initializing embedding model...")
            self.embedding_model = SentenceTransformer(
                'distiluse-base-multilingual-cased-v2',
                device='cpu'
            )
            logger.info("Embedding model initialized successfully")
            
            # Initialize storage
            self.texts = []
            self.metadatas = []
            self.embeddings = None
            
            # Initialize text splitter
            self.text_splitter = SimpleTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
            
            # Load existing data if available
            self._load_from_disk()
            
        except Exception as e:
            logger.error(f"Error initializing RAG processor: {str(e)}")
            raise

    def _load_from_disk(self) -> None:
        """Load existing data from disk if available."""
        try:
            texts_path = self.persist_directory / "texts.pkl"
            embeddings_path = self.persist_directory / "embeddings.npy"
            metadata_path = self.persist_directory / "metadata.pkl"
            
            if all(p.exists() for p in [texts_path, embeddings_path, metadata_path]):
                logger.info("Loading existing data from disk...")
                with open(texts_path, 'rb') as f:
                    self.texts = pickle.load(f)
                with open(metadata_path, 'rb') as f:
                    self.metadatas = pickle.load(f)
                self.embeddings = np.load(embeddings_path)
                
                # Validate data consistency
                if len(self.texts) != len(self.metadatas) or len(self.texts) != self.embeddings.shape[0]:
                    logger.warning(f"Data inconsistency detected: texts={len(self.texts)}, metadatas={len(self.metadatas)}, embeddings={self.embeddings.shape[0]}")
                    logger.warning("Clearing corrupted data and starting fresh...")
                    self.texts = []
                    self.metadatas = []
                    self.embeddings = None
                    self._save_to_disk()
                else:
                    logger.info(f"Loaded {len(self.texts)} documents from disk")
            else:
                logger.info("No existing data found on disk")
        except Exception as e:
            logger.error(f"Error loading data from disk: {str(e)}")
            # Clear corrupted data
            self.texts = []
            self.metadatas = []
            self.embeddings = None
            self._save_to_disk()

    def _save_to_disk(self) -> None:
        """Save current data to disk."""
        try:
            texts_path = self.persist_directory / "texts.pkl"
            embeddings_path = self.persist_directory / "embeddings.npy"
            metadata_path = self.persist_directory / "metadata.pkl"
            
            logger.info(f"Saving {len(self.texts)} documents to disk...")
            
            # Save texts
            with open(texts_path, 'wb') as f:
                pickle.dump(self.texts, f)
            logger.info(f"Saved texts to {texts_path}")
            
            # Save metadata
            with open(metadata_path, 'wb') as f:
                pickle.dump(self.metadatas, f)
            logger.info(f"Saved metadata to {metadata_path}")
            
            # Save embeddings
            if self.embeddings is not None:
                np.save(embeddings_path, self.embeddings)
                logger.info(f"Saved embeddings to {embeddings_path}")
            
            logger.info("All data saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving data to disk: {str(e)}")
            raise

    def process_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Process and store documents in the vector store."""
        try:
            logger.info(f"Processing {len(documents)} documents...")
            new_texts = []
            new_metadatas = []
            
            for doc in documents:
                # Split document into chunks
                chunks = self.text_splitter.split_text(doc['content'])
                logger.info(f"Split document into {len(chunks)} chunks")
                
                # Add chunks and their metadata
                new_texts.extend(chunks)
                new_metadatas.extend([{
                    'source': doc.get('source', 'unknown'),
                    'title': doc.get('title', 'unknown'),
                    'date': doc.get('date', 'unknown'),
                    'chunk_index': i
                } for i in range(len(chunks))])
            
            # Generate embeddings for new texts
            logger.info("Generating embeddings for new texts...")
            new_embeddings = self.embedding_model.encode(new_texts, show_progress_bar=True)
            
            # Update storage
            self.texts.extend(new_texts)
            self.metadatas.extend(new_metadatas)
            
            # Handle embeddings properly
            if self.embeddings is None:
                self.embeddings = new_embeddings
            else:
                # Ensure both arrays have the same number of dimensions
                if self.embeddings.size == 0:
                    self.embeddings = new_embeddings
                else:
                    self.embeddings = np.vstack([self.embeddings, new_embeddings])
            
            # Validate consistency
            if len(self.texts) != len(self.metadatas) or len(self.texts) != self.embeddings.shape[0]:
                logger.error(f"Data inconsistency after processing: texts={len(self.texts)}, metadatas={len(self.metadatas)}, embeddings={self.embeddings.shape[0]}")
                raise ValueError("Data arrays are not in sync after processing documents")
            
            logger.info(f"Added {len(new_texts)} new chunks to storage")
            
            # Save to disk
            self._save_to_disk()
            
        except Exception as e:
            logger.error(f"Error processing documents: {str(e)}")
            raise

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant documents using semantic search."""
        try:
            if not self.texts:
                logger.info("No texts available for search")
                return []
            
            if self.embeddings is None:
                logger.info("No embeddings available for search")
                return []
            
            logger.info(f"Searching for query: '{query}' with k={k}")
            logger.info(f"Available texts: {len(self.texts)}, embeddings shape: {self.embeddings.shape}")
            
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])[0]
            logger.info(f"Query embedding shape: {query_embedding.shape}")
            
            # Calculate cosine similarity
            similarities = np.dot(self.embeddings, query_embedding) / (
                np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(query_embedding)
            )
            logger.info(f"Similarities shape: {similarities.shape}")
            
            # Get top k results
            top_k_indices = np.argsort(similarities)[-k:][::-1]
            logger.info(f"Top k indices: {top_k_indices}")
            
            # Format results
            results = []
            for idx in top_k_indices:
                if idx < len(self.texts) and idx < len(self.metadatas):
                    results.append({
                        'content': self.texts[idx],
                        'metadata': self.metadatas[idx],
                        'score': float(similarities[idx])
                    })
                else:
                    logger.warning(f"Index {idx} out of range for texts ({len(self.texts)}) or metadatas ({len(self.metadatas)})")
            
            logger.info(f"Returning {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in search method: {str(e)}")
            return []

    def _extract_content_from_category(self, category: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract content from a category and its subcategories."""
        documents = []
        
        # Process contents in this category
        if 'contents' in category:
            for content in category['contents']:
                # Create a document from the content
                doc = {
                    'content': content.get('description', '') + '\n' + content.get('title', ''),
                    'source': content.get('url', 'unknown'),
                    'title': content.get('title', 'unknown'),
                    'date': content.get('last_updated', 'unknown'),
                    'category': category.get('name', 'unknown'),
                    'keywords': content.get('keywords', [])
                }
                documents.append(doc)
        
        # Process subcategories recursively
        if 'subcategories' in category:
            for subcategory in category['subcategories']:
                documents.extend(self._extract_content_from_category(subcategory))
        
        return documents

    def load_from_json(self, json_file: str) -> None:
        """Load documents from a JSON file and process them."""
        try:
            logger.info(f"Loading JSON file: {json_file}")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract all documents from categories
            all_documents = []
            if 'categories' in data:
                for category in data['categories']:
                    all_documents.extend(self._extract_content_from_category(category))
            
            logger.info(f"Extracted {len(all_documents)} documents from JSON")
            self.process_documents(all_documents)
            
        except Exception as e:
            logger.error(f"Error loading JSON file: {str(e)}")
            raise

    def clear_vector_store(self) -> None:
        """Clear all documents from the vector store."""
        self.texts = []
        self.metadatas = []
        self.embeddings = None
        self._save_to_disk()

if __name__ == "__main__":
    # Initialize RAG processor
    rag = RAGProcessor()
    logger.info("RAG processor initialized successfully")
    
    # Test documents with real municipal service information
    test_documents = [
        {
            "content": """
            Serviços Disponíveis na Câmara Municipal:
            
            1. Atendimento ao Público
            - Emissão de certidões e documentos
            - Informações sobre licenciamentos
            - Apoio ao munícipe
            
            2. Licenciamentos
            - Licenças de construção
            - Licenças de utilização
            - Alvarás de atividade
            
            3. Serviços Urbanos
            - Gestão de resíduos
            - Manutenção de espaços públicos
            - Limpeza urbana
            
            4. Serviços Sociais
            - Apoio social
            - Habitação social
            - Ação social escolar
            
            Horários de Atendimento:
            Segunda a Sexta: 9h00 - 17h00
            Sábado: 9h00 - 12h30
            """,
            "metadata": {
                "source": "servicos_municipais",
                "title": "Serviços Municipais",
                "date": "2024-03-19"
            }
        },
        {
            "content": """
            Processo de Obtenção de Certidões:
            
            1. Certidão de Registo Predial
            - Documentos necessários:
              * BI/CC do requerente
              * Número de identificação fiscal (NIF)
              * Morada completa do imóvel
            
            2. Certidão de Conteúdo
            - Documentos necessários:
              * BI/CC do requerente
              * Documento que se pretende certificar
            
            3. Certidão de Não Dívida
            - Documentos necessários:
              * BI/CC do requerente
              * NIF
              * Comprovativo de morada
            
            Prazo de Emissão: 24 horas úteis
            Taxa: 5€ por certidão
            """,
            "metadata": {
                "source": "certidoes",
                "title": "Certidões Municipais",
                "date": "2024-03-19"
            }
        },
        {
            "content": """
            Informações sobre Licenciamentos:
            
            1. Licença de Construção
            - Documentos necessários:
              * Projeto arquitetónico
              * Projeto de especialidades
              * Estudo geotécnico
              * NIF do proprietário
            
            2. Licença de Utilização
            - Documentos necessários:
              * Projeto de execução
              * Certificado de conformidade
              * NIF do proprietário
            
            3. Alvará de Atividade
            - Documentos necessários:
              * Planta de localização
              * Projeto de instalações
              * NIF do requerente
            
            Prazo de Análise: 30 dias úteis
            Taxa: Varia conforme o tipo de licença
            """,
            "metadata": {
                "source": "licenciamentos",
                "title": "Licenciamentos Municipais",
                "date": "2024-03-19"
            }
        }
    ]
    
    logger.info(f"Processing {len(test_documents)} documents...")
    
    # Process each document
    for doc in test_documents:
        # Split document into chunks
        chunks = rag.text_splitter.split_text(doc["content"])
        logger.info(f"Split document into {len(chunks)} chunks")
        
        # Generate embeddings for new texts
        logger.info("Generating embeddings for new texts...")
        embeddings = rag.embedding_model.encode(chunks, show_progress_bar=True, batch_size=32)
        
        # Add to storage
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            rag.texts.append(chunk)
            rag.metadatas.append({
                **doc["metadata"],
                "chunk_index": i
            })
        
        # Add all embeddings at once to avoid vstack issues
        if rag.embeddings is None:
            rag.embeddings = embeddings
        else:
            rag.embeddings = np.vstack([rag.embeddings, embeddings])
        
        logger.info(f"Added {len(chunks)} new chunks to storage")
    
    # Save all data
    logger.info(f"Saving {len(rag.texts)} documents to disk...")
    rag._save_to_disk()
    logger.info("All data saved successfully")
    
    # Test search
    test_query = "Como posso obter uma certidão?"
    results = rag.search(test_query, k=2)
    logger.info(f"Search results: {results}") 