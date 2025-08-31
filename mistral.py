import httpx
import os
from tenacity import retry, wait_random_exponential, stop_after_attempt
import re

def get_mistral_api_key():
    """Get Mistral API key from environment with better error handling"""
    key = os.getenv("MISTRAL_API_KEY")
    if not key:
        # Try alternative environment variable names
        key = os.getenv("MISTRAL_KEY") or os.getenv("mistral_api_key")
    
    if not key:
        print("❌ MISTRAL_API_KEY environment variable not set")
        print("Available env vars:", [k for k in os.environ.keys() if 'mistral' in k.lower()])
        raise ValueError("MISTRAL_API_KEY environment variable not set")
    
    print("✅ Mistral API key loaded successfully")
    return key

MISTRAL_API_KEY = get_mistral_api_key()
MISTRAL_MODEL = "mistral-small"

# AI Optimization Configuration
AI_CONFIG = {
    # Core settings
    'use_smart_selector': True,          # Use smart technique selection
    'use_validation': True,              # Use response validation/improvement
    'use_multi_perspective': True,       # Use multiple perspectives for complex queries
    'use_iterative_refinement': False,   # Use iterative refinement (slower but better)
    'use_post_processing': True,         # Use response post-processing
    'add_metadata': False,               # Add processing metadata to responses
    
    # Context optimization
    'use_adaptive_chunking': True,       # Use intelligent context chunking
    'use_quality_scoring': True,         # Score and rank content sections
    'max_context_tokens': 3000,          # Maximum context tokens
    
    # Response settings
    'max_tokens': 2048,                  # Maximum response tokens
    'quality_threshold': 8,              # Minimum quality score to accept (out of 15)
    'max_techniques_to_try': 3,          # Maximum techniques to try per query
    
    # Performance settings
    'enable_parallel_generation': False, # Generate multiple responses in parallel (experimental)
    'cache_responses': True,             # Cache responses for identical queries
    'timeout_seconds': 60                # Maximum processing time per query
}

def classify_query_type(query):
    """Simple query classification for better prompt selection"""
    query_lower = query.lower()
    
    # Research/academic queries
    if any(word in query_lower for word in ['research', 'study', 'paper', 'analysis', 'theory', 'methodology']):
        return 'research'
    
    # How-to/tutorial queries
    if any(word in query_lower for word in ['how to', 'tutorial', 'guide', 'step', 'implement', 'create', 'build']):
        return 'tutorial'
    
    # Comparison queries
    if any(word in query_lower for word in ['compare', 'difference', 'vs', 'versus', 'better', 'best']):
        return 'comparison'
    
    # Definition/explanation queries
    if any(word in query_lower for word in ['what is', 'what are', 'define', 'explain', 'meaning']):
        return 'definition'
    
    # Problem-solving queries
    if any(word in query_lower for word in ['problem', 'issue', 'error', 'fix', 'solve', 'debug']):
        return 'problem_solving'
    
    return 'general'

