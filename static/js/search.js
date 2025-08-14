// Real-time Search Engine JavaScript

class SearchEngine {
  constructor() {
    this.searchInput = document.getElementById("searchInput");
    this.searchButton = document.getElementById("searchButton");
    this.suggestionsContainer = document.getElementById("suggestionsContainer");
    this.suggestionsList = document.getElementById("suggestionsList");
    this.loadingIndicator = document.getElementById("loadingIndicator");
    this.searchResults = document.getElementById("searchResults");
    this.popularTopics = document.getElementById("popularTopics");

    this.currentQuery = "";
    this.suggestionTimeout = null;
    this.isSearching = false;

    // DEBUG: Log element status
    console.log("🔧 SearchEngine Debug Info:");
    console.log("  searchInput:", this.searchInput);
    console.log("  suggestionsContainer:", this.suggestionsContainer);
    console.log("  suggestionsList:", this.suggestionsList);

    if (!this.suggestionsContainer) {
      console.error("❌ CRITICAL: suggestionsContainer element not found!");
    } else {
      console.log(
        "✅ suggestionsContainer found:",
        this.suggestionsContainer.className
      );
    }

    this.initializeEventListeners();
  }

  initializeEventListeners() {
    // Search input events
    this.searchInput.addEventListener("input", (e) => {
      this.handleInputChange(e.target.value);
    });

    this.searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        this.performSearch();
      } else if (e.key === "Escape") {
        this.hideSuggestions();
      }
    });

    this.searchInput.addEventListener("focus", () => {
      if (this.currentQuery) {
        this.showSuggestions();
      }
    });

    // Click outside to hide suggestions
    document.addEventListener("click", (e) => {
      if (
        !this.suggestionsContainer.contains(e.target) &&
        !this.searchInput.contains(e.target)
      ) {
        this.hideSuggestions();
      }
    });

    // Search button
    this.searchButton.addEventListener("click", () => {
      this.performSearch();
    });

    // Tab switching
    document.querySelectorAll(".tab-button").forEach((button) => {
      button.addEventListener("click", () => {
        this.switchTab(button.dataset.tab);
      });
    });

    // Popular topics
    document.querySelectorAll(".topic-button").forEach((button) => {
      button.addEventListener("click", () => {
        const query = button.dataset.query;
        this.searchInput.value = query;
        this.currentQuery = query;
        this.performSearch();
      });
    });
  }

  handleInputChange(value) {
    this.currentQuery = value.trim();

    // Clear previous timeout
    if (this.suggestionTimeout) {
      clearTimeout(this.suggestionTimeout);
    }

    if (this.currentQuery.length === 0) {
      this.hideSuggestions();
      this.showPopularTopics();
      return;
    }

    this.hidePopularTopics();

    // Debounce the suggestions request
    this.suggestionTimeout = setTimeout(() => {
      this.fetchSuggestions(this.currentQuery);
    }, 200); // 200ms delay for better performance
  }

  async fetchSuggestions(query) {
    if (!query || query.length < 1) {
      this.hideSuggestions();
      return;
    }

    try {
      const response = await fetch(
        `/api/suggestions?q=${encodeURIComponent(query)}`
      );
      const data = await response.json();

      if (data.suggestions && data.suggestions.length > 0) {
        this.displaySuggestions(data.suggestions);
      } else {
        this.hideSuggestions();
      }
    } catch (error) {
      console.error("Error fetching suggestions:", error);
      this.hideSuggestions();
    }
  }

  displaySuggestions(suggestions) {
    console.log("Displaying suggestions:", suggestions); // Debug log
    console.log("Suggestions container element:", this.suggestionsContainer); // Debug log

    if (!this.suggestionsContainer) {
      console.error("❌ Suggestions container not found!");
      return;
    }

    this.suggestionsList.innerHTML = "";

    suggestions.forEach((suggestion, index) => {
      const li = document.createElement("li");
      li.className = "suggestion-item";
      li.innerHTML = `
                <i class="fas fa-search"></i>
                <span>${this.highlightMatch(
                  suggestion,
                  this.currentQuery
                )}</span>
            `;

      li.addEventListener("click", () => {
        this.selectSuggestion(suggestion);
      });

      // Keyboard navigation
      li.addEventListener("mouseenter", () => {
        this.clearSuggestionSelection();
        li.classList.add("selected");
      });

      this.suggestionsList.appendChild(li);
    });

    this.showSuggestions();
    console.log(
      "Suggestions container display:",
      this.suggestionsContainer.style.display
    ); // Debug log
    console.log(
      "Suggestions container visibility:",
      this.suggestionsContainer.style.visibility
    ); // Debug log
  }

  highlightMatch(text, query) {
    if (!query) return text;

    const regex = new RegExp(`(${query})`, "gi");
    return text.replace(regex, "<strong>$1</strong>");
  }

  selectSuggestion(suggestion) {
    this.searchInput.value = suggestion;
    this.currentQuery = suggestion;
    this.hideSuggestions();
    this.performSearch();
  }

  showSuggestions() {
    console.log("Showing suggestions container"); // Debug log
    this.suggestionsContainer.style.display = "block";
    this.suggestionsContainer.style.visibility = "visible";
    this.suggestionsContainer.style.opacity = "1";
  }

  hideSuggestions() {
    console.log("Hiding suggestions container"); // Debug log
    this.suggestionsContainer.style.display = "none";
    this.suggestionsContainer.style.visibility = "hidden";
    this.suggestionsContainer.style.opacity = "0";
  }

  clearSuggestionSelection() {
    document.querySelectorAll(".suggestion-item").forEach((item) => {
      item.classList.remove("selected");
    });
  }

  showPopularTopics() {
    this.popularTopics.style.display = "block";
    this.searchResults.style.display = "none";
  }

  hidePopularTopics() {
    this.popularTopics.style.display = "none";
  }

  async performSearch() {
    if (!this.currentQuery || this.isSearching) {
      return;
    }

    this.isSearching = true;
    this.hideSuggestions();
    this.hidePopularTopics();
    this.showLoading();

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query: this.currentQuery,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        this.displaySearchResults(data);
      } else {
        this.showError(data.error || "Search failed");
      }
    } catch (error) {
      console.error("Search error:", error);
      this.showError("Network error occurred during search");
    } finally {
      this.isSearching = false;
      this.hideLoading();
    }
  }

  showLoading() {
    this.loadingIndicator.style.display = "block";
    this.searchResults.style.display = "none";
  }

  hideLoading() {
    this.loadingIndicator.style.display = "none";
  }

  displaySearchResults(data) {
    // Update result counts
    document.getElementById("webCount").textContent = data.web_results.length;
    document.getElementById("academicCount").textContent =
      data.academic_papers.length;

    // Display service status if available
    if (data.service_status) {
      console.log("Service Status:", data.service_status);
    }

    // Display search timing info
    if (data.search_time) {
      console.log(`Search completed in ${data.search_time}s`);
    }

    // Display web results
    this.displayWebResults(data.web_results);

    // Display academic results
    this.displayAcademicResults(data.academic_papers);

    // Display AI answer
    this.displayAIAnswer(data.ai_answer);

    // Show results container
    this.searchResults.style.display = "block";

    // Switch to the first tab with results
    if (data.web_results.length > 0) {
      this.switchTab("web");
    } else if (data.academic_papers.length > 0) {
      this.switchTab("academic");
    } else {
      this.switchTab("ai");
    }

    // Scroll to results
    this.searchResults.scrollIntoView({ behavior: "smooth" });
  }

  displayWebResults(results) {
    const webResults = document.getElementById("webResults");

    if (results.length === 0) {
      webResults.innerHTML = `
                <div class="no-results">
                    <i class="fas fa-search"></i>
                    <h3>No web results found</h3>
                    <p>Try different keywords or check your spelling</p>
                </div>
            `;
      return;
    }

    webResults.innerHTML = results
      .map(
        (result) => `
            <div class="result-item">
                <a href="${result.url}" target="_blank" class="result-title">
                    ${result.title || "Untitled"}
                </a>
                <p class="result-snippet">
                    ${
                      result.snippet ||
                      result.description ||
                      "No description available"
                    }
                </p>
                <div class="result-meta">
                    <a href="${result.url}" target="_blank" class="result-url">
                        ${this.formatUrl(result.url)}
                    </a>
                    <span class="result-source">
                        <i class="fas fa-globe"></i> Web Result
                    </span>
                </div>
            </div>
        `
      )
      .join("");
  }

  displayAcademicResults(results) {
    const academicResults = document.getElementById("academicResults");

    if (results.length === 0) {
      academicResults.innerHTML = `
                <div class="no-results">
                    <i class="fas fa-graduation-cap"></i>
                    <h3>No academic papers found</h3>
                    <p>Try broader terms or check if academic search is available</p>
                </div>
            `;
      return;
    }

    academicResults.innerHTML = results
      .map(
        (paper) => `
            <div class="result-item">
                <div class="result-title">
                    ${paper.title || "Untitled Paper"}
                </div>
                <p class="result-snippet">
                    ${
                      paper.abstract ||
                      paper.description ||
                      "No abstract available"
                    }
                </p>
                ${
                  paper.preview && paper.preview !== "No preview available"
                    ? `<div class="result-preview">
                      <strong>Preview:</strong> ${paper.preview}
                   </div>`
                    : ""
                }
                <div class="result-meta">
                    <span class="result-authors">
                        <i class="fas fa-user"></i> ${
                          paper.authors || "Unknown Authors"
                        }
                    </span>
                    <span class="result-year">
                        <i class="fas fa-calendar"></i> ${
                          paper.year || "Unknown Year"
                        }
                    </span>
                    <span class="result-score">
                        <i class="fas fa-star"></i> Relevance: ${(
                          paper.score || 0
                        ).toFixed(2)}
                    </span>
                    ${
                      paper.pdf_path
                        ? `<a href="${paper.pdf_path}" target="_blank" class="result-pdf">
                          <i class="fas fa-file-pdf"></i> View PDF
                       </a>`
                        : ""
                    }
                </div>
            </div>
        `
      )
      .join("");
  }

  displayAIAnswer(answer) {
    const aiAnswer = document.getElementById("aiAnswer");

    if (!answer || answer.trim() === "") {
      aiAnswer.innerHTML = `
                <div class="no-results">
                    <i class="fas fa-robot"></i>
                    <h3>AI Answer Not Available</h3>
                    <p>AI answer generation is temporarily unavailable</p>
                </div>
            `;
      return;
    }

    aiAnswer.innerHTML = `
            <h3><i class="fas fa-robot"></i> AI-Generated Answer</h3>
            <div class="ai-content">${this.formatAIAnswer(answer)}</div>
        `;
  }

  formatAIAnswer(answer) {
    // Simple formatting for AI answers
    return answer
      .replace(/\n\n/g, "</p><p>")
      .replace(/\n/g, "<br>")
      .replace(/^/, "<p>")
      .replace(/$/, "</p>");
  }

  formatUrl(url) {
    try {
      const urlObj = new URL(url);
      return urlObj.hostname + (urlObj.pathname !== "/" ? urlObj.pathname : "");
    } catch {
      return url;
    }
  }

  switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll(".tab-button").forEach((button) => {
      button.classList.remove("active");
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add("active");

    // Update tab content
    document.querySelectorAll(".tab-pane").forEach((pane) => {
      pane.classList.remove("active");
    });
    document.getElementById(`${tabName}Tab`).classList.add("active");
  }

  showError(message) {
    this.searchResults.style.display = "block";
    document.getElementById("webResults").innerHTML = `
            <div class="error-message">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>Search Error</h3>
                <p>${message}</p>
            </div>
        `;
    this.switchTab("web");
  }
}

// Initialize the search engine when the page loads
document.addEventListener("DOMContentLoaded", () => {
  const searchEngine = new SearchEngine();

  // Show popular topics initially
  searchEngine.showPopularTopics();

  console.log("Academic Search Engine initialized successfully!");
});
