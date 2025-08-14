# Flask Academic Search Engine

A modern, responsive search engine built with Flask that provides real-time auto-suggestions without unwanted automatic searches.

## ✨ Features

- **🔍 Real-time Auto-suggestions**: Get instant suggestions as you type
- **🚫 No Auto-search**: Search only when you want to (button click or suggestion selection)
- **📱 Responsive Design**: Beautiful interface that works on all devices
- **⚡ Fast Performance**: Optimized JavaScript with debouncing
- **🎨 Modern UI**: Clean, Google-inspired design with smooth animations
- **🔄 Multiple Search Sources**: Web results, academic papers, and AI answers

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_flask.txt
```

### 2. Run the Application

```bash
python run_flask.py
```

Or manually:

```bash
python flask_app.py
```

### 3. Open in Browser

Navigate to: `http://localhost:5000`

## 📁 Project Structure

```
search_engine/
├── flask_app.py           # Main Flask application
├── run_flask.py          # Launcher script
├── requirements_flask.txt # Python dependencies
├── templates/
│   └── index.html        # Main HTML template
├── static/
│   ├── css/
│   │   └── style.css     # Responsive CSS styles
│   └── js/
│       └── search.js     # Real-time search functionality
└── README_FLASK.md       # This file
```

## 🔧 How It Works

### Real-time Auto-suggestions

- **Debounced Input**: 200ms delay to prevent excessive API calls
- **Smart Matching**: Starts-with, contains, and fuzzy matching
- **Keyboard Navigation**: Use arrow keys to navigate suggestions
- **Click to Search**: Click any suggestion to search immediately

### Search Behavior

- **Manual Trigger Only**: Searches happen only when:
  - You click the "Search" button
  - You click on a suggestion
  - You press Enter in the search box
- **No Auto-search**: Typing alone will NOT trigger searches
- **Tab/Window Safe**: Changing tabs won't cause unwanted searches

### API Endpoints

#### GET `/api/suggestions?q=query`

Returns real-time suggestions based on the query.

**Response:**

```json
{
  "suggestions": ["machine learning", "machine learning algorithms"],
  "query": "machine",
  "count": 2
}
```

#### POST `/api/search`

Performs the main search across all sources.

**Request:**

```json
{
  "query": "machine learning"
}
```

**Response:**

```json
{
  "query": "machine learning",
  "timestamp": "2024-01-01T12:00:00",
  "web_results": [...],
  "academic_papers": [...],
  "ai_answer": "...",
  "search_time": 1.23,
  "total_results": 25
}
```

## 🎨 Customization

### Adding New Suggestion Sources

Edit the `ACADEMIC_SUGGESTIONS` list in `flask_app.py`:

```python
ACADEMIC_SUGGESTIONS = [
    "your custom suggestion",
    "another suggestion",
    # ... more suggestions
]
```

### Styling

Modify `static/css/style.css` to customize the appearance:

- Colors: Change the CSS variables at the top
- Layout: Modify the grid and flexbox properties
- Animations: Adjust the `@keyframes` animations

### Search Sources

Update the search logic in `flask_app.py`:

- Add new search engines in the `/api/search` endpoint
- Modify the result formatting
- Add new tabs in the HTML template

## 🔌 Integration with Existing Code

To use your existing search modules:

1. **Import your modules** in `flask_app.py`:

```python
from your_web_crawler import WebCrawler
from your_elasticsearch_config import es
from your_ai_module import generate_answer
```

2. **Update the search endpoint** to use your existing functions

3. **Adapt the result format** to match your data structure

## 🐛 Troubleshooting

### Port Already in Use

If port 5000 is busy, change it in `flask_app.py`:

```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Use different port
```

### Module Import Errors

Make sure all your existing search modules are in the Python path:

```python
import sys
sys.path.append('/path/to/your/modules')
```

### Static Files Not Loading

Ensure the directory structure is correct and Flask can find the static files.

## 🆚 Flask vs Streamlit

| Feature               | Flask                                     | Streamlit                           |
| --------------------- | ----------------------------------------- | ----------------------------------- |
| **Auto-suggestions**  | ✅ Real-time with debouncing              | ❌ Limited, causes auto-search      |
| **Search Control**    | ✅ Full control over when searches happen | ❌ Hard to prevent auto-search      |
| **Performance**       | ✅ Optimized JavaScript                   | ⚠️ Can be slow with frequent reruns |
| **Customization**     | ✅ Full HTML/CSS/JS control               | ⚠️ Limited styling options          |
| **Responsive Design** | ✅ Native responsive CSS                  | ⚠️ Limited mobile optimization      |
| **Development Speed** | ⚠️ More setup required                    | ✅ Very fast prototyping            |

## 📈 Performance Tips

1. **Debouncing**: The current 200ms delay balances responsiveness and performance
2. **Caching**: Consider adding Redis for suggestion caching
3. **CDN**: Use a CDN for Font Awesome and other external assets
4. **Compression**: Enable gzip compression for production
5. **Database**: Use SQLite for search history persistence

## 🚀 Next Steps

1. **Add Search History**: Implement persistent search history with SQLite
2. **User Authentication**: Add user accounts and personalized suggestions
3. **Advanced Filtering**: Add date filters, source filters, etc.
4. **Export Results**: Add PDF/Excel export functionality
5. **Analytics**: Track search patterns and popular queries

## 📝 License

This project is open source and available under the MIT License.