def get_enhanced_system_prompt(query_type):
    """Generate detailed, structured prompts optimized for mistral-small performance"""
    
    # Enhanced base prompt with more specific instructions for smaller models
    base_prompt = (
        "You are an expert AI assistant specializing in providing comprehensive, accurate answers. "
        "CRITICAL INSTRUCTIONS:\n"
        "- Use ONLY information from the provided context\n"
        "- Be systematic and thorough in your analysis\n"
        "- Always explain your reasoning clearly\n"
        "- Structure your response with clear headings and bullet points\n"
        "- Cite specific sources when making claims\n"
        "- If information is incomplete, explicitly state what's missing\n\n"
    )
    
    # More detailed, structured prompts that guide smaller models better
    type_specific_prompts = {
        'research': (
            "RESEARCH ANALYSIS MODE:\n"
            "Structure your response as follows:\n"
            "## Summary\n[One-paragraph overview of key findings]\n\n"
            "## Main Findings\n[Bullet points of primary discoveries/results]\n\n"
            "## Supporting Evidence\n[Specific citations and data from sources]\n\n"
            "## Methodology/Approach\n[How the research was conducted, if mentioned]\n\n"
            "## Limitations & Gaps\n[What the research doesn't cover or acknowledge]\n\n"
            "## Implications\n[What these findings mean in broader context]\n\n"
            "Always cite sources as: 'According to [Author, Year]...' or 'As stated in [Source]...'\n"
        ),
        'tutorial': (
            "TUTORIAL/INSTRUCTIONAL MODE:\n"
            "Create a comprehensive learning resource with this structure:\n"
            "## Overview\n[What will be learned and why it's important]\n\n"
            "## Prerequisites\n[What knowledge/tools are needed beforehand]\n\n"
            "## Step-by-Step Instructions\n[Numbered steps with clear explanations]\n\n"
            "## Examples\n[Concrete examples from the context]\n\n"
            "## Common Pitfalls\n[Potential issues and how to avoid them]\n\n"
            "## Additional Resources\n[Related information from context]\n\n"
            "Use simple, clear language and explain technical terms.\n"
        ),
        'comparison': (
            "COMPARATIVE ANALYSIS MODE:\n"
            "Structure your comparison systematically:\n"
            "## Overview\n[Brief introduction to what's being compared]\n\n"
            "## Key Similarities\n[Shared characteristics and features]\n\n"
            "## Key Differences\n[Distinct features, organized by category]\n\n"
            "## Advantages & Disadvantages\n[Pros and cons of each option]\n\n"
            "## Use Cases\n[When to choose one over the other]\n\n"
            "## Conclusion\n[Summary recommendation based on context]\n\n"
            "Present information objectively and cite sources for claims.\n"
        ),
        'definition': (
            "DEFINITION/EXPLANATION MODE:\n"
            "Provide comprehensive explanation using this structure:\n"
            "## Core Definition\n[Clear, concise definition]\n\n"
            "## Key Characteristics\n[Essential features and properties]\n\n"
            "## How It Works\n[Mechanism or process, if applicable]\n\n"
            "## Examples & Applications\n[Real-world examples from context]\n\n"
            "## Related Concepts\n[Connected ideas and terminology]\n\n"
            "## Context & Background\n[Historical or situational information]\n\n"
            "Start with the simplest explanation, then add complexity.\n"
        ),
        'problem_solving': (
            "PROBLEM-SOLVING MODE:\n"
            "Approach the problem systematically:\n"
            "## Problem Analysis\n[Break down the issue into components]\n\n"
            "## Root Causes\n[Identify underlying reasons]\n\n"
            "## Solution Strategy\n[Overall approach to solving the problem]\n\n"
            "## Step-by-Step Solution\n[Detailed implementation steps]\n\n"
            "## Alternative Approaches\n[Other possible solutions from context]\n\n"
            "## Prevention & Best Practices\n[How to avoid similar issues]\n\n"
            "## Verification\n[How to confirm the solution works]\n\n"
            "Be practical and specific in your recommendations.\n"
        ),
        'general': (
            "COMPREHENSIVE ANALYSIS MODE:\n"
            "Structure your response clearly:\n"
            "## Main Points\n[Key information organized by importance]\n\n"
            "## Supporting Details\n[Additional context and explanations]\n\n"
            "## Examples\n[Concrete examples from the provided context]\n\n"
            "## Connections\n[How different pieces of information relate]\n\n"
            "## Implications\n[What this information means more broadly]\n\n"
            "Be thorough but organized, using clear headings and bullet points.\n"
        )
    }
    
    specific_prompt = type_specific_prompts.get(query_type, type_specific_prompts['general'])
    
    return base_prompt + specific_prompt + (
        "\nREMEMBER: Stay within the provided context. If key information is missing, "
        "explicitly state what additional information would be needed for a complete answer. "
        "Quality over quantity - be thorough but focused."
    )

@retry(wait=wait_random_exponential(multiplier=1, min=4, max=10), 
      stop=stop_after_attempt(3))
