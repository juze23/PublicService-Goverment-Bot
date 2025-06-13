from typing import List, Optional, Dict
from pydantic import BaseModel, HttpUrl
from datetime import datetime

class Content(BaseModel):
    """Represents a piece of content from gov.pt"""
    title: str
    description: str
    url: HttpUrl
    category: str
    subcategory: Optional[str] = None
    keywords: List[str] = []
    last_updated: Optional[datetime] = None
    content_type: str  # 'service', 'guide', 'news', 'topic', etc.
    metadata: Dict[str, str] = {}

class Category(BaseModel):
    """Represents a category of content"""
    name: str
    description: Optional[str] = None
    url: HttpUrl
    subcategories: List['Category'] = []
    contents: List[Content] = []
    parent: Optional['Category'] = None

class KnowledgeBase(BaseModel):
    """Main knowledge base structure"""
    categories: List[Category] = []
    last_updated: datetime
    version: str = "1.0.0"
    
    def add_category(self, category: Category) -> None:
        """Add a new category to the knowledge base"""
        self.categories.append(category)
    
    def find_content(self, query: str) -> List[Content]:
        """Search for content matching the query"""
        # This will be implemented with proper search logic
        pass
    
    def get_category_by_name(self, name: str) -> Optional[Category]:
        """Find a category by its name"""
        for category in self.categories:
            if category.name.lower() == name.lower():
                return category
        return None

# Update forward references
Category.model_rebuild() 