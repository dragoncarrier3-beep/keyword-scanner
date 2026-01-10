from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.requests import Request
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import pdfplumber
from urllib.parse import urljoin, urlparse
import re
import unicodedata
from typing import List, Optional
import io

app = FastAPI()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class ScanRequest(BaseModel):
    url: str
    keyword: str


class ScanResult(BaseModel):
    document_url: str
    keyword: str
    excerpt: str


def normalize_text(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return text


def find_keyword_excerpt(text: str, keyword: str, context_chars: int = 200) -> Optional[str]:
    normalized_text = normalize_text(text)
    normalized_keyword = normalize_text(keyword)
    
    index = normalized_text.find(normalized_keyword)

    if index == -1:
        return None
    
    start = max(0, index - context_chars)
    end = min(len(text), index + len(keyword) + context_chars)
    
    excerpt = text[start:end].strip()
    excerpt = re.sub(r'\s+', ' ', excerpt)
    
    return excerpt


def extract_text_from_pdf(url: str) -> Optional[str]:
    try:
        response = requests.get(url, timeout=15, stream=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        max_size = 10 * 1024 * 1024
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > max_size:
            print(f"PDF too large: {url} ({content_length} bytes)")
            return None
        
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > max_size:
                print(f"PDF too large during download: {url}")
                return None
        
        pdf_file = io.BytesIO(content)
        text_content = []
        max_pages = 20
        max_text_length = 500000
        
        with pdfplumber.open(pdf_file) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                if len('\n'.join(text_content)) > max_text_length:
                    break
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        
        result = '\n'.join(text_content)
        if len(result) > max_text_length:
            result = result[:max_text_length]
        
        del content, pdf_file
        return result
    except Exception as e:
        print(f"Error extracting PDF from {url}: {e}")
        return None


def extract_text_from_html(url: str) -> Optional[str]:
    try:
        response = requests.get(url, timeout=15, stream=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        max_size = 5 * 1024 * 1024
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > max_size:
            print(f"HTML too large: {url} ({content_length} bytes)")
            return None
        
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > max_size:
                print(f"HTML too large during download: {url}")
                return None
        
        soup = BeautifulSoup(content, 'html.parser')
        
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        max_text_length = 500000
        if len(text) > max_text_length:
            text = text[:max_text_length]
        
        del content, soup
        return text
    except Exception as e:
        print(f"Error extracting HTML from {url}: {e}")
        return None


def find_document_links(base_url: str) -> List[str]:
    try:
        response = requests.get(base_url, timeout=15, stream=True, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        
        max_size = 2 * 1024 * 1024
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > max_size:
            print(f"Base page too large: {base_url}")
            return []
        
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > max_size:
                break
        
        soup = BeautifulSoup(content, 'html.parser')
        document_links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            full_url = urljoin(base_url, href)
            
            parsed = urlparse(full_url)
            if parsed.scheme not in ['http', 'https']:
                continue
            
            path_lower = parsed.path.lower()
            if path_lower.endswith('.pdf'):
                document_links.append(full_url)
            elif path_lower.endswith(('.html', '.htm')):
                document_links.append(full_url)
        
        del content, soup
        return list(set(document_links))
    except Exception as e:
        print(f"Error fetching base URL {base_url}: {e}")
        return []


def search_document(url: str, keyword: str) -> Optional[ScanResult]:
    text = None
    try:
        if url.endswith('.pdf'):
            text = extract_text_from_pdf(url)
        elif url.endswith(('.html', '.htm')):
            text = extract_text_from_html(url)
        else:
            return None
        
        if not text:
            return None
        
        excerpt = find_keyword_excerpt(text, keyword)
        if not excerpt:
            return None
        
        result = ScanResult(
            document_url=url,
            keyword=keyword,
            excerpt=excerpt
        )
        return result
    finally:
        if text:
            del text
            import gc
            gc.collect()


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/scan", response_model=List[ScanResult])
async def scan_documents(request: ScanRequest):
    try:
        parsed_url = urlparse(request.url)
        if parsed_url.scheme not in ['http', 'https']:
            raise HTTPException(status_code=400, detail="Invalid URL scheme. Use http:// or https://")
        
        if not request.url or not request.keyword:
            raise HTTPException(status_code=400, detail="URL and keyword are required")
        
        document_links = find_document_links(request.url)
        
        if not document_links:
            return []
        
        document_links = document_links[:3]
        
        results = []
        for doc_url in document_links:
            try:
                result = search_document(doc_url, request.keyword)
                if result:
                    results.append(result)
            except Exception as e:
                print(f"Error processing document {doc_url}: {e}")
                continue
            finally:
                import gc
                gc.collect()
        
        return results
    
    except HTTPException:
        raise
    except requests.RequestException as e:
        error_msg = str(e) if str(e) else "Error fetching URL"
        raise HTTPException(status_code=400, detail=f"Network error: {error_msg}")
    except Exception as e:
        error_msg = str(e) if str(e) else "Unknown error occurred"
        print(f"Unexpected error in scan_documents: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {error_msg}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