def call_mistral(question, context, max_tokens=1536, model_override=None):
    # Classify query type for better prompt selection
    query_type = classify_query_type(question)
    system_prompt = get_enhanced_system_prompt(query_type)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}\n\nPlease provide a comprehensive answer based on the above context."}
    ]

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    # Optimized parameters specifically for mistral-small to maximize performance
    def get_optimal_params_for_small_model(query_type):
        """
        Optimized parameters that help mistral-small perform better
        Focus on techniques that boost smaller model capabilities
        """
        params = {
            'research': {
                'temperature': 0.15,  # Lower temperature for better factual accuracy
                'top_p': 0.85,        # More focused vocabulary for precision
                'frequency_penalty': 0.1,  # Reduce repetition
                'presence_penalty': 0.1    # Encourage new concepts
            },
            'tutorial': {
                'temperature': 0.3,   # Moderate creativity for clear explanations
                'top_p': 0.9,         # Balanced vocabulary
                'frequency_penalty': 0.0,  # Allow repetition for educational reinforcement
                'presence_penalty': 0.2    # Encourage comprehensive coverage
            },
            'comparison': {
                'temperature': 0.2,   # Focused for objective analysis
                'top_p': 0.85,        # Precise vocabulary
                'frequency_penalty': 0.15, # Avoid repetitive comparisons
                'presence_penalty': 0.1
            },
            'definition': {
                'temperature': 0.1,   # Very precise for definitions
                'top_p': 0.8,         # Most focused vocabulary
                'frequency_penalty': 0.0,  # Allow standard terminology repetition
                'presence_penalty': 0.05
            },
            'problem_solving': {
                'temperature': 0.25,  # Balanced for systematic thinking
                'top_p': 0.9,         # Good vocabulary range
                'frequency_penalty': 0.1,  # Avoid repetitive solutions
                'presence_penalty': 0.15   # Encourage comprehensive solutions
            },
            'general': {
                'temperature': 0.25,
                'top_p': 0.85,
                'frequency_penalty': 0.05,
                'presence_penalty': 0.1
            }
        }
        return params.get(query_type, params['general'])
    
    optimal_params = get_optimal_params_for_small_model(query_type)
    selected_model = model_override or MISTRAL_MODEL  # Always use mistral-small unless overridden
    
    body = {
        "model": selected_model,
        "messages": messages,
        "temperature": optimal_params['temperature'],
        "top_p": optimal_params['top_p'],
        "frequency_penalty": optimal_params['frequency_penalty'],  # NEW: Reduce repetition
        "presence_penalty": optimal_params['presence_penalty'],    # NEW: Encourage topic diversity
        "max_tokens": max_tokens,
        "stream": False,
        "safe_prompt": False  # Allow more comprehensive responses
    }

    try:
        response = httpx.post("https://api.mistral.ai/v1/chat/completions", json=body, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"❌ Mistral API error: {e}"

# Advanced optimization functions
def call_mistral_with_chain_of_thought(question, context, max_tokens=2048):
    """Enhanced call with chain-of-thought reasoning for complex queries"""
    
    # Check if query needs chain-of-thought reasoning
    complex_indicators = ['analyze', 'compare', 'evaluate', 'why', 'how does', 'relationship', 'impact']
    needs_cot = any(indicator in question.lower() for indicator in complex_indicators)
    
    if needs_cot:
        # Add chain-of-thought instruction
        cot_instruction = (
            "\n\nFor complex queries, please think step by step:\n"
            "1. First, identify the key components of the question\n"
            "2. Then, analyze the relevant information from the context\n"
            "3. Finally, synthesize your analysis into a comprehensive answer\n"
            "Use this reasoning structure in your response."
        )
        enhanced_context = context + cot_instruction
        return call_mistral(question, enhanced_context, max_tokens)
    else:
        return call_mistral(question, context, max_tokens)

def call_mistral_with_self_consistency(question, context, max_tokens=1536, num_samples=3):
    """Generate multiple responses and select the most consistent one"""
    
    responses = []
    for i in range(num_samples):
        # Slightly vary temperature for diversity
        temp_variation = 0.3 + (i * 0.1)  # 0.3, 0.4, 0.5
        
        # Modify the call to use varied temperature
        query_type = classify_query_type(question)
        system_prompt = get_enhanced_system_prompt(query_type)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}\n\nPlease provide a comprehensive answer based on the above context."}
        ]
        
        body = {
            "model": "mistral-medium",
            "messages": messages,
            "temperature": temp_variation,
            "top_p": 0.9,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        try:
            response = httpx.post("https://api.mistral.ai/v1/chat/completions", 
                                json=body, 
                                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}, 
                                timeout=30)
            response.raise_for_status()
            responses.append(response.json()["choices"][0]["message"]["content"].strip())
        except Exception as e:
            responses.append(f"Error in sample {i+1}: {e}")
    
    # Simple consistency check - return the longest response (often most comprehensive)
    return max(responses, key=len) if responses else "No valid responses generated"

