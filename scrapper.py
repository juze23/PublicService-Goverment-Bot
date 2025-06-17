import os
import json
import time
import logging
import requests
import hashlib
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime
from typing import List, Dict, Optional, Union, Tuple
from urllib.parse import urljoin, urlparse
from data_structure import Content, Category, KnowledgeBase

# Configuração do logger principal
logger = logging.getLogger("scraper")
logger.setLevel(logging.INFO)
log_handler = logging.FileHandler("scraper.log")
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(log_handler)

# Configuração para o download de PDFs
PDF_DOWNLOAD_DIR = 'downloads/pdfs'
os.makedirs(PDF_DOWNLOAD_DIR, exist_ok=True)

# Adicionar logger específico para download de PDFs
pdf_logger = logging.getLogger('pdf_downloader')
pdf_logger.setLevel(logging.INFO)
pdf_handler = logging.FileHandler('pdf_downloads.log')
pdf_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
pdf_logger.addHandler(pdf_handler)

class CmpScraper:
    def __init__(self, headless=True, max_depth=3):
        self.base_url = "https://www.cm-porto.pt"
        self.knowledge_base = KnowledgeBase(
            last_updated=datetime.now(),
            version="1.0.0"
        )
        self.max_depth = max_depth
        self.headless = headless
        self.visited_urls = set()
        self.setup_driver()
        
        # Categorias principais para o chatbot
        self.main_sections = [
            "Cidade", "Município", "Urbanismo", "Ambiente", "Educação", 
            "Cultura", "Economia", "Mobilidade", "Juventude", "Ação Social"
        ]

    def setup_driver(self):
        """Configura o driver do Selenium com as opções apropriadas"""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument("--headless=new")  # Usar o novo modo headless
            
            # Configurar user agent moderno
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
        """Função principal para iniciar o scraping do site"""
        try:
            logger.info("Iniciando scraping do site da Câmara Municipal do Porto...")
            
            # Forçar o carregamento completo da página inicial
            soup = self.get_page_content(self.base_url)
            
            if not soup:
                logger.error("Não foi possível acessar a página inicial.")
                return
                
            # Extrair categorias principais do menu
            main_categories = self.extract_main_categories(soup)
            
            if not main_categories:
                logger.warning("Nenhuma categoria principal encontrada. Tentando método alternativo...")
                main_categories = self.create_manual_categories()
            
            # Para cada categoria principal, extrair seus conteúdos e subcategorias
            for category in main_categories:
                logger.info(f"Processando categoria: {category.name}")
                
                # Converte URL para string se for objeto Pydantic Url
                category_url = str(category.url) if hasattr(category.url, "__str__") else category.url
                
                # Só processa se não tiver visitado ainda
                if category_url and category_url not in self.visited_urls:
                    # Extrai subcategorias e seus conteúdos
                    subcategories = self.extract_subcategories(category)
                    
                    # Limita o número de subcategorias para processamento
                    processed_subcategories = subcategories[:10]
                    
                    # Para cada subcategoria, extrair conteúdos específicos
                    for subcategory in processed_subcategories:
                        try:
                            contents = self.extract_content_from_subcategory(subcategory)
                            subcategory.contents = contents
                        except Exception as e:
                            logger.error(f"Erro ao extrair conteúdo da subcategoria {subcategory.name}: {str(e)}")
                            subcategory.contents = []
                    
                    category.subcategories = processed_subcategories
                    
                    # Também extrai conteúdo direto da categoria atual
                    try:
                        category_contents = self.extract_content_from_page(category_url, category.name)
                        category.contents = category_contents
                    except Exception as e:
                        logger.error(f"Erro ao extrair conteúdo da categoria {category.name}: {str(e)}")
                        category.contents = []
                    
                    # Adiciona à base de conhecimento
                    self.knowledge_base.add_category(category)

            # Salva a base de conhecimento em um arquivo JSON
            self.save_knowledge_base()
            logger.info("Scraping concluído com sucesso!")

        except Exception as e:
            logger.error(f"Erro durante scraping: {str(e)}", exc_info=True)
        finally:
            self.driver.quit()
            logger.info("Driver do Selenium encerrado")
            
            # Salva informações sobre os PDFs baixados
            if hasattr(self, 'downloaded_pdfs') and self.downloaded_pdfs:
                self.save_pdf_info()
    
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

    def save_knowledge_base(self):
        """Salva a base de conhecimento em um arquivo JSON"""
        try:
            # Usa o método dict() em vez de model_dump() para compatibilidade
            # com versões mais antigas da Pydantic
            try:
                kb_dict = self.knowledge_base.model_dump()
            except AttributeError:
                kb_dict = self.knowledge_base.dict()
            
            # Função para converter objetos complexos para strings
            def json_serializable(obj):
                if isinstance(obj, dict):
                    return {k: json_serializable(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [json_serializable(item) for item in obj]
                elif isinstance(obj, datetime):
                    return obj.strftime('%Y-%m-%d %H:%M:%S')
                # Converte URLs da Pydantic para strings
                elif hasattr(obj, "__str__"):
                    return str(obj)
                else:
                    return obj
            
            # Aplica a conversão recursivamente
            serialized_kb = json_serializable(kb_dict)
            
            # Salva o arquivo com o encoder personalizado
            with open('knowledge_base.json', 'w', encoding='utf-8') as f:
                json.dump(serialized_kb, f, ensure_ascii=False, indent=2)

            logger.info(f"Base de conhecimento guardada com sucesso: {len(serialized_kb.get('categories', []))} categorias")
        except Exception as e:
            logger.error(f"Erro ao guardar a base de conhecimento: {str(e)}", exc_info=True)

    def get_page_content(self, url: str) -> Optional[BeautifulSoup]:
        """Obtém o conteúdo HTML da página e retorna um objeto BeautifulSoup"""
        try:
            # Assegurar que a URL é uma string
            url_str = str(url) if hasattr(url, "__str__") else url
            
            # Verifica se já visitamos esta URL
            if url_str in self.visited_urls:
                logger.debug(f"URL já visitada, pulando: {url_str}")
                return None
            
            # Adiciona à lista de URLs visitadas
            self.visited_urls.add(url_str)
            
            # Assegura que temos uma URL absoluta
            if isinstance(url_str, str) and not url_str.startswith(('http://', 'https://')):
                url_str = urljoin(self.base_url, url_str)
            
            logger.info(f"Acessando URL: {url_str}")
            self.driver.get(url_str)
            
            # Adicionar um pequeno delay para garantir carregamento
            time.sleep(2)
            
            # Verificar cookies ou banners e fechar se necessário (ajustar seletores conforme o site)
            try:
                cookie_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Aceitar') or contains(text(), 'Accept')]")
                if cookie_buttons:
                    cookie_buttons[0].click()
                    time.sleep(1)
            except:
                pass
                
            # Espera pelo carregamento de elementos importantes
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Rolar para carregar conteúdo lazy-loaded
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
                time.sleep(0.5)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                time.sleep(0.5)
            except TimeoutException:
                logger.warning(f"Timeout ao aguardar carregamento da página: {url_str}")
            
            # Obtém o HTML e cria o objeto BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Verificar se é uma página real ou de aviso/erro
            if soup.find(id='warning-ie') or soup.find(class_='warning-ie'):
                logger.warning(f"Página está mostrando aviso de browser: {url_str}")
                
                # Tentar contornar banner de browser
                try:
                    warning_buttons = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Continuar') or contains(text(), 'Continue')]")
                    if warning_buttons:
                        warning_buttons[0].click()
                        time.sleep(2)
                        # Obter o novo conteúdo após clicar no botão
                        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                except Exception as e:
                    logger.error(f"Erro ao tentar contornar aviso de browser: {str(e)}")
                    
            return soup
            
        except Exception as e:
            logger.error(f"Erro ao carregar {url}: {str(e)}")
            return None

    def extract_main_categories(self, soup: BeautifulSoup) -> List[Category]:
        """Extrai as categorias principais do menu do site"""
        logger.info("Extraindo categorias principais...")
        categories = []
        
        # Tentativa 1: Método original - usando a estrutura de menu específica
        menu_container = soup.find('div', class_='block mega-menu block_3')
        if menu_container:
            menu_items = menu_container.select('.list-menu.level-1 > li')
            
            for item in menu_items:
                try:
                    link = item.select_one('a')
                    if link and link.get('href'):
                        name = link.get_text(strip=True)
                        url = urljoin(self.base_url, link['href'])
                        
                        # Só processa categorias que estão na lista principal
                        if any(section.lower() in name.lower() for section in self.main_sections):
                            category = Category(
                                name=name,
                                url=url,
                                description=self.get_category_description(name),
                                subcategories=[],
                                contents=[]
                            )
                            logger.info(f"Categoria encontrada: {name} ({url})")
                            categories.append(category)
                except Exception as e:
                    logger.error(f"Erro ao extrair categoria: {str(e)}")
        
        # Tentativa 2: Buscar links de navegação do site
        if not categories:
            logger.info("Tentando método alternativo para encontrar categorias...")
            nav_items = soup.select('nav a, .nav a, .navigation a, .main-nav a, header a')
            
            for link in nav_items:
                try:
                    name = link.get_text(strip=True)
                    url = link.get('href')
                    
                    if name and url and any(section.lower() in name.lower() for section in self.main_sections):
                        url = urljoin(self.base_url, url)
                        
                        # Evitar duplicados
                        if not any(c.name == name for c in categories):
                            category = Category(
                                name=name,
                                url=url,
                                description=self.get_category_description(name),
                                subcategories=[],
                                contents=[]
                            )
                            logger.info(f"Categoria alternativa encontrada: {name} ({url})")
                            categories.append(category)
                except Exception as e:
                    logger.error(f"Erro ao extrair categoria alternativa: {str(e)}")
        
        logger.info(f"Total de categorias encontradas: {len(categories)}")
        return categories

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

        return subcategories[:20]  # Limitar a 10 subcategorias para evitar excesso

    def extract_content_from_subcategory(self, subcategory: Category) -> List[Content]:
        """Extrai conteúdo de uma subcategoria"""
        # Converte URL para string se for objeto Pydantic Url
        subcategory_url = str(subcategory.url) if hasattr(subcategory.url, "__str__") else subcategory.url
        
        if not subcategory_url:
            return []
            
        return self.extract_content_from_page(subcategory_url, subcategory.name)

    def extract_content_from_page(self, url: str, category_name: str) -> List[Content]:
        """Extrai conteúdos de uma página com mais texto e profundidade"""
        soup = self.get_page_content(url)
        if not soup:
            return []

        contents = []
        
        # 1. Extrai conteúdo principal da página - aumentando a captura de elementos
        main_content = soup.select_one('.container .section, main, article, .content, .page-content, .block_122')
        if main_content:
            # Amplia os seletores para capturar mais elementos de texto
            title_elem = soup.select_one('h1, h2, .block_121, .page-title, .title')
            # Amplia os tipos de elementos de texto para capturar
            text_blocks = main_content.select('p, .block_122, .text, .description, li, .content-block, div.info, .details, .summary')
            
            # Monta o texto completo - removendo limite de caracteres
            title_text = title_elem.get_text(strip=True) if title_elem else category_name
            full_text = " ".join([block.get_text(strip=True) for block in text_blocks if block.get_text(strip=True)])
            
            if title_text or full_text:
                try:
                    content_type = self.determine_content_type(url)
                    description = f"Informações sobre {title_text}" if title_text else f"Conteúdo relacionado a {category_name}"
                    
                    # Removido o limite de caracteres para o conteúdo
                    content = Content(
                        title=title_text or "Informação Geral",
                        content=full_text if full_text else "Informação não disponível",
                        description=description,
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
        
        # 2. Extrai informações de blocos específicos - ampliando seleção de blocos
        content_blocks = soup.select('.content, .block, .item, .card, .news-item, article, .group-item, .info, .event')
        
        for block in content_blocks:
            try:
                # Amplia os seletores para encontrar mais elementos
                title_elem = block.select_one('.name, .title, h3, h4, h5, strong, .event-title')
                link_elem = block.select_one('a')
                # Captura mais elementos que possam conter descrições
                desc_elems = block.select('.description, .excerpt, p, .summary, .details, .event-date, .event-hour, .event-local')
                
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
                    description = f"Informações relacionadas a {title or category_name}"
                
                # Só extrair se tivermos pelo menos título ou descrição
                if (title or description) and len(title + description) > 10:
                    # Verificar se é do mesmo domínio
                    if self.is_same_domain(link_url):
                        content_type = self.determine_content_type(link_url)
                        
                        # Removido o limite de caracteres para conteúdo e descrição
                        content = Content(
                            title=title or "Informação Relevante",
                            content=description if description else "Informação não disponível",
                            description=description if description else f"Conteúdo relacionado a {category_name}",
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

        # Adicionar busca específica por links de PDF
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
        
        return contents
    
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
                        return pdf['local_path'], pdf['size']
            
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
                
                # Tenta baixar usando Selenium se requests falhar
                return self.download_pdf_with_selenium(pdf_url, local_path, category)
            
            # Salva o arquivo PDF
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Verifica o tamanho do arquivo
            file_size = os.path.getsize(local_path)
            
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
    
    def download_pdf_with_selenium(self, pdf_url: str, local_path: str, category: str) -> Tuple[str, int]:
        """Tenta baixar um PDF usando o Selenium quando o requests falha"""
        try:
            pdf_logger.info(f"Tentando baixar PDF com Selenium: {pdf_url}")
            
            # Configura o driver para baixar automaticamente PDFs
            options = Options()
            options.add_argument("--headless=new")
            prefs = {
                "download.default_directory": os.path.abspath(os.path.dirname(local_path)),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "plugins.always_open_pdf_externally": True
            }
            options.add_experimental_option("prefs", prefs)
            
            driver_path = os.path.join(os.path.dirname(__file__), 'drivers', 'chromedriver.exe')
            service = Service(executable_path=driver_path)
            pdf_driver = webdriver.Chrome(service=service, options=options)
            
            try:
                pdf_driver.get(pdf_url)
                time.sleep(5)  # Espera para dar tempo de iniciar o download
                
                # Verifica se o arquivo foi baixado corretamente
                downloaded_file = max([f for f in os.listdir(os.path.dirname(local_path))], 
                                     key=lambda f: os.path.getctime(os.path.join(os.path.dirname(local_path), f)))
                
                if downloaded_file:
                    downloaded_path = os.path.join(os.path.dirname(local_path), downloaded_file)
                    # Move para o local correto se necessário
                    if downloaded_path != local_path and os.path.exists(downloaded_path):
                        os.rename(downloaded_path, local_path)
                    
                    file_size = os.path.getsize(local_path)
                    pdf_logger.info(f"PDF baixado com sucesso via Selenium: {local_path} ({file_size} bytes)")
                    
                    # Registra o PDF baixado
                    if hasattr(self, 'downloaded_pdfs'):
                        self.downloaded_pdfs.append({
                            'url': pdf_url,
                            'local_path': local_path,
                            'size': file_size,
                            'title': os.path.splitext(os.path.basename(local_path))[0],
                            'category': category,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                    
                    return local_path, file_size
                
                return "", 0
                
            finally:
                pdf_driver.quit()
                
        except Exception as e:
            pdf_logger.error(f"Erro ao baixar PDF com Selenium {pdf_url}: {str(e)}")
            return "", 0

    def is_same_domain(self, url: str) -> bool:
        """Verifica se uma URL pertence ao mesmo domínio que o site principal"""
        try:
            # Assegurar que a URL é uma string
            url_str = str(url) if hasattr(url, "__str__") else url
            
            parsed_base = urlparse(self.base_url)
            parsed_url = urlparse(url_str)
            return parsed_url.netloc == parsed_base.netloc or parsed_url.netloc == ""
        except Exception as e:
            logger.error(f"Erro ao verificar domínio: {str(e)}")
            return False

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

    def deep_crawl(self, start_url, max_depth=5):
        """Rastreia todo o site recursivamente, até a profundidade especificada"""
        queue = [(start_url, 0)]  # (url, profundidade)
        visited = set()
        
        while queue:
            current_url, depth = queue.pop(0)
            
            # Pula se já visitado ou atingir profundidade máxima
            if current_url in visited or depth > max_depth:
                continue
                
            visited.add(current_url)
            logger.info(f"[Rastreamento Profundo] Processando: {current_url} (nível {depth})")
            
            # Extrai conteúdo da página
            soup = self.get_page_content(current_url)
            if not soup:
                continue
                
            # Adiciona o conteúdo à base de conhecimento
            self.extract_content_from_page(current_url, "Rastreamento Geral")
            
            # Encontra todos os links na página
            if depth < max_depth:
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag.get('href')
                    if href:
                        # Normaliza URL
                        next_url = urljoin(self.base_url, href)
                        # Verifica se é do mesmo domínio e não é um recurso não HTML
                        if (self.is_same_domain(next_url) and
                            not any(next_url.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.zip'])):
                            queue.append((next_url, depth + 1))


if __name__ == "__main__":
    scraper = CmpScraper(headless=True, max_depth=2)
    scraper.scrape()