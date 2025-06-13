import os
import json
import time
import logging
import requests
import hashlib
from urllib.parse import urlparse, unquote, urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
from typing import List, Dict, Optional, Union, Tuple, Set
from queue import Queue
from data_structure import Content, Category, KnowledgeBase

# Configurações de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scraper")
file_handler = logging.FileHandler("scraper.log")
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Configuração para o download de PDFs
PDF_DOWNLOAD_DIR = 'downloads/pdfs'
os.makedirs(PDF_DOWNLOAD_DIR, exist_ok=True)

pdf_logger = logging.getLogger('pdf_downloader')
pdf_logger.setLevel(logging.INFO)
pdf_handler = logging.FileHandler('pdf_downloads.log')
pdf_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
pdf_logger.addHandler(pdf_handler)

class CmpScraper:
    def __init__(self, headless=True, max_depth=10, use_templates=True):
        self.base_url = "https://www.cm-porto.pt"
        self.knowledge_base = KnowledgeBase(
            last_updated=datetime.now(),
            version="1.0.0"
        )
        self.max_depth = max_depth
        self.headless = headless
        self.visited_urls = set()
        self.url_queue = Queue()
        self.url_depth = {}
        self.content_urls = set()
        self.downloaded_pdfs = []
        self.use_templates = use_templates
        self.page_templates = {}
        self.setup_driver()
        
        # Categorias principais para o chatbot
        self.main_sections = [
            "Cidade", "Município", "Urbanismo", "Ambiente", "Educação", 
            "Cultura", "Economia", "Mobilidade", "Juventude", "Ação Social"
        ]
        
        # Extensões de arquivos a ignorar
        self.ignore_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.ico', '.css', '.js', 
            '.mp3', '.mp4', '.avi', '.mov', '.zip', '.rar', '.7z', 
            '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.exe', '.apk', '.dmg', '.iso'
        ]
        
        # URLs a ignorar (padrões)
        self.ignore_patterns = [
            'login', 'logout', 'admin', 'signup', 'signin',
            'facebook.com', 'twitter.com', 'instagram.com', 'youtube.com',
            'mailto:', 'tel:', 'whatsapp', 'javascript:'
        ]

    def setup_driver(self):
        """Configura o driver do Selenium com as opções apropriadas"""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")
            
            # Configurações para evitar detecção de automação
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            
            # Verifica se o driver existe
            driver_path = os.path.join(os.path.dirname(__file__), 'drivers', 'chromedriver.exe')
            if not os.path.exists(driver_path):
                raise FileNotFoundError(f"ChromeDriver não encontrado em: {driver_path}")

            service = Service(executable_path=driver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(30)
            
            logger.info("Driver do Selenium configurado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao configurar o driver: {str(e)}")
            raise

    def scrape(self):
        """Função principal que escolhe entre método de templates e scraping completo"""
        try:
            logger.info("Iniciando scraping do site da Câmara Municipal do Porto...")
            
            if self.use_templates:
                # Primeiro faz análise do site para criar templates
                self.analyze_site_structure()
                # Depois faz o scraping baseado em templates
                self.scrape_with_templates()
            else:
                # Modo de rastreamento completo
                self.scrape_complete_site()
            
            # Salva a base de conhecimento e informações de PDFs
            self.save_knowledge_base()
            self.save_pdf_info()
            
            logger.info("Scraping concluído com sucesso!")
            
        except Exception as e:
            logger.error(f"Erro durante scraping: {str(e)}", exc_info=True)
        finally:
            self.driver.quit()
            logger.info("Driver do Selenium encerrado")
    
    def scrape_with_templates(self):
        """Scraping inteligente usando templates identificados"""
        logger.info("Iniciando scraping usando templates de páginas...")
        
        # Inicia com as categorias principais
        main_categories = self.create_manual_categories()
        
        # Para cada categoria, extrai subcategorias e conteúdos
        for category in main_categories:
            logger.info(f"Processando categoria: {category.name}")
            
            # Extrai conteúdos da categoria principal usando templates
            category_url = str(category.url)
            if category_url not in self.visited_urls:
                self.visited_urls.add(category_url)
                try:
                    # Usa extração baseada em templates
                    category_contents = self.extract_content_from_page(category_url, category.name)
                    category.contents = category_contents
                except Exception as e:
                    logger.error(f"Erro ao extrair conteúdo da categoria {category.name}: {str(e)}")
            
            # Extrai subcategorias
            subcategories = self.extract_subcategories(category)
            processed_subcategories = []
            
            # Processa subcategorias
            for subcategory in subcategories[:20]:  # Limita a 20 subcategorias
                logger.info(f"Processando subcategoria: {subcategory.name}")
                
                subcategory_url = str(subcategory.url)
                if subcategory_url not in self.visited_urls:
                    self.visited_urls.add(subcategory_url)
                    try:
                        # Usa extração baseada em templates
                        subcategory_contents = self.extract_content_from_page(subcategory_url, subcategory.name)
                        subcategory.contents = subcategory_contents
                        processed_subcategories.append(subcategory)
                    except Exception as e:
                        logger.error(f"Erro ao extrair conteúdo da subcategoria {subcategory.name}: {str(e)}")
            
            # Adiciona as subcategorias processadas
            category.subcategories = processed_subcategories
            
            # Adiciona a categoria à base de conhecimento
            self.knowledge_base.add_category(category)

    def scrape_complete_site(self):
        """Faz scraping completo do site usando rastreamento recursivo"""
        logger.info("Iniciando scraping completo do site...")
        
        # Inicia com a página principal
        self.url_queue.put(self.base_url)
        self.url_depth[self.base_url] = 0
        
        # Mapeia categorias principais para criar estrutura
        main_categories = self.create_manual_categories()
        category_dict = {str(cat.url): cat for cat in main_categories}
        
        # Adiciona as páginas de categorias à fila
        for category in main_categories:
            category_url = str(category.url)
            if category_url not in self.url_depth:
                self.url_queue.put(category_url)
                self.url_depth[category_url] = 1
        
        # Contador para acompanhamento
        pages_processed = 0
        start_time = time.time()
        
        # Processa cada URL na fila enquanto tiver URLs para processar
        while not self.url_queue.empty():
            current_url = self.url_queue.get()
            current_depth = self.url_depth[current_url]
            
            # Se já visitou esta URL, pula
            if current_url in self.visited_urls:
                continue
            
            # Adiciona à lista de URLs visitadas
            self.visited_urls.add(current_url)
            pages_processed += 1
            
            # Log a cada 10 páginas e estatísticas
            if pages_processed % 10 == 0:
                elapsed = time.time() - start_time
                pages_per_second = pages_processed / elapsed if elapsed > 0 else 0
                logger.info(f"Progresso: {pages_processed} páginas processadas, {self.url_queue.qsize()} na fila, velocidade: {pages_per_second:.2f} pág/s")
            
            # Obtém o conteúdo da página
            soup = self.get_page_content(current_url)
            if not soup:
                continue
            
            # Determina a categoria da URL atual
            category_name = self.determine_category(current_url, category_dict)
            
            # Extrai conteúdo da página atual
            try:
                page_contents = self.extract_content_from_page(current_url, category_name)
                
                # Adiciona o conteúdo extraído à estrutura da base de conhecimento
                if page_contents and current_url not in self.content_urls:
                    # Encontra ou cria a categoria apropriada
                    target_cat = None
                    for cat in main_categories:
                        if self.is_subcategory_of(current_url, str(cat.url)):
                            target_cat = cat
                            break
                    
                    if not target_cat:
                        # Se não encontrou uma categoria, usa a primeira
                        target_cat = main_categories[0]
                    
                    # Adiciona conteúdo à categoria
                    for content in page_contents:
                        self.add_content_to_category(target_cat, content)
                        self.content_urls.add(current_url)
                
            except Exception as e:
                logger.error(f"Erro ao extrair conteúdo de {current_url}: {str(e)}")
            
            # Se não alcançou a profundidade máxima, extrai links para adicionar à fila
            if current_depth < self.max_depth:
                self.extract_and_queue_links(soup, current_url, current_depth)
            
            # Salva a base de conhecimento a cada 100 páginas para evitar perda de dados
            if pages_processed % 100 == 0:
                self.save_knowledge_base()
                self.save_pdf_info()
        
        # Depois de processar todas as URLs, adiciona categorias à base de conhecimento
        for category in main_categories:
            self.knowledge_base.add_category(category)

    def analyze_site_structure(self):
        """Analisa a estrutura do site para identificar tipos de páginas e seus padrões HTML"""
        logger.info("Iniciando análise da estrutura do site...")
        
        # 1. Começa com categorias principais
        main_categories = self.create_manual_categories()
        
        # 2. Para cada categoria, obtém a página e analisa sua estrutura
        for category in main_categories:
            category_url = str(category.url)
            soup = self.get_page_content(category_url)
            if not soup:
                continue
            
            # 3. Identifica padrões de estrutura HTML
            structure = self.identify_page_structure(soup)
            page_type = self.classify_page_type(soup, structure)
            
            # 4. Armazena o template para esse tipo de página
            if page_type not in self.page_templates:
                self.page_templates[page_type] = {
                    'selectors': self.get_optimal_selectors(soup),
                    'examples': []
                }
            
            self.page_templates[page_type]['examples'].append({
                'url': category_url,
                'title': category.name
            })
            
            logger.info(f"Página {category.name} classificada como tipo: {page_type}")
            
            # 5. Amostra algumas subcategorias para enriquecer os templates
            subcategories = self.extract_subcategories(category)
            for subcategory in subcategories[:5]:  # Limita a 5 por categoria para análise
                subcategory_url = str(subcategory.url)
                soup = self.get_page_content(subcategory_url)
                if not soup:
                    continue
                
                structure = self.identify_page_structure(soup)
                page_type = self.classify_page_type(soup, structure)
                
                if page_type not in self.page_templates:
                    self.page_templates[page_type] = {
                        'selectors': self.get_optimal_selectors(soup),
                        'examples': []
                    }
                
                self.page_templates[page_type]['examples'].append({
                    'url': subcategory_url,
                    'title': subcategory.name
                })
        
        # 6. Salva os templates para reutilização
        with open('page_templates.json', 'w', encoding='utf-8') as f:
            json.dump(self.page_templates, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Análise concluída. {len(self.page_templates)} tipos de páginas identificados.")

    def identify_page_structure(self, soup):
        """Identifica a estrutura básica da página"""
        structure = {
            'has_main_content': bool(soup.select_one('main, .main, #main, .content, .page-content')),
            'has_sidebar': bool(soup.select_one('.sidebar, aside, .complementary')),
            'has_article': bool(soup.select_one('article')),
            'has_sections': len(soup.select('section')),
            'header_level': self.get_header_structure(soup),
            'form_count': len(soup.select('form')),
            'table_count': len(soup.select('table')),
            'list_count': len(soup.select('ul, ol')),
            'pdf_links': len([a for a in soup.select('a[href]') if a.get('href', '').lower().endswith('.pdf')]),
            'image_count': len(soup.select('img')),
        }
        return structure

    def get_header_structure(self, soup):
        """Analisa estrutura de cabeçalhos (h1-h6) na página"""
        headers = {}
        for i in range(1, 7):
            headers[f'h{i}'] = len(soup.select(f'h{i}'))
        return headers

    def classify_page_type(self, soup, structure):
        """Classifica o tipo de página com base em sua estrutura"""
        page_title = soup.title.string if soup.title else ""
        meta_description = soup.find('meta', {'name': 'description'})
        description = meta_description.get('content', '') if meta_description else ""
        
        # Determina o tipo de página
        if structure['has_article'] and structure['pdf_links'] > 3:
            return "documento_page"
        elif structure['table_count'] > 2:
            return "table_data_page"
        elif structure['form_count'] > 0:
            return "form_page"
        elif "notícias" in page_title.lower() or "notícias" in description.lower():
            return "news_page"
        elif "evento" in page_title.lower() or "agenda" in description.lower():
            return "event_page"
        elif structure['has_sections'] > 5:
            return "multi_section_page"
        elif structure['has_main_content'] and structure['has_sidebar']:
            return "content_with_sidebar_page"
        elif "contacto" in page_title.lower() or "contact" in page_title.lower():
            return "contact_page"
        else:
            return "generic_content_page"

    def get_optimal_selectors(self, soup):
        """Determina os seletores CSS ótimos para extrair conteúdo desta página"""
        selectors = {}
        
        # Tenta encontrar o título principal
        title_candidates = ['h1', '.page-title', '.title', 'header h1', 'header h2', '.heading']
        for selector in title_candidates:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                selectors['title'] = selector
                break
        
        # Tenta encontrar o conteúdo principal
        content_candidates = [
            'main', 'article', '.page-content', '.content', '#main-content', 
            '.text-content', '.article-body', 'section.main'
        ]
        for selector in content_candidates:
            elements = soup.select(selector)
            if elements and any(len(el.get_text(strip=True)) > 200 for el in elements):
                selectors['main_content'] = selector
                break
        
        # Tenta encontrar a data (para notícias/eventos)
        date_candidates = ['.date', '.published', 'time', '.datetime', '.post-date', '.news-date']
        for selector in date_candidates:
            element = soup.select_one(selector)
            if element and element.get_text(strip=True):
                selectors['date'] = selector
                break
        
        # Tenta identificar links para PDFs
        pdf_links = [a for a in soup.select('a[href]') if a.get('href', '').lower().endswith('.pdf')]
        if pdf_links:
            pdf_parent_classes = {}
            for link in pdf_links:
                for parent in link.parents:
                    if parent.name in ['div', 'section', 'article', 'aside']:
                        parent_class = ' '.join(parent.get('class', []))
                        if parent_class:
                            pdf_parent_classes[parent_class] = pdf_parent_classes.get(parent_class, 0) + 1
            
            if pdf_parent_classes:
                most_common_class = max(pdf_parent_classes.items(), key=lambda x: x[1])[0]
                selectors['pdf_container'] = f'.{most_common_class}'
        
        return selectors

    def extract_and_queue_links(self, soup: BeautifulSoup, base_url: str, current_depth: int):
        """Extrai links da página e os adiciona à fila de processamento"""
        if not soup:
            return
        
        # Encontra todos os links na página
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link.get('href', '').strip()
            
            # Pula links vazios ou inválidos
            if not href or href == '#' or href.startswith('javascript:'):
                continue
            
            # Normaliza URL para url absoluta
            full_url = urljoin(base_url, href)
            
            # Verifica se deve ignorar esta URL
            if self.should_ignore_url(full_url):
                continue
            
            # Se não visitamos ainda e é do mesmo domínio, adiciona à fila
            if full_url not in self.visited_urls and self.is_same_domain(full_url):
                # Registra a nova profundidade
                new_depth = current_depth + 1
                
                # Se já está na fila com profundidade maior, atualiza para menor
                if full_url in self.url_depth:
                    if new_depth < self.url_depth[full_url]:
                        self.url_depth[full_url] = new_depth
                else:
                    # Adiciona à fila e registra profundidade
                    self.url_queue.put(full_url)
                    self.url_depth[full_url] = new_depth
                    logger.debug(f"Adicionado à fila: {full_url} (profundidade {new_depth})")

    def should_ignore_url(self, url: str) -> bool:
        """Verifica se uma URL deve ser ignorada no rastreamento"""
        # Verifica extensões a ignorar
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        
        # Ignora URLs com extensões não HTML
        for ext in self.ignore_extensions:
            if path.endswith(ext):
                return True
        
        # Ignora padrões específicos
        url_lower = url.lower()
        for pattern in self.ignore_patterns:
            if pattern in url_lower:
                return True
        
        return False

    def determine_category(self, url: str, category_dict: Dict[str, Category]) -> str:
        """Determina a qual categoria uma URL pertence"""
        url_str = str(url)
        
        # Verifica se é exatamente uma categoria principal
        if url_str in category_dict:
            return category_dict[url_str].name
        
        # Verifica se é uma subcategoria pelo prefixo da URL
        for cat_url, category in category_dict.items():
            if self.is_subcategory_of(url_str, cat_url):
                return category.name
        
        # Examina a URL para determinar a categoria
        url_lower = url_str.lower()
        
        for section in self.main_sections:
            # Verifica ocorrência exata ou com hífens, underscores
            section_lower = section.lower()
            section_variants = [
                section_lower,
                section_lower.replace(" ", "-"), 
                section_lower.replace(" ", "_"),
                section_lower.replace("ç", "c"),
                section_lower.replace("ã", "a"),
                section_lower.replace("á", "a")
            ]
            
            for variant in section_variants:
                if variant in url_lower:
                    return section
        
        # Se não conseguir determinar, retorna "Informações Gerais"
        return "Informações Gerais"

    def is_subcategory_of(self, url: str, category_url: str) -> bool:
        """Verifica se uma URL é subcategoria de uma URL de categoria"""
        # Remove protocolo e domínio para comparação
        parsed_url = urlparse(url)
        parsed_cat = urlparse(category_url)
        
        url_path = parsed_url.path.rstrip('/')
        cat_path = parsed_cat.path.rstrip('/')
        
        # Verifica se o caminho da URL começa com o caminho da categoria
        return url_path.startswith(cat_path + '/') or url_path == cat_path

    def add_content_to_category(self, category: Category, content: Content):
        """Adiciona um conteúdo à categoria apropriada ou subcategoria"""
        # Verifica se o conteúdo deve ser adicionado a uma subcategoria
        if hasattr(content, 'category') and content.category != category.name:
            # Procura a subcategoria apropriada
            for subcategory in category.subcategories:
                if subcategory.name == content.category:
                    subcategory.contents.append(content)
                    return
            
            # Se não encontrou subcategoria, cria uma
            if content.category != category.name:
                subcategory = Category(
                    name=content.category,
                    url=content.url,
                    description=f"Subcategoria de {category.name}: {content.category}",
                    parent_category=category.name,
                    subcategories=[],
                    contents=[content]
                )
                category.subcategories.append(subcategory)
                return
        
        # Adiciona à categoria principal
        category.contents.append(content)

    def create_manual_categories(self) -> List[Category]:
        """Cria categorias manualmente quando o scraping automático falha"""
        logger.info("Criando categorias principais manualmente")
        categories = []
        
        # Mapeamento de categoria para URL
        category_urls = {
            "Cidade": "/cidade",
            "Município": "/municipio",
            "Urbanismo": "/urbanismo",
            "Ambiente": "/ambiente",
            "Educação": "/educacao",
            "Cultura": "/cultura",
            "Economia": "/economia",
            "Mobilidade": "/mobilidade",
            "Juventude": "/juventude",
            "Ação Social": "/acao-social"
        }
        
        for name, path in category_urls.items():
            url = urljoin(self.base_url, path)
            category = Category(
                name=name,
                url=url,
                description=self.get_category_description(name),
                subcategories=[],
                contents=[]
            )
            categories.append(category)
            logger.info(f"Categoria manual criada: {name} ({url})")
            
        return categories

    def get_category_description(self, category_name: str) -> str:
        """Retorna uma descrição padrão baseada no nome da categoria"""
        descriptions = {
            "Cidade": "Informações gerais sobre a cidade do Porto, sua história, símbolos e marcos importantes.",
            "História da cidade": "História e evolução da cidade do Porto ao longo dos séculos, eventos históricos e patrimônio.",
            "Educação": "Informações sobre o sistema educativo, escolas, programas e iniciativas educacionais no Porto.",
            "Juventude": "Programas, eventos e iniciativas voltados para jovens na cidade do Porto.",
            "Cultura": "Eventos culturais, museus, galerias, teatros e patrimônio cultural do Porto.",
            "Mobilidade": "Transportes públicos, ciclovias, acessibilidade e infraestrutura de mobilidade na cidade.",
            "Ambiente": "Projetos ambientais, sustentabilidade, parques e jardins da cidade do Porto.",
            "Município": "Informações sobre a Câmara Municipal do Porto, sua estrutura e funcionamento.",
            "Urbanismo": "Planos de urbanização, desenvolvimento urbano e gestão territorial da cidade.",
            "Ação Social": "Programas de apoio social, inclusão e serviços à comunidade no Porto."
        }
        return descriptions.get(category_name, f"Informações sobre {category_name} na cidade do Porto.")

    def extract_content_from_page(self, url: str, category_name: str) -> List[Content]:
        """Extrai conteúdos de uma página usando templates ou método genérico"""
        soup = self.get_page_content(url)
        if not soup:
            return []

        contents = []
        
        if self.use_templates and self.page_templates:
            # Usa abordagem de templates adaptável à estrutura da página
            structure = self.identify_page_structure(soup)
            page_type = self.classify_page_type(soup, structure)
            
            # Seleciona o template apropriado para o tipo de página
            if page_type in self.page_templates:
                selectors = self.page_templates[page_type].get('selectors', {})
                
                # Extrai conteúdo com base no tipo de página
                if page_type == "news_page":
                    return self.extract_news_content(soup, url, category_name, selectors)
                elif page_type == "event_page":
                    return self.extract_event_content(soup, url, category_name, selectors)
                elif page_type == "documento_page":
                    return self.extract_document_content(soup, url, category_name, selectors)
                elif page_type == "table_data_page":
                    return self.extract_table_content(soup, url, category_name, selectors)
                elif page_type == "form_page":
                    return self.extract_form_content(soup, url, category_name, selectors)
            
            # Se não tiver template específico ou falhar, usa extração genérica
            return self.extract_generic_content(soup, url, category_name)
        else:
            # Método genérico de extração
            return self.extract_generic_content(soup, url, category_name)
    
    def extract_news_content(self, soup, url, category_name, selectors):
        """Extrai conteúdo específico de páginas de notícias"""
        contents = []
        
        # Extrai a notícia principal
        title_elem = soup.select_one(selectors.get('title', 'h1, .title, .heading'))
        main_content_elem = soup.select_one(selectors.get('main_content', 'article, .content, .text-content'))
        date_elem = soup.select_one(selectors.get('date', '.date, time, .published'))
        
        if title_elem and main_content_elem:
            title = title_elem.get_text(strip=True)
            full_text = main_content_elem.get_text(strip=True)
            date = date_elem.get_text(strip=True) if date_elem else ""
            
            # Encontra parágrafos para uma descrição mais limpa
            paragraphs = main_content_elem.select('p')
            description = ' '.join([p.get_text(strip=True) for p in paragraphs[:2]]) if paragraphs else full_text[:300]
            
            # Extrai imagens relacionadas
            images = main_content_elem.select('img')
            image_urls = [urljoin(url, img.get('src', '')) for img in images if img.get('src')]
            
            content = Content(
                title=title,
                content=full_text,
                description=description,
                url=url,
                category=category_name,
                content_type="Notícia",
                type="Notícia",
                keywords=self.extract_keywords(title, full_text),
                last_updated=datetime.now(),
                metadata={
                    "date": date,
                    "images": image_urls,
                    "page_type": "news_page"
                }
            )
            contents.append(content)
        
        # Também procura por links para outras notícias na página
        news_links = soup.select('.news-list a, .related-news a, .other-news a')
        for link in news_links[:5]:  # Limita a 5 notícias relacionadas
            href = link.get('href')
            if href and self.is_same_domain(href):
                news_url = urljoin(url, href)
                title = link.get_text(strip=True)
                content = Content(
                    title=title,
                    content=f"Notícia relacionada: {title}",
                    description=f"Link para notícia relacionada: {title}",
                    url=news_url,
                    category=category_name,
                    content_type="Notícia",
                    type="Notícia",
                    keywords=self.extract_keywords(title, ""),
                    last_updated=datetime.now()
                )
                contents.append(content)
        
        # Extrai PDFs relacionados
        pdf_links = self.extract_pdf_links(soup, url)
        for pdf_url, pdf_title in pdf_links:
            try:
                local_path, file_size = self.download_pdf(pdf_url, category_name)
                if local_path:
                    pdf_content = Content(
                        title=pdf_title or "Documento PDF",
                        content=f"Documento PDF relacionado à notícia: {pdf_url}",
                        description=f"PDF relacionado a {category_name}: {pdf_title}",
                        url=pdf_url,
                        category=category_name,
                        content_type="Documento",
                        type="Documento",
                        keywords=self.extract_keywords(pdf_title, category_name),
                        last_updated=datetime.now(),
                        metadata={"local_path": local_path, "file_size": str(file_size)}
                    )
                    contents.append(pdf_content)
            except Exception as e:
                pdf_logger.error(f"Erro ao processar PDF {pdf_url}: {str(e)}")
        
        return contents
    
    def extract_event_content(self, soup, url, category_name, selectors):
        """Extrai conteúdo específico de páginas de eventos"""
        contents = []
        
        # Extrai informações do evento
        title_elem = soup.select_one(selectors.get('title', 'h1, .title, .event-title'))
        main_content_elem = soup.select_one(selectors.get('main_content', '.event-content, article, .content'))
        date_elem = soup.select_one(selectors.get('date', '.date, .event-date, time'))
        location_elem = soup.select_one('.location, .place, .venue, .event-location')
        
        if title_elem:
            title = title_elem.get_text(strip=True)
            full_text = main_content_elem.get_text(strip=True) if main_content_elem else ""
            date = date_elem.get_text(strip=True) if date_elem else ""
            location = location_elem.get_text(strip=True) if location_elem else ""
            
            # Tenta extrair outros dados específicos de eventos
            time_elem = soup.select_one('.time, .hour, .event-time')
            price_elem = soup.select_one('.price, .cost, .event-price')
            
            time_info = time_elem.get_text(strip=True) if time_elem else ""
            price = price_elem.get_text(strip=True) if price_elem else ""
            
            # Combina informações para descrição
            event_details = []
            if date: event_details.append(f"Data: {date}")
            if time_info: event_details.append(f"Hora: {time_info}")
            if location: event_details.append(f"Local: {location}")
            if price: event_details.append(f"Preço: {price}")
            
            description = " | ".join(event_details)
            if full_text:
                if description:
                    description += " | " + full_text[:200]
                else:
                    description = full_text[:300]
            
            content = Content(
                title=title,
                content=full_text,
                description=description,
                url=url,
                category=category_name,
                content_type="Evento",
                type="Evento",
                keywords=self.extract_keywords(title, full_text),
                last_updated=datetime.now(),
                metadata={
                    "date": date,
                    "location": location,
                    "time": time_info,
                    "price": price,
                    "page_type": "event_page"
                }
            )
            contents.append(content)
        
        # Extrai PDFs relacionados
        pdf_links = self.extract_pdf_links(soup, url)
        for pdf_url, pdf_title in pdf_links:
            try:
                local_path, file_size = self.download_pdf(pdf_url, category_name)
                if local_path:
                    pdf_content = Content(
                        title=pdf_title or "Documento PDF",
                        content=f"Documento PDF relacionado ao evento: {pdf_url}",
                        description=f"PDF relacionado a {category_name}: {pdf_title}",
                        url=pdf_url,
                        category=category_name,
                        content_type="Documento",
                        type="Documento",
                        keywords=self.extract_keywords(pdf_title, category_name),
                        last_updated=datetime.now(),
                        metadata={"local_path": local_path, "file_size": str(file_size)}
                    )
                    contents.append(pdf_content)
            except Exception as e:
                pdf_logger.error(f"Erro ao processar PDF {pdf_url}: {str(e)}")
        
        return contents
    
    def extract_document_content(self, soup, url, category_name, selectors):
        """Extrai conteúdo específico de páginas de documentos"""
        contents = []
        
        # Extrai título e descrição geral
        title_elem = soup.select_one(selectors.get('title', 'h1, .title, .page-title'))
        title = title_elem.get_text(strip=True) if title_elem else category_name
        
        # Para páginas de documentos, o foco principal é extrair PDFs
        pdf_links = self.extract_pdf_links(soup, url)
        
        # Se encontrou PDFs
        if pdf_links:
            # Cria conteúdo para a página principal
            intro_text = ""
            main_content = soup.select_one(selectors.get('main_content', 'main, article, .content'))
            if main_content:
                paragraphs = main_content.select('p')
                intro_text = " ".join([p.get_text(strip=True) for p in paragraphs[:3]])
            
            if intro_text:
                content = Content(
                    title=title,
                    content=intro_text,
                    description=f"Página de documentos: {title}",
                    url=url,
                    category=category_name,
                    content_type="Informação",
                    type="Informação",
                    keywords=self.extract_keywords(title, intro_text),
                    last_updated=datetime.now()
                )
                contents.append(content)
            
            # Adiciona cada PDF
            for pdf_url, pdf_title in pdf_links:
                try:
                    local_path, file_size = self.download_pdf(pdf_url, category_name)
                    if local_path:
                        pdf_content = Content(
                            title=pdf_title or "Documento PDF",
                            content=f"Documento PDF disponível em {pdf_url}",
                            description=f"PDF relacionado a {category_name}: {pdf_title}",
                            url=pdf_url,
                            category=category_name,
                            content_type="Documento",
                            type="Documento",
                            keywords=self.extract_keywords(pdf_title, title),
                            last_updated=datetime.now(),
                            metadata={"local_path": local_path, "file_size": str(file_size)}
                        )
                        contents.append(pdf_content)
                except Exception as e:
                    pdf_logger.error(f"Erro ao processar PDF {pdf_url}: {str(e)}")
        else:
            # Se não encontrou PDFs, extrai o conteúdo como página normal
            return self.extract_generic_content(soup, url, category_name)
        
        return contents
    
    def extract_table_content(self, soup, url, category_name, selectors):
        """Extrai conteúdo de páginas com tabelas de dados"""
        contents = []
        
        # Extrai título da página
        title_elem = soup.select_one(selectors.get('title', 'h1, .title, .page-title'))
        title = title_elem.get_text(strip=True) if title_elem else category_name
        
        # Extrai tabelas
        tables = soup.select('table')
        table_data = []
        
        for i, table in enumerate(tables):
            # Extrai cabeçalhos
            headers = []
            header_row = table.select_one('thead tr')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.select('th')]
            
            # Se não encontrou cabeçalhos em thead, tenta na primeira linha
            if not headers:
                first_row = table.select_one('tr')
                if first_row:
                    headers = [th.get_text(strip=True) for th in first_row.select('th')]
            
            # Extrai linhas
            rows = []
            for tr in table.select('tbody tr'):
                row = [td.get_text(strip=True) for td in tr.select('td')]
                if row:  # Ignora linhas vazias
                    rows.append(row)
            
            # Adiciona dados da tabela
            table_data.append({
                'headers': headers,
                'rows': rows,
                'row_count': len(rows)
            })
        
        # Gera conteúdo para cada tabela significativa
        for i, table in enumerate(table_data):
            if table['row_count'] > 0:
                # Cria uma representação textual da tabela
                table_text = ""
                
                # Adiciona cabeçalhos se existirem
                if table['headers']:
                    table_text += " | ".join(table['headers']) + "\n"
                    table_text += "-" * 50 + "\n"
                
                # Adiciona até 10 primeiras linhas
                for j, row in enumerate(table['rows'][:10]):
                    table_text += " | ".join(row) + "\n"
                
                # Indica se há mais linhas
                if len(table['rows']) > 10:
                    table_text += f"... e mais {len(table['rows']) - 10} linhas"
                
                # Define um título para a tabela
                table_title = f"{title} - Tabela {i+1}" if i > 0 else title
                
                content = Content(
                    title=table_title,
                    content=table_text,
                    description=f"Tabela de dados com {table['row_count']} registros" + (f" e colunas: {', '.join(table['headers'])}" if table['headers'] else ""),
                    url=url,
                    category=category_name,
                    content_type="Tabela",
                    type="Tabela",
                    keywords=self.extract_keywords(title, " ".join(table['headers'])),
                    last_updated=datetime.now(),
                    metadata={
                        "table_index": i,
                        "row_count": table['row_count'],
                        "headers": table['headers']
                    }
                )
                contents.append(content)
        
        # Se não encontrou tabelas com dados, usa extração genérica
        if not contents:
            return self.extract_generic_content(soup, url, category_name)
        
        # Extrai PDFs relacionados
        pdf_links = self.extract_pdf_links(soup, url)
        for pdf_url, pdf_title in pdf_links:
            try:
                local_path, file_size = self.download_pdf(pdf_url, category_name)
                if local_path:
                    pdf_content = Content(
                        title=pdf_title or "Documento PDF",
                        content=f"Documento PDF complementar à tabela: {pdf_url}",
                        description=f"PDF relacionado a {title}: {pdf_title}",
                        url=pdf_url,
                        category=category_name,
                        content_type="Documento",
                        type="Documento",
                        keywords=self.extract_keywords(pdf_title, title),
                        last_updated=datetime.now(),
                        metadata={"local_path": local_path, "file_size": str(file_size)}
                    )
                    contents.append(pdf_content)
            except Exception as e:
                pdf_logger.error(f"Erro ao processar PDF {pdf_url}: {str(e)}")
        
        return contents
    
    def extract_form_content(self, soup, url, category_name, selectors):
        """Extrai conteúdo específico de páginas com formulários"""
        contents = []
        
        # Extrai título e descrição
        title_elem = soup.select_one(selectors.get('title', 'h1, .title, .page-title'))
        title = title_elem.get_text(strip=True) if title_elem else category_name
        
        # Informações sobre formulários
        forms = soup.select('form')
        form_info = []
        
        for i, form in enumerate(forms):
            # Identifica o propósito do formulário
            form_id = form.get('id', '')
            form_class = ' '.join(form.get('class', []))
            form_name = form.get('name', '')
            form_method = form.get('method', 'GET').upper()
            form_action = form.get('action', '#')
            
            # Extrai campos do formulário para entender seu propósito
            fields = []
            for input_field in form.select('input, select, textarea'):
                field_type = input_field.get('type', input_field.name)
                field_name = input_field.get('name', '')
                field_id = input_field.get('id', '')
                field_placeholder = input_field.get('placeholder', '')
                field_label_text = ""
                
                # Tenta encontrar label associado
                if field_id:
                    label = soup.select_one(f'label[for="{field_id}"]')
                    if label:
                        field_label_text = label.get_text(strip=True)
                
                fields.append({
                    'type': field_type,
                    'name': field_name,
                    'label': field_label_text or field_placeholder or field_name
                })
            
            form_info.append({
                'id': form_id,
                'name': form_name or form_id or f"form-{i+1}",
                'method': form_method,
                'action': form_action,
                'fields': fields
            })
        
        # Cria conteúdo para a página de formulário
        if form_info:
            # Extrai texto introdutório
            intro_text = ""
            main_content = soup.select_one(selectors.get('main_content', 'main, article, .content'))
            if main_content:
                # Extrai apenas parágrafos fora dos formulários
                paragraphs = []
                for p in main_content.select('p'):
                    # Verifica se o parágrafo não está dentro de um form
                    if not any(p in form for form in forms):
                        paragraphs.append(p.get_text(strip=True))
                
                intro_text = " ".join(paragraphs)
            
            # Gera descrição do formulário
            form_description = []
            for form in form_info:
                field_names = [f['label'] for f in form['fields'] if f['label']]
                if field_names:
                    form_description.append(f"Formulário {form['name']} com campos: {', '.join(field_names[:5])}")
                    if len(field_names) > 5:
                        form_description[-1] += f" e mais {len(field_names) - 5} campos"
            
            # Combina informações
            content_text = intro_text + "\n\n" + "\n".join(form_description) if form_description else intro_text
            
            content = Content(
                title=title,
                content=content_text,
                description=f"Página com {len(forms)} formulário(s): {title}",
                url=url,
                category=category_name,
                content_type="Formulário",
                type="Formulário",
                keywords=self.extract_keywords(title, content_text),
                last_updated=datetime.now(),
                metadata={
                    "form_count": len(forms),
                    "forms": form_info
                }
            )
            contents.append(content)
        
        # Extrai PDFs relacionados (geralmente formulários para download)
        pdf_links = self.extract_pdf_links(soup, url)
        for pdf_url, pdf_title in pdf_links:
            try:
                local_path, file_size = self.download_pdf(pdf_url, category_name)
                if local_path:
                    pdf_content = Content(
                        title=pdf_title or "Formulário PDF",
                        content=f"Formulário em PDF disponível em {pdf_url}",
                        description=f"Formulário {pdf_title} para download",
                        url=pdf_url,
                        category=category_name,
                        content_type="Documento",
                        type="Documento",
                        keywords=self.extract_keywords(pdf_title, "formulário"),
                        last_updated=datetime.now(),
                        metadata={"local_path": local_path, "file_size": str(file_size)}
                    )
                    contents.append(pdf_content)
            except Exception as e:
                pdf_logger.error(f"Erro ao processar PDF {pdf_url}: {str(e)}")
        
        # Se não conseguiu extrair informações específicas, usa método genérico
        if not contents:
            return self.extract_generic_content(soup, url, category_name)
        
        return contents
    
    def extract_generic_content(self, soup, url, category_name):
        """Extrai conteúdo de páginas genéricas"""
        contents = []
        
        # 1. Extrai conteúdo principal da página - ampliando a captura de elementos
        main_content_selectors = [
            '.container .section', 'main', 'article', '.content', '.page-content', 
            '.block_122', '#main-content', '.main-content', '.article-content',
            '.text-content', '.page-body', '.entry-content', '.post-content'
        ]
        
        main_content = None
        for selector in main_content_selectors:
            main_content = soup.select_one(selector)
            if main_content and len(main_content.get_text(strip=True)) > 100:
                break
        
        if main_content:
            # Amplia os seletores para capturar todos os tipos de títulos
            title_selectors = ['h1', 'h2', '.block_121', '.page-title', '.title', '.main-title', 
                              '.article-title', '.post-title', '.content-title', '.header-title']
            title_elem = None
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem and title_elem.get_text(strip=True):
                    break
            
            # Captura todos os elementos de texto possíveis
            text_selectors = ['p', '.block_122', '.text', '.description', 'li', '.content-block', 
                             'div.info', '.details', '.summary', '.paragraph', '.body-text',
                             'div.texto', '.content-text', '.article-body', 'div[data-content]',
                             'div.conteudo', 'span.text', '.news-content', '.info-text']
            
            # Coletando todos os blocos de texto da página
            all_text_blocks = []
            for selector in text_selectors:
                text_blocks = main_content.select(selector)
                all_text_blocks.extend(text_blocks)
            
            # Monta o texto completo - sem limite de caracteres
            title_text = title_elem.get_text(strip=True) if title_elem else category_name
            full_text = " ".join([block.get_text(strip=True) for block in all_text_blocks if block.get_text(strip=True)])
            
            # Se não encontrou texto nos seletores específicos, tenta extrair todo o texto do bloco principal
            if not full_text or len(full_text) < 100:
                # Extrai todo o texto do bloco principal, excluindo scripts e estilos
                for script_or_style in main_content.select('script, style'):
                    script_or_style.extract()
                
                full_text = main_content.get_text(strip=True).replace('\n', ' ').replace('\r', ' ')
                # Limpa múltiplos espaços
                import re
                full_text = re.sub(r'\s+', ' ', full_text)
            
            if title_text or full_text:
                try:
                    content_type = self.determine_content_type(url)
                    description = f"Informações sobre {title_text}" if title_text else f"Conteúdo relacionado a {category_name}"
                    
                    # Cria o objeto de conteúdo com o texto completo, sem limites
                    content = Content(
                        title=title_text or "Informação Geral",
                        content=full_text if full_text else "Informação não disponível",
                        description=description[:500],  # Só limita a descrição para não ficar muito grande
                        url=url,
                        category=category_name,
                        content_type=content_type,
                        type=content_type,
                        keywords=self.extract_keywords(title_text, full_text),
                        last_updated=datetime.now()
                    )
                    contents.append(content)
                except Exception as e:
                    logger.error(f"Erro ao criar objeto Content para {url}: {str(e)}")
        
        # 2. Se não conseguiu extrair conteúdo principal ou o conteúdo é muito curto, tenta uma abordagem mais agressiva
        if not contents or (contents and len(contents[0].content) < 200):
            # Remove scripts, estilos e elementos ocultos
            for script_or_style in soup.select('script, style, [style*="display:none"], [style*="display: none"]'):
                script_or_style.extract()
            
            # Tenta extrair o corpo inteiro da página
            body = soup.select_one('body')
            if body:
                body_text = body.get_text(strip=True).replace('\n', ' ').replace('\r', ' ')
                import re
                body_text = re.sub(r'\s+', ' ', body_text)
                
                # Se o texto do corpo for significativamente maior que o já encontrado
                if not contents or len(body_text) > len(contents[0].content) * 2:
                    # Busca qualquer título na página
                    title_elem = soup.select_one('h1, h2, title') 
                    title_text = title_elem.get_text(strip=True) if title_elem else category_name
                    
                    content = Content(
                        title=title_text or "Informação da Página",
                        content=body_text[:30000],  # Limita a 30.000 caracteres para evitar conteúdo excessivo
                        description=f"Conteúdo completo da página relacionada a {category_name}",
                        url=url,
                        category=category_name,
                        content_type=self.determine_content_type(url),
                        type=self.determine_content_type(url),
                        keywords=self.extract_keywords(title_text, body_text[:5000]),  # Limita texto para keywords
                        last_updated=datetime.now()
                    )
                    contents.insert(0, content)  # Insere como primeiro conteúdo por ser mais importante
        
        # 3. Ainda extrai blocos de conteúdo adicionais como no método original
        # Amplia mais ainda os seletores para encontrar qualquer bloco relevante
        content_blocks = soup.select('.content, .block, .item, .card, .news-item, article, .group-item, .info, .event, '
                                  '.list-item, .news, .article, .post, .service-item, .feature, .department, '
                                  '.project, .program, .initiative')
        
        for block in content_blocks:
            try:
                title_elem = block.select_one('.name, .title, h3, h4, h5, strong, .event-title, .item-title, .card-title')
                link_elem = block.select_one('a')
                desc_elems = block.select('.description, .excerpt, p, .summary, .details, .event-date, '
                                       '.event-hour, .event-local, .text, .info-text, .card-text')
                
                title = ""
                if title_elem:
                    title = title_elem.get_text(strip=True)
                elif link_elem and link_elem.get_text(strip=True):
                    title = link_elem.get_text(strip=True)
                
                link_url = ""
                if link_elem and link_elem.get('href'):
                    link_url = urljoin(self.base_url, link_elem['href'])
                else:
                    link_url = url
                
                # Combina o texto de todos os elementos de descrição
                description = " ".join([elem.get_text(strip=True) for elem in desc_elems if elem.get_text(strip=True)])
                if not description:
                    # Se não encontrou descrição nos elementos específicos, tenta pegar todo texto do bloco
                    # Primeiro remove elementos que não são relevantes
                    for script_or_style in block.select('script, style'):
                        script_or_style.extract()
                    description = block.get_text(strip=True)
                
                # Só extrair se tivermos pelo menos título ou descrição substancial
                if (title or description) and len((title or "") + (description or "")) > 20:
                    if self.is_same_domain(link_url):
                        content_type = self.determine_content_type(link_url)
                        
                        # Verifica se este conteúdo não é duplicado de algo que já extraímos
                        is_duplicate = False
                        for existing_content in contents:
                            if (title and title in existing_content.title) or \
                               (description and description in existing_content.content):
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            content = Content(
                                title=title or "Informação Relevante",
                                content=description,
                                description=description[:300] if len(description) > 300 else description,
                                url=link_url,
                                category=category_name,
                                content_type=content_type,
                                type=content_type,
                                keywords=self.extract_keywords(title, description),
                                last_updated=datetime.now()
                            )
                            contents.append(content)
            except Exception as e:
                logger.error(f"Erro ao extrair conteúdo de bloco: {str(e)}")

        # 4. Adicionar busca específica por links de PDF
        pdf_links = self.extract_pdf_links(soup, url)
        
        # Para cada PDF encontrado
        for pdf_url, pdf_title in pdf_links:
            try:
                # Baixa o PDF e obtém o caminho local
                local_path, file_size = self.download_pdf(pdf_url, category_name)
                
                if local_path:
                    # Cria um objeto de conteúdo para o PDF
                    # Convertendo file_size para string para resolver o erro
                    pdf_content = Content(
                        title=pdf_title or "Documento PDF",
                        content=f"Documento PDF disponível em {pdf_url}",
                        description=f"PDF relacionado a {category_name}: {pdf_title}",
                        url=pdf_url,
                        category=category_name,
                        content_type="Documento",
                        type="Documento",
                        keywords=self.extract_keywords(pdf_title, category_name),
                        last_updated=datetime.now(),
                        metadata={"local_path": local_path, "file_size": str(file_size)}  # Convertido para string
                    )
                    contents.append(pdf_content)
                    pdf_logger.info(f"PDF adicionado à base de conhecimento: {pdf_title}")
            except Exception as e:
                pdf_logger.error(f"Erro ao processar PDF {pdf_url}: {str(e)}")
        
        return contents[:50]  # Limita a 50 conteúdos por página

    def extract_content_from_subcategory(self, subcategory: Category) -> List[Content]:
        """Extrai conteúdo de uma subcategoria"""
        # Converte URL para string se for objeto Pydantic Url
        subcategory_url = str(subcategory.url) if hasattr(subcategory.url, "__str__") else subcategory.url
        
        if not subcategory_url:
            return []
            
        return self.extract_content_from_page(subcategory_url, subcategory.name)

    def extract_subcategories(self, category: Category) -> List[Category]:
        """Extrai subcategorias de uma categoria principal"""
        # Converte URL para string se for objeto Pydantic Url
        category_url = str(category.url) if hasattr(category.url, "__str__") else category.url
        
        if not category_url:
            return []
            
        soup = self.get_page_content(category_url)
        if not soup:
            return []

        subcategories = []
        
        # Tenta encontrar o painel de submenu para esta categoria
        panels = soup.select('.panel-menu, .sub-panel-menu, .submenu, nav, .nav, .sidebar')
        
        # Se não encontrou painéis específicos, busca em qualquer lista que possa conter subcategorias
        if not panels:
            panels = soup.select('ul, .list, .list-group, .accordion, .dropdown-menu')
        
        for panel in panels:
            # Busca todos os links que podem representar subcategorias
            links = panel.select('a')
            
            for link in links:
                try:
                    name = link.get_text(strip=True)
                    url = link.get('href')
                    
                    # Filtros para identificar links relevantes como subcategorias
                    if (name and url and len(name) > 2 and 
                        not url.startswith('#') and 
                        not url.startswith('javascript') and
                        not url.startswith('tel:') and
                        not url.startswith('mailto:')):
                        
                        url = urljoin(self.base_url, url)
                        
                        # Verifica se não é um link externo
                        url_str = str(url)
                        if self.is_same_domain(url_str) and url_str != str(category.url):
                            # Evitar duplicados
                            if not any(str(sub.url) == url_str for sub in subcategories):
                                subcategory = Category(
                                    name=name,
                                    url=url,
                                    description=f"Subcategoria de {category.name}: {name}",
                                    parent_category=category.name,
                                    subcategories=[],
                                    contents=[]
                                )
                                logger.info(f"Subcategoria encontrada: {name} ({url})")
                                subcategories.append(subcategory)
                except Exception as e:
                    logger.error(f"Erro ao extrair subcategoria: {str(e)}")
        
        return subcategories

    def save_knowledge_base(self):
        """Salva a base de conhecimento em um arquivo JSON"""
        try:
            logger.info("Salvando base de conhecimento em knowledge_base.json...")
            
            # Converte objeto KnowledgeBase para dicionário
            try:
                if hasattr(self.knowledge_base, "model_dump"):
                    # Para Pydantic v2+
                    kb_dict = self.knowledge_base.model_dump()
                else:
                    # Para Pydantic v1
                    kb_dict = self.knowledge_base.dict()
            except AttributeError:
                # Fallback para outras implementações
                kb_dict = {
                    "categories": [cat.dict() if hasattr(cat, "dict") else vars(cat) 
                                  for cat in self.knowledge_base.categories],
                    "last_updated": self.knowledge_base.last_updated.isoformat() 
                                    if hasattr(self.knowledge_base.last_updated, "isoformat") 
                                    else str(self.knowledge_base.last_updated),
                    "version": self.knowledge_base.version
                }
            
            # Cria o arquivo com formatação bonita
            with open('knowledge_base.json', 'w', encoding='utf-8') as f:
                json.dump(kb_dict, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"Base de conhecimento salva com sucesso: {len(self.knowledge_base.categories)} categorias")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao salvar base de conhecimento: {str(e)}", exc_info=True)
            return False

    def save_pdf_info(self):
        """Salva informações sobre os PDFs baixados"""
        try:
            with open('pdf_downloads.json', 'w', encoding='utf-8') as f:
                json.dump(self.downloaded_pdfs, f, ensure_ascii=False, indent=2, default=str)
            pdf_logger.info(f"Informações de {len(self.downloaded_pdfs)} PDFs salvas em pdf_downloads.json")
        except Exception as e:
            pdf_logger.error(f"Erro ao salvar informações dos PDFs: {str(e)}")

    def get_page_content(self, url: str) -> BeautifulSoup:
        """Obtém o conteúdo de uma página usando Selenium com retentativas"""
        try:
            logger.info(f"Obtendo conteúdo da página: {url}")
            
            # Tenta carregar a página até 3 vezes
            for attempt in range(3):
                try:
                    self.driver.get(url)
                    # Espera o conteúdo carregar
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Espera adicional para AJAX e JavaScript
                    time.sleep(2)
                    
                    # Obtém o HTML
                    page_source = self.driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    return soup
                except (TimeoutException, NoSuchElementException) as e:
                    logger.warning(f"Tentativa {attempt+1} falhou para {url}: {str(e)}")
                    if attempt == 2:  # Última tentativa
                        raise
            
            return None
        except Exception as e:
            logger.error(f"Erro ao obter conteúdo de {url}: {str(e)}")
            return None

    def extract_pdf_links(self, soup: BeautifulSoup, base_url: str) -> List[Tuple[str, str]]:
        """Extrai links para arquivos PDF da página"""
        pdf_links = []
        
        # Busca por links que terminam com .pdf
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href.lower().endswith('.pdf'):
                pdf_url = urljoin(base_url, href)
                # Tenta obter um título para o PDF a partir do texto do link
                pdf_title = link.get_text(strip=True)
                if not pdf_title:
                    # Se não tiver texto, tenta extrair o nome do arquivo da URL
                    parsed_url = urlparse(pdf_url)
                    filename = os.path.basename(unquote(parsed_url.path))
                    pdf_title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
                
                pdf_links.append((pdf_url, pdf_title))
                pdf_logger.debug(f"Link PDF encontrado: {pdf_url} - {pdf_title}")
        
        # Busca por links que podem ser PDFs pela descrição ou classe
        pdf_indicators = ['pdf', 'documento', 'download', 'baixar', 'regulamento', 'formulário', 'manual']
        for link in soup.find_all('a'):
            if link.get('href') and not link['href'].lower().endswith('.pdf'):
                link_text = link.get_text(strip=True).lower()
                link_class = ' '.join(link.get('class', [])).lower()
                
                if any(ind in link_text for ind in pdf_indicators) or any(ind in link_class for ind in pdf_indicators):
                    pdf_url = urljoin(base_url, link['href'])
                    pdf_title = link.get_text(strip=True)
                    
                    # Verifica se parece ser um link para PDF com base em outros atributos
                    if ('pdf' in link.get('type', '').lower() or 
                        'pdf' in link.get('data-type', '').lower() or
                        'pdf' in link.get('title', '').lower() or
                        'download' in link.get('download', '').lower()):
                        pdf_links.append((pdf_url, pdf_title))
                        pdf_logger.debug(f"Link PDF inferido: {pdf_url} - {pdf_title}")
        
        # Remove duplicados
        unique_links = []
        seen_urls = set()
        for url, title in pdf_links:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_links.append((url, title))
        
        return unique_links

    def download_pdf(self, pdf_url: str, category: str) -> Tuple[str, int]:
        """
        Faz o download de um arquivo PDF
        Retorna (caminho_local, tamanho_bytes)
        """
        try:
            # Assegura que já não foi baixado anteriormente
            if hasattr(self, 'downloaded_pdfs'):
                for pdf in self.downloaded_pdfs:
                    if pdf['url'] == pdf_url:
                        pdf_logger.info(f"PDF já baixado anteriormente: {pdf_url}")
                        return pdf['local_path'], int(pdf['size'])
            
            # Gera um nome de arquivo único baseado na URL
            url_hash = hashlib.md5(pdf_url.encode()).hexdigest()
            parsed_url = urlparse(pdf_url)
            filename = os.path.basename(unquote(parsed_url.path))
            
            # Se o nome não termina em .pdf, adiciona a extensão
            if not filename.lower().endswith('.pdf'):
                filename = f"{url_hash}.pdf"
            else:
                # Senão, adiciona hash antes do nome para evitar colisões
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{url_hash[:8]}{ext}"
            
            # Cria o caminho completo
            category_dir = os.path.join(PDF_DOWNLOAD_DIR, category.replace(' ', '_').lower())
            os.makedirs(category_dir, exist_ok=True)
            local_path = os.path.join(category_dir, filename)
            
            # Verifica se o arquivo já existe
            if os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                pdf_logger.info(f"PDF já existe localmente: {local_path}")
                
                # Registra o PDF
                if hasattr(self, 'downloaded_pdfs'):
                    self.downloaded_pdfs.append({
                        'url': pdf_url,
                        'local_path': local_path,
                        'size': file_size,
                        'title': os.path.splitext(os.path.basename(filename))[0],
                        'category': category,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                
                return local_path, file_size
            
            # Faz o download usando requests
            pdf_logger.info(f"Baixando PDF: {pdf_url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
            response = requests.get(pdf_url, stream=True, headers=headers, timeout=30)
            
            # Verifica se a resposta parece ser um PDF
            content_type = response.headers.get('Content-Type', '').lower()
            if response.status_code != 200 or ('application/pdf' not in content_type and not pdf_url.lower().endswith('.pdf')):
                pdf_logger.warning(f"URL não retornou um PDF válido: {pdf_url} - Status: {response.status_code} - Content-Type: {content_type}")
                return "", 0
            
            # Salva o arquivo PDF
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verifica o tamanho do arquivo
            file_size = os.path.getsize(local_path)
            
            # Verifica se o arquivo parece ser realmente um PDF (pelos bytes de assinatura)
            with open(local_path, 'rb') as f:
                header = f.read(4)
                if header != b'%PDF':
                    pdf_logger.warning(f"Arquivo não parece ser um PDF válido: {local_path}")
                    # Se não for um PDF, remove o arquivo
                    os.remove(local_path)
                    return "", 0
            
            pdf_logger.info(f"PDF baixado com sucesso: {local_path} ({file_size} bytes)")
            
            # Registra o PDF baixado
            if hasattr(self, 'downloaded_pdfs'):
                self.downloaded_pdfs.append({
                    'url': pdf_url,
                    'local_path': local_path,
                    'size': file_size,
                    'title': os.path.splitext(os.path.basename(filename))[0],
                    'category': category,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            
            return local_path, file_size
            
        except Exception as e:
            pdf_logger.error(f"Erro ao baixar PDF {pdf_url}: {str(e)}")
            return "", 0

    def is_same_domain(self, url: str) -> bool:
        """Verifica se a URL pertence ao mesmo domínio base"""
        try:
            if not url:
                return False
            
            base_domain = urlparse(self.base_url).netloc
            url_domain = urlparse(url).netloc
            
            # Verifica se o domínio principal (sem subdomínios) é o mesmo
            base_main_domain = '.'.join(base_domain.split('.')[-2:]) if len(base_domain.split('.')) >= 2 else base_domain
            url_main_domain = '.'.join(url_domain.split('.')[-2:]) if len(url_domain.split('.')) >= 2 else url_domain
            
            return url_main_domain == base_main_domain
        except Exception:
            return False

    def determine_content_type(self, url: str) -> str:
        """Determina o tipo de conteúdo baseado na URL"""
        # Assegurar que a URL é uma string
        url_lower = str(url).lower() if hasattr(url, "__str__") else str(url).lower()
        
        if "noticia" in url_lower or "news" in url_lower:
            return "Notícia"
        elif "evento" in url_lower or "agenda" in url_lower:
            return "Evento"
        elif "documento" in url_lower or ".pdf" in url_lower:
            return "Documento"
        elif "projeto" in url_lower:
            return "Projeto"
        elif any(word in url_lower for word in ["educacao", "escola", "ensino"]):
            return "Educacional"
        elif any(word in url_lower for word in ["cultura", "museu", "teatro"]):
            return "Cultural"
        elif any(word in url_lower for word in ["mobilidade", "transporte"]):
            return "Mobilidade"
        elif any(word in url_lower for word in ["ambiente", "parques", "jardins"]):
            return "Ambiental"
        else:
            return "Informação"

    def extract_keywords(self, title: str, description: str) -> List[str]:
        """Extrai palavras-chave relevantes do título e descrição"""
        common_words = {"do", "da", "de", "no", "na", "os", "as", "um", "uma", "com", "para", "pelo", "pela", "que", "por"}
        
        # Normaliza e combina texto
        text = f"{title or ''} {description or ''}"
        text = text.lower()
        
        # Remove caracteres especiais e divide em palavras
        import re
        words = re.findall(r'\b[a-zÀ-ÿ]{4,}\b', text)
        words = [w for w in words if w not in common_words]
        
        # Se não houver palavras adequadas, usar algumas padrão
        if not words:
            return ["porto", "município", "informação", "cidade"]
        
        # Conta frequência
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1
        
        # Ordena por frequência
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        
        # Retorna primeiras 8 palavras-chave
        return [word for word, _ in sorted_words[:8]]

if __name__ == "__main__":
    # Configuração via argumentos de linha de comando
    import argparse
    
    parser = argparse.ArgumentParser(description='Scraper inteligente para o site da Câmara Municipal do Porto')
    parser.add_argument('--headless', action='store_true', default=True, help='Executar em modo headless (sem interface gráfica)')
    parser.add_argument('--depth', type=int, default=5, help='Profundidade máxima de rastreamento (default: 5)')
    parser.add_argument('--use-templates', action='store_true', default=True, help='Usar templates para extração de conteúdo')
    parser.add_argument('--complete', action='store_true', help='Fazer rastreamento completo do site')
    parser.add_argument('--analyze-only', action='store_true', help='Apenas analisar a estrutura do site sem coletar conteúdo')
    
    args = parser.parse_args()
    
    # Inicializa o scraper
    scraper = CmpScraper(
        headless=args.headless, 
        max_depth=args.depth,
        use_templates=args.use_templates
    )
    
    try:
        if args.analyze_only:
            # Apenas analisa a estrutura do site
            scraper.analyze_site_structure()
        elif args.complete:
            # Executa o rastreamento completo do site
            scraper.scrape_complete_site()
        else:
            # Executa o scraping padrão
            scraper.scrape()
        
        print("Scraping concluído com sucesso!")
        
    except Exception as e:
        print(f"Erro durante a execução: {str(e)}")
    finally:
        if hasattr(scraper, 'driver'):
            scraper.driver.quit()