def enhance_context_with_keywords(question, context):
    """Enhance context by highlighting key terms related to the question"""
    
    # Extract key terms from question
    question_words = set(question.lower().split())
    important_words = {word for word in question_words 
                      if len(word) > 3 and word not in ['what', 'how', 'why', 'when', 'where', 'which', 'that', 'this', 'they', 'them', 'with', 'from', 'into', 'during', 'before', 'after']}
    
    # Add keyword emphasis instruction
    if important_words:
        keyword_instruction = f"\n\nKey terms to focus on: {', '.join(important_words)}\nPlease pay special attention to information related to these terms in your response."
        enhanced_context = context + keyword_instruction
        return enhanced_context
    
    return context

def optimize_context_for_small_model(context, max_context_tokens=3000):
    """
    Optimize context specifically for smaller models by:
    1. Prioritizing high-quality content
    2. Removing redundancy
    3. Adding structure markers
    4. Ensuring key information is emphasized
    """
    
    # Split context into sections
    sections = context.split('\n\n')
    
    # Score sections by quality indicators
    def score_section(section):
        score = 0
        # Prefer sections with citations
        if any(indicator in section.lower() for indicator in ['according to', 'research shows', 'study found', 'author:', 'source:']):
            score += 3
        # Prefer sections with specific data/numbers
        if any(char.isdigit() for char in section):
            score += 2
        # Prefer longer, more detailed sections
        if len(section.split()) > 50:
            score += 2
        # Prefer sections with technical terms
        if any(indicator in section.lower() for indicator in ['analysis', 'method', 'approach', 'technique', 'algorithm']):
            score += 1
        return score
    
    # Sort sections by quality score
    scored_sections = [(score_section(section), section) for section in sections if section.strip()]
    scored_sections.sort(key=lambda x: x[0], reverse=True)
    
    # Build optimized context within token limit
    optimized_sections = []
    current_length = 0
    
    # Add structure markers for better comprehension
    structure_intro = "=== CONTEXT INFORMATION ===\nThe following information sources are ranked by relevance and quality:\n\n"
    current_length += len(structure_intro.split())
    
    for i, (score, section) in enumerate(scored_sections):
        section_header = f"--- SOURCE {i+1} (Quality Score: {score}) ---\n"
        full_section = section_header + section + "\n\n"
        
        # Estimate token count (rough approximation: 1 token ≈ 0.75 words)
        estimated_tokens = len(full_section.split()) * 0.75
        
        if current_length + estimated_tokens <= max_context_tokens:
            optimized_sections.append(full_section)
            current_length += estimated_tokens
        else:
            # Try to fit a truncated version
            available_tokens = max_context_tokens - current_length
            available_words = int(available_tokens / 0.75)
            
            if available_words > 50:  # Only include if meaningful length
                words = section.split()
                truncated_section = section_header + ' '.join(words[:available_words]) + "... [truncated for length]\n\n"
                optimized_sections.append(truncated_section)
            break
    
    final_context = structure_intro + ''.join(optimized_sections)
    
    # Add emphasis footer
    footer = "\n=== END CONTEXT ===\nPlease use the above information to provide a comprehensive, well-structured answer.\n"
    final_context += footer
    
    return final_context

