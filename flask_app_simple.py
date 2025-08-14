from flask import Flask, render_template, request, jsonify
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import Mistral separately (optional)
try:
    from mistral import call_mistral
    mistral_available = True
    print("✅ Mistral AI module imported successfully")
except ImportError as e:
    print(f"⚠️  Mistral AI not available: {e}")
    call_mistral = None
    mistral_available = False
except ValueError as e:
    print(f"⚠️  Mistral API key not configured: {e}")
    call_mistral = None
    mistral_available = False

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secure-secret-key-here')

# Academic suggestions
ACADEMIC_SUGGESTIONS = [
    "machine learning algorithms", "machine learning models", "machine learning applications",
    "mathematics", "mathematical modeling", "data mining", "data analysis", "data science",
    "deep learning neural networks", "natural language processing", "computer vision", 
    "artificial intelligence", "quantum computing", "cybersecurity", "software engineering", 
    "web development", "database systems", "python programming", "javascript frameworks", 
    "data structures algorithms", "mobile app development", "user interface design", 
    "network protocols", "operating systems", "cloud computing", "blockchain technology",
    "algorithms", "programming", "coding", "development", "technology", "science"
]

def get_smart_suggestions(query, suggestions_list, max_results=5):
    """Generate smart suggestions based on query"""
    if not query or len(query.strip()) < 1:
        return []
    
    query_lower = query.lower().strip()
    matched_suggestions = []
    
    # Exact starts-with matches (highest priority)
    for suggestion in suggestions_list:
        if suggestion.lower().startswith(query_lower):
            matched_suggestions.append(suggestion)
    
    # Partial word matches
    if len(matched_suggestions) < max_results:
        for suggestion in suggestions_list:
            if query_lower in suggestion.lower() and suggestion not in matched_suggestions:
                matched_suggestions.append(suggestion)
    
    return matched_suggestions[:max_results]

def generate_ai_answer(query, web_results, academic_papers):
    """Generate AI answer using available AI services"""
    if not mistral_available or not call_mistral:
        return "AI answer generation is not available. Please configure your Mistral API key in the .env file to enable this feature."
    
    try:
        # Prepare context from search results
        context_parts = []
        
        # Add web results context
        for i, result in enumerate(web_results[:3]):  # Top 3 web results
            title = result.get('title', 'No title')
            snippet = result.get('snippet', '')
            context_parts.append(f"Web Result {i+1}: {title}\n{snippet}")
        
        # Add academic papers context
        for i, paper in enumerate(academic_papers[:3]):  # Top 3 papers
            title = paper.get('title', 'No title')
            abstract = paper.get('abstract', '')
            context_parts.append(f"Academic Paper {i+1}: {title}\n{abstract}")
        
        # Combine context
        full_context = "\n\n".join(context_parts)
        
        if not full_context.strip():
            return "No sufficient context available to generate a comprehensive answer."
        
        # Call Mistral API
        ai_response = call_mistral(query, full_context)
        return ai_response
        
    except Exception as e:
        return f"Error generating AI answer: {str(e)}"

@app.route('/')
def index():
    """Main search page"""
    return render_template('index.html')

@app.route('/debug')
def debug_suggestions():
    """Debug page for auto-suggestions"""
    return render_template('debug_suggestions.html')

@app.route('/test')
def test_suggestions():
    """Simple test page for auto-suggestions"""
    with open('test_suggestions.html', 'r') as f:
        return f.read()

@app.route('/simple')
def simple_test():
    """Ultra simple test"""
    with open('simple_test.html', 'r') as f:
        return f.read()

@app.route('/api/suggestions')
def get_suggestions():
    """API endpoint for real-time auto-suggestions"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 1:
        return jsonify({'suggestions': []})
    
    suggestions = get_smart_suggestions(query, ACADEMIC_SUGGESTIONS, max_results=5)
    
    return jsonify({
        'suggestions': suggestions,
        'query': query,
        'count': len(suggestions)
    })

@app.route('/api/search', methods=['POST'])
def search():
    """Simplified search API endpoint"""
    data = request.get_json()
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    search_start_time = time.time()
    
    # Initialize results with mock data for testing
    results = {
        'query': query,
        'timestamp': datetime.now().isoformat(),
        'web_results': [
            {
                'title': f'Sample Result for "{query}" from GeeksforGeeks',
                'url': 'https://www.geeksforgeeks.org/sample',
                'snippet': f'This is a sample result demonstrating search for {query}. Your web crawler would provide real results here.',
                'source': 'GeeksforGeeks'
            },
            {
                'title': f'Another Result for "{query}" from MathWorld',
                'url': 'https://mathworld.wolfram.com/sample',
                'snippet': f'Sample mathematical content related to {query}. Real crawler results would appear here.',
                'source': 'MathWorld'
            }
        ],
        'academic_papers': [
            {
                'title': f'Research Paper on {query}',
                'authors': 'Sample Authors',
                'abstract': f'This is a sample abstract for research on {query}. Real Elasticsearch results would appear here.',
                'year': '2024',
                'score': 0.95,
                'pdf_path': '/sample/paper.pdf'
            }
        ],
        'ai_answer': generate_ai_answer(query, 
            [{'title': f'Sample Result for "{query}"', 'snippet': f'This is sample content about {query} for AI analysis.'}],
            [{'title': f'Research on {query}', 'abstract': f'This is sample academic content about {query} for AI analysis.'}]
        ),
        'search_time': round(time.time() - search_start_time, 2),
        'total_results': 3,
        'service_status': {
            'web_crawler': True,  # Simulated
            'elasticsearch': False,  # Actually not connected
            'minio': True,  # Simulated
            'mistral_ai': mistral_available and bool(call_mistral)
        }
    }
    
    print(f"🎉 Simple search completed for: {query}")
    return jsonify(results)

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'running',
        'message': 'Flask app is working!',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    print("🚀 Starting SIMPLIFIED Flask Academic Search Engine")
    print("=" * 60)
    print("📱 Your app will be available at: http://localhost:5000")
    print("✨ Features:")
    print("   • Real-time auto-suggestions ✅")
    print("   • No unwanted automatic searches ✅") 
    print("   • Beautiful responsive interface ✅")
    print("   • Mock search results (for testing) ✅")
    print("\n💡 This simplified version:")
    print("   • Loads MUCH faster (no AI models)")
    print("   • Shows sample results")
    print("   • Tests the UI and suggestions")
    print("   • Can be upgraded later with real services")
    print("\n⚡ Press Ctrl+C to stop the server")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
