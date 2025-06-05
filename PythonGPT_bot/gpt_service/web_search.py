from duckduckgo_search import DDGS
import asyncio
from typing import List, Dict

async def search_web(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """
    Выполняет поиск в интернете с помощью DuckDuckGo
    
    Args:
        query (str): Поисковый запрос
        max_results (int): Максимальное количество результатов
        
    Returns:
        List[Dict[str, str]]: Список результатов поиска
    """
    try:
        # Создаем экземпляр DDGS
        with DDGS() as ddgs:
            # Выполняем поиск
            results = list(ddgs.text(query, max_results=max_results))
            
            # Форматируем результаты
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'title': result.get('title', ''),
                    'link': result.get('link', ''),
                    'snippet': result.get('body', '')
                })
            
            return formatted_results
    except Exception as e:
        print(f"Ошибка при поиске: {e}")
        return []

def format_search_results(results: List[Dict[str, str]]) -> str:
    """
    Форматирует результаты поиска в читаемый текст
    
    Args:
        results (List[Dict[str, str]]): Список результатов поиска
        
    Returns:
        str: Отформатированный текст с результатами
    """
    if not results:
        return "К сожалению, не удалось найти информацию по вашему запросу."
    
    formatted_text = "🔍 <b>Результаты поиска:</b>\n\n"
    
    for i, result in enumerate(results, 1):
        formatted_text += f"{i}. <b>{result['title']}</b>\n"
        formatted_text += f"📎 {result['link']}\n"
        formatted_text += f"📝 {result['snippet']}\n\n"
    
    return formatted_text 