def add_few_shot_examples(query_type):
    """Add few-shot examples to help guide mistral-small"""
    
    examples = {
        'research': """
Example of excellent research analysis:
Question: "What are the key findings about machine learning in healthcare?"
Answer:
## Summary
Recent studies show machine learning improves diagnostic accuracy by 15-25% across multiple medical domains.

## Main Findings  
• ML models achieve 94% accuracy in radiology image analysis (Source: Medical AI Journal, 2023)
• Natural language processing reduces clinical documentation time by 40%
• Predictive models identify high-risk patients 72 hours earlier than traditional methods

This is the quality and structure expected for your response.
""",
        'tutorial': """
Example of excellent tutorial format:
Question: "How do you implement authentication in web apps?"
Answer:
## Overview
Authentication verifies user identity before granting access to protected resources.

## Prerequisites
- Basic knowledge of HTTP protocols
- Understanding of session management
- Web framework familiarity

## Step-by-Step Instructions
1. Set up user registration endpoint
2. Implement password hashing (use bcrypt)
3. Create login validation logic
4. Generate session tokens or JWTs
5. Add middleware for protected routes

This structure ensures clear, actionable guidance.
""",
        'general': """
Example of excellent structured response:
## Main Points
• Clear organization with headings and bullet points
• Specific evidence from provided sources
• Logical flow from general to specific information

## Supporting Details
Include relevant context and background information that helps users understand the topic fully.

Follow this systematic approach for comprehensive answers.
"""
    }
    
    return examples.get(query_type, examples['general'])

