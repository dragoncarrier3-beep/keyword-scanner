document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('searchForm');
    const urlInput = document.getElementById('url');
    const keywordInput = document.getElementById('keyword');
    const submitBtn = document.getElementById('submitBtn');
    const loading = document.getElementById('loading');
    const resultsDiv = document.getElementById('results');

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const url = urlInput.value.trim();
        const keyword = keywordInput.value.trim();

        if (!url || !keyword) {
            showError('Please fill in both URL and keyword fields.');
            return;
        }

        setLoading(true);
        clearResults();

        try {
            const response = await fetch('/scan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    keyword: keyword
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'An error occurred while scanning documents.');
            }

            const results = await response.json();
            displayResults(results, keyword);

        } catch (error) {
            showError(error.message || 'Failed to scan documents. Please check the URL and try again.');
        } finally {
            setLoading(false);
        }
    });

    function setLoading(isLoading) {
        if (isLoading) {
            loading.classList.add('active');
            submitBtn.disabled = true;
        } else {
            loading.classList.remove('active');
            submitBtn.disabled = false;
        }
    }

    function clearResults() {
        resultsDiv.innerHTML = '';
    }

    function showError(message) {
        resultsDiv.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
    }

    function displayResults(results, keyword) {
        if (results.length === 0) {
            resultsDiv.innerHTML = '<div class="no-results">No matches found for the keyword in the scanned documents.</div>';
            return;
        }

        const resultsTitle = document.createElement('div');
        resultsTitle.className = 'results-title';
        resultsTitle.textContent = `Found ${results.length} match${results.length > 1 ? 'es' : ''}`;
        resultsDiv.appendChild(resultsTitle);

        results.forEach(result => {
            const resultItem = document.createElement('div');
            resultItem.className = 'result-item';

            const urlLink = document.createElement('a');
            urlLink.href = result.document_url;
            urlLink.target = '_blank';
            urlLink.className = 'result-url';
            urlLink.textContent = result.document_url;

            const excerptDiv = document.createElement('div');
            excerptDiv.className = 'result-excerpt';
            
            const normalizedKeyword = keyword.toLowerCase();
            const normalizedExcerpt = result.excerpt.toLowerCase();
            const keywordIndex = normalizedExcerpt.indexOf(normalizedKeyword);
            
            if (keywordIndex !== -1) {
                const beforeKeyword = result.excerpt.substring(0, keywordIndex);
                const keywordText = result.excerpt.substring(keywordIndex, keywordIndex + keyword.length);
                const afterKeyword = result.excerpt.substring(keywordIndex + keyword.length);
                
                excerptDiv.innerHTML = 
                    escapeHtml(beforeKeyword) + 
                    `<span class="result-keyword">${escapeHtml(keywordText)}</span>` + 
                    escapeHtml(afterKeyword);
            } else {
                excerptDiv.textContent = result.excerpt;
            }

            resultItem.appendChild(urlLink);
            resultItem.appendChild(excerptDiv);
            resultsDiv.appendChild(resultItem);
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});