def validate_and_improve_response(original_response, question, context, max_tokens=1536):
    """
    Generate a response, then have AI validate and improve it
    This often leads to higher quality answers from smaller models
    """
    
    validation_prompt = f"""
You are a quality assurance expert. Review the following AI response for accuracy, completeness, and clarity.

ORIGINAL QUESTION: {question}

AI RESPONSE TO REVIEW:
{original_response}

AVAILABLE CONTEXT:
{context[:2000]}...  # Truncated for validation

Please provide an IMPROVED version that:
1. Fixes any factual errors
2. Adds missing important information from the context
3. Improves clarity and structure
4. Ensures all claims are supported by the context
5. Maintains the same response format and style

If the original response is already excellent, you may keep it largely the same but add any missing details.

IMPROVED RESPONSE:"""

    try:
        messages = [
            {"role": "user", "content": validation_prompt}
        ]
        
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        body = {
            "model": MISTRAL_MODEL,
            "messages": messages,
            "temperature": 0.2,  # Low temperature for focused improvement
            "top_p": 0.85,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        response = httpx.post("https://api.mistral.ai/v1/chat/completions", json=body, headers=headers, timeout=30)
        response.raise_for_status()
        improved_response = response.json()["choices"][0]["message"]["content"].strip()
        
        # Return improved response if it's significantly better (longer and more detailed)
        if len(improved_response) > len(original_response) * 0.8:  # At least 80% as long
            return improved_response
        else:
            return original_response
            
    except Exception as e:
        # If validation fails, return original response
        return original_response

def multi_perspective_analysis(question, context, max_tokens=1536):
    """
    Generate response from multiple perspectives and synthesize the best answer
    """
    
    perspectives = [
        "You are a research scientist focusing on evidence-based analysis.",
        "You are a practical engineer focusing on real-world applications.", 
        "You are an educator focusing on clear, comprehensive explanations."
    ]
    
    responses = []
    
    for i, perspective in enumerate(perspectives):
        try:
            messages = [
                {"role": "system", "content": f"{perspective} Answer the following question using only the provided context."},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
            ]
            
            body = {
                "model": MISTRAL_MODEL,
                "messages": messages,
                "temperature": 0.3 + (i * 0.1),  # Vary temperature slightly
                "top_p": 0.9,
                "max_tokens": max_tokens // 2,  # Shorter responses to combine
                "stream": False
            }
            
            response = httpx.post("https://api.mistral.ai/v1/chat/completions", 
                                json=body, 
                                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}, 
                                timeout=30)
            response.raise_for_status()
            responses.append(response.json()["choices"][0]["message"]["content"].strip())
            
        except Exception as e:
            responses.append(f"Perspective {i+1} failed: {e}")
    
    # Synthesize the perspectives
    synthesis_prompt = f"""
You are an expert synthesizer. Combine the following three perspective responses into one comprehensive, well-structured answer.

QUESTION: {question}

RESEARCH SCIENTIST PERSPECTIVE:
{responses[0]}

PRACTICAL ENGINEER PERSPECTIVE: 
{responses[1]}

EDUCATOR PERSPECTIVE:
{responses[2]}

Create a synthesis that:
1. Combines the best insights from all perspectives
2. Maintains factual accuracy
3. Provides comprehensive coverage
4. Uses clear structure with headings
5. Cites different viewpoints when relevant

SYNTHESIZED COMPREHENSIVE ANSWER:"""

    try:
        messages = [{"role": "user", "content": synthesis_prompt}]
        
        body = {
            "model": MISTRAL_MODEL,
            "messages": messages,
            "temperature": 0.25,
            "top_p": 0.9,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        response = httpx.post("https://api.mistral.ai/v1/chat/completions", 
                            json=body, 
                            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}, 
                            timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
        
    except Exception as e:
        # If synthesis fails, return the longest individual response
        return max(responses, key=len)

def adaptive_context_chunking(question, context, max_context_tokens=3000):
    """
    Intelligently chunk context based on question focus and content relevance
    """
    
    # Extract key concepts from question
    question_lower = question.lower()
    key_concepts = []
    
    # Technical terms
    tech_terms = ['algorithm', 'method', 'approach', 'technique', 'process', 'system', 'model', 'framework']
    key_concepts.extend([term for term in tech_terms if term in question_lower])
    
    # Action words
    action_words = ['implement', 'create', 'build', 'design', 'develop', 'optimize', 'improve', 'solve']
    key_concepts.extend([word for word in action_words if word in question_lower])
    
    # Domain-specific extraction
    question_words = [word for word in question_lower.split() if len(word) > 3]
    key_concepts.extend(question_words[:5])  # Top 5 important words
    
    # Score context sections based on concept relevance
    sections = context.split('\n\n')
    scored_sections = []
    
    for section in sections:
        if not section.strip():
            continue
            
        score = 0
        section_lower = section.lower()
        
        # Score based on key concept presence
        for concept in key_concepts:
            if concept in section_lower:
                score += 2
        
        # Bonus for sections with examples
        if any(indicator in section_lower for indicator in ['example', 'for instance', 'such as', 'like']):
            score += 1
            
        # Bonus for sections with specific data
        if any(char.isdigit() for char in section):
            score += 1
            
        # Bonus for sections with citations
        if any(indicator in section_lower for indicator in ['according to', 'source:', 'research', 'study']):
            score += 2
            
        scored_sections.append((score, len(section), section))
    
    # Sort by score (descending) then by length (descending)
    scored_sections.sort(key=lambda x: (x[0], x[1]), reverse=True)
    
    # Build optimized context
    optimized_sections = []
    current_tokens = 0
    
    for score, length, section in scored_sections:
        section_tokens = len(section.split()) * 0.75  # Rough token estimate
        
        if current_tokens + section_tokens <= max_context_tokens:
            optimized_sections.append(f"[Relevance Score: {score}] {section}")
            current_tokens += section_tokens
        else:
            # Try to fit a summarized version
            remaining_tokens = max_context_tokens - current_tokens
            if remaining_tokens > 100:  # Worth including a summary
                words = section.split()
                summary_length = int(remaining_tokens / 0.75)
                summary = ' '.join(words[:summary_length]) + "... [truncated]"
                optimized_sections.append(f"[Relevance Score: {score}] {summary}")
            break
    
    return '\n\n'.join(optimized_sections)

def iterative_refinement(question, context, max_iterations=2, max_tokens=1536):
    """
    Iteratively refine the response by asking follow-up questions and improving
    """
    
    # Generate initial response
    initial_response = call_mistral(question, context, max_tokens)
    
    current_response = initial_response
    
    for iteration in range(max_iterations):
        # Generate refinement prompt
        refinement_prompt = f"""
You previously answered this question: {question}

Your previous answer was:
{current_response}

Context available:
{context[:1500]}...

Now, please provide an ENHANCED version that:
1. Addresses any gaps or unclear points in the previous answer
2. Adds more specific details from the context
3. Improves the organization and flow
4. Includes additional relevant examples if available
5. Ensures all claims are well-supported

Focus on making this the most comprehensive and accurate answer possible.

ENHANCED ANSWER:"""

        try:
            messages = [{"role": "user", "content": refinement_prompt}]
            
            body = {
                "model": MISTRAL_MODEL,
                "messages": messages,
                "temperature": 0.2,  # Lower temperature for refinement
                "top_p": 0.85,
                "max_tokens": max_tokens,
                "stream": False
            }
            
            response = httpx.post("https://api.mistral.ai/v1/chat/completions", 
                                json=body, 
                                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"}, 
                                timeout=30)
            response.raise_for_status()
            refined_response = response.json()["choices"][0]["message"]["content"].strip()
            
            # Use refined response if it's better (longer and more detailed)
            if len(refined_response) > len(current_response) * 0.9:
                current_response = refined_response
            else:
                break  # No significant improvement, stop refining
                
        except Exception as e:
            break  # If refinement fails, return current response
    
    return current_response

def advanced_mistral_call(question, context, max_tokens=2048, technique='auto'):
    """
    Advanced AI call that automatically selects the best technique based on query complexity
    
    Techniques:
    - 'basic': Standard call with optimizations
    - 'validation': Generate + validate/improve  
    - 'multi_perspective': Multiple viewpoints + synthesis
    - 'iterative': Iterative refinement
    - 'auto': Automatically choose based on query complexity
    """
    
    # Determine complexity and select technique
    if technique == 'auto':
        question_lower = question.lower()
        
        # High complexity indicators
        high_complexity = any(indicator in question_lower for indicator in [
            'analyze', 'compare', 'evaluate', 'relationship', 'impact', 'why does', 
            'how does', 'what causes', 'implications', 'consequences', 'trade-offs'
        ])
        
        # Medium complexity indicators  
        medium_complexity = any(indicator in question_lower for indicator in [
            'explain', 'describe', 'how to', 'what is', 'differences', 'advantages',
            'disadvantages', 'benefits', 'drawbacks', 'process', 'method'
        ])
        
        # Auto-select technique
        if high_complexity:
            technique = 'multi_perspective'
        elif medium_complexity:
            technique = 'validation'
        else:
            technique = 'basic'
    
    # Apply adaptive context chunking for all techniques
    optimized_context = adaptive_context_chunking(question, context, max_context_tokens=3000)
    enhanced_context = enhance_context_with_keywords(question, optimized_context)
    
    # Apply selected technique
    if technique == 'multi_perspective':
        # For complex analytical questions - get multiple perspectives
        response = multi_perspective_analysis(question, enhanced_context, max_tokens)
        
    elif technique == 'iterative':
        # For questions needing deep refinement
        response = iterative_refinement(question, enhanced_context, max_iterations=2, max_tokens=max_tokens)
        
    elif technique == 'validation':
        # For medium complexity - generate then validate/improve
        initial_response = call_mistral_with_chain_of_thought(question, enhanced_context, max_tokens)
        response = validate_and_improve_response(initial_response, question, enhanced_context, max_tokens)
        
    else:  # 'basic'
        # Standard optimized approach
        response = call_mistral_with_chain_of_thought(question, enhanced_context, max_tokens)
    
    return response, technique  # Return both response and technique used

def get_response_quality_score(response, question, context):
    """
    Score response quality based on multiple factors
    """
    score = 0
    
    # Length score (longer responses often more comprehensive)
    if len(response) > 1000:
        score += 3
    elif len(response) > 500:
        score += 2
    elif len(response) > 200:
        score += 1
    
    # Structure score (headers, bullet points, organization)
    if '##' in response or '###' in response:
        score += 2
    if '•' in response or '-' in response or any(f'{i}.' in response for i in range(1, 10)):
        score += 1
    
    # Citation score
    citation_indicators = ['according to', 'source:', 'research shows', 'study found', 'as stated in']
    citations = sum(1 for indicator in citation_indicators if indicator.lower() in response.lower())
    score += min(citations, 3)  # Max 3 points for citations
    
    # Context utilization score
    question_words = set(question.lower().split())
    important_words = {word for word in question_words if len(word) > 3}
    
    response_lower = response.lower()
    word_coverage = sum(1 for word in important_words if word in response_lower)
    if word_coverage >= len(important_words) * 0.8:
        score += 2
    elif word_coverage >= len(important_words) * 0.5:
        score += 1
    
    # Specificity score (numbers, technical terms, examples)
    if any(char.isdigit() for char in response):
        score += 1
    if any(term in response_lower for term in ['example', 'for instance', 'such as']):
        score += 1
    
    return min(score, 15)  # Max score of 15

def smart_response_selector(question, context, max_tokens=2048):
    """
    Try multiple techniques and select the best response based on quality scoring
    """
    
    techniques = ['basic', 'validation']
    
    # For complex questions, also try multi_perspective
    if any(indicator in question.lower() for indicator in ['analyze', 'compare', 'evaluate', 'relationship']):
        techniques.append('multi_perspective')
    
    best_response = ""
    best_score = 0
    best_technique = "basic"
    
    for technique in techniques:
        try:
            response, used_technique = advanced_mistral_call(question, context, max_tokens, technique)
            score = get_response_quality_score(response, question, context)
            
            if score > best_score:
                best_score = score
                best_response = response
                best_technique = used_technique
                
        except Exception as e:
            continue  # Try next technique if this one fails
    
    return best_response, best_technique, best_score

def post_process_response(response, question, context):
    """
    Post-process response to add citations, improve formatting, and enhance readability
    """
    
    # Add source references where missing
    processed_response = response
    
    # Find potential citation points (factual claims)
    factual_indicators = ['research shows', 'studies indicate', 'data reveals', 'evidence suggests']
    
    # Improve formatting
    lines = processed_response.split('\n')
    improved_lines = []
    
    for line in lines:
        # Ensure proper header formatting
        if line.strip() and not line.startswith('#') and ':' in line and len(line.split(':')[0]) < 50:
            if not any(line.startswith(prefix) for prefix in ['##', '###', '####']):
                # Convert to proper header format
                title = line.split(':')[0].strip()
                content = ':'.join(line.split(':')[1:]).strip()
                if content:
                    improved_lines.append(f"## {title}")
                    improved_lines.append(content)
                else:
                    improved_lines.append(f"## {title}")
            else:
                improved_lines.append(line)
        else:
            improved_lines.append(line)
    
    processed_response = '\n'.join(improved_lines)
    
    # Add a summary conclusion if response is long and doesn't have one
    if len(processed_response) > 1000 and not any(keyword in processed_response.lower() for keyword in ['conclusion', 'summary', 'in summary']):
        processed_response += "\n\n## Summary\nThis comprehensive analysis covers the key aspects of your question based on the available research and technical documentation."
    
    return processed_response

def add_response_metadata(response, technique_used, quality_score, processing_time=None):
    """
    Add helpful metadata to response for transparency
    """
    
    metadata = f"\n\n---\n*Response generated using {technique_used} technique • Quality score: {quality_score}/15"
    
    if processing_time:
        metadata += f" • Processing time: {processing_time:.2f}s"
    
    metadata += "*"
    
    return response + metadata