"""
Enhanced Mistral AI Integration with Advanced Optimization Features
Implements validation, multi-perspective analysis, iterative refinement, and smart selection
"""

import httpx
import json
import time
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from tenacity import retry, wait_random_exponential, stop_after_attempt
from dataclasses import dataclass
from ai_config import ai_config
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AIResponse:
    """Structured response from AI processing"""
    content: str
    confidence_score: float
    perspective_index: int
    processing_time: float
    sources_used: List[Dict]
    validation_passed: bool
    refinement_iterations: int
    reasoning_steps: List[str] = None

@dataclass
class SourceInfo:
    """Information about a source used in AI processing"""
    title: str
    content: str
    url: str = ""
    source_type: str = "unknown"  # 'academic', 'web', 'vector'
    relevance_score: float = 0.0
    confidence_score: float = 0.0

class EnhancedMistralAI:
    """
    Enhanced Mistral AI client with advanced optimization features
    """
    
    def __init__(self, api_key: str, config=None):
        self.api_key = api_key
        self.config = config or ai_config
        self.model = "mistral-small"
        self.base_url = "https://api.mistral.ai/v1/chat/completions"
        
    def _validate_messages(self, messages: List[Dict]) -> bool:
        """Validate messages structure before sending to API"""
        if not messages:
            logger.error("Empty messages list")
            return False
        
        for i, message in enumerate(messages):
            if not isinstance(message, dict):
                logger.error(f"Message {i} is not a dictionary: {message}")
                return False
            
            if "role" not in message:
                logger.error(f"Message {i} missing 'role' field: {message}")
                return False
                
            if "content" not in message:
                logger.error(f"Message {i} missing 'content' field: {message}")
                return False
                
            if not isinstance(message["role"], str):
                logger.error(f"Message {i} role is not string: {message['role']}")
                return False
                
            if not isinstance(message["content"], str):
                logger.error(f"Message {i} content is not string: {message['content']}")
                return False
        
        return True

    def _make_api_call(self, messages: List[Dict], **kwargs) -> Dict:
        """Make a call to Mistral API with error handling"""
         # Validate messages first
        if not self._validate_messages(messages):
            raise ValueError("Invalid messages structure")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Get parameters from config
        params = self.config.get_mistral_params(kwargs.get('perspective_index', 0))
        params.update(kwargs)  # Override with any passed parameters
        
        # Ensure messages are properly formatted
        sanitized_messages = []
        for message in messages:
            sanitized_message = {
                "role": str(message.get("role", "user")),
                "content": str(message.get("content", ""))
            }
            sanitized_messages.append(sanitized_message)
        
        body = {
            "model": self.model,
            "messages": sanitized_messages,
            "stream": False,
            **params
        }
        
        # Debug logging to see what's being sent
        logger.debug(f"Sending to Mistral API: {json.dumps(body, indent=2)[:1000]}...")
        
        try:
            response = httpx.post(self.base_url, json=body, headers=headers, timeout=60)
            
            # Log the response for debugging
            logger.debug(f"Mistral API response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Mistral API error {response.status_code}: {response.text}")
                
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Mistral API HTTP error: {e}")
            logger.error(f"Response text: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Mistral API error: {e}")
            raise
    
    def _calculate_confidence_score(self, response_text: str, context: str) -> float:
        """Calculate confidence score based on response characteristics"""
        if not response_text or not context:
            return 0.0
        
        # Simple heuristic-based confidence calculation
        score = 0.5  # Base score
        
        # Length and detail factor
        if len(response_text) > 100:
            score += 0.1
        if len(response_text) > 300:
            score += 0.1
        
        # Context utilization (check if response references context)
        context_words = set(context.lower().split())
        response_words = set(response_text.lower().split())
        overlap = len(context_words.intersection(response_words))
        utilization_ratio = overlap / max(len(context_words), 1)
        score += utilization_ratio * 0.3
        
        # Uncertainty indicators (reduce confidence for uncertain language)
        uncertain_phrases = ['i think', 'maybe', 'possibly', 'might be', 'not sure', 'unclear']
        uncertainty_count = sum(1 for phrase in uncertain_phrases if phrase in response_text.lower())
        score -= uncertainty_count * 0.05
        
        return max(0.0, min(1.0, score))
    
    def _smart_context_selection(self, query: str, available_sources: List[SourceInfo]) -> List[SourceInfo]:
        """Smart selection of most relevant context sources"""
        if not self.config.use_smart_selector:
            return available_sources[:self.config.max_context_sources]
        
        # Simple relevance scoring based on keyword overlap
        query_words = set(query.lower().split())
        
        scored_sources = []
        for source in available_sources:
            # Calculate relevance score
            content_words = set((source.content + " " + source.title).lower().split())
            overlap = len(query_words.intersection(content_words))
            relevance = overlap / max(len(query_words), 1)
            
            source.relevance_score = relevance
            if relevance >= self.config.context_relevance_threshold:
                scored_sources.append(source)
        
        # Sort by relevance and apply diversity factor
        scored_sources.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Apply diversity selection (avoid too many similar sources)
        selected_sources = []
        used_domains = set()
        
        for source in scored_sources:
            if len(selected_sources) >= self.config.max_context_sources:
                break
                
            # Simple diversity check based on source type and domain
            source_signature = f"{source.source_type}_{source.url.split('/')[2] if source.url else 'unknown'}"
            
            if (len(selected_sources) < 3 or  # Always take first 3 best sources
                source_signature not in used_domains or
                len(used_domains) < self.config.max_context_sources * self.config.source_diversity_factor):
                selected_sources.append(source)
                used_domains.add(source_signature)
        
        return selected_sources
    
    def _validate_response(self, response: str, query: str, context: str) -> Tuple[bool, float]:
        """Validate AI response quality and accuracy"""
        if not self.config.use_validation:
            return True, 1.0
        
        # Calculate confidence score
        confidence = self._calculate_confidence_score(response, context)
        
        # Check if response meets validation threshold
        validation_passed = confidence >= self.config.validation_threshold
        
        # Additional validation checks
        if len(response.strip()) < 50:  # Too short
            validation_passed = False
            confidence *= 0.5
        
        if "i don't know" in response.lower() or "no information" in response.lower():
            confidence *= 0.3
        
        return validation_passed, confidence
    
    def _generate_multi_perspective_responses(self, query: str, context: str) -> List[AIResponse]:
        """Generate multiple responses from different perspectives"""
        if not self.config.use_multi_perspective:
            return []
        
        perspectives = [
            "You are a technical expert. Provide a detailed, technical analysis.",
            "You are an educator. Explain clearly for someone learning this topic.",
            "You are a researcher. Focus on accuracy and cite evidence from the context.",
            "You are a practical consultant. Focus on actionable insights and applications.",
            "You are a critical analyst. Evaluate the information objectively and note limitations."
        ]
        
        responses = []
        perspective_count = min(self.config.perspective_count, len(perspectives))
        
        for i in range(perspective_count):
            try:
                system_prompt = perspectives[i % len(perspectives)]
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
                ]
                
                start_time = time.time()
                api_response = self._make_api_call(messages, perspective_index=i)
                processing_time = time.time() - start_time
                
                content = api_response["choices"][0]["message"]["content"].strip()
                confidence = self._calculate_confidence_score(content, context)
                
                response = AIResponse(
                    content=content,
                    confidence_score=confidence,
                    perspective_index=i,
                    processing_time=processing_time,
                    sources_used=[],
                    validation_passed=True,
                    refinement_iterations=0
                )
                responses.append(response)
                
            except Exception as e:
                logger.error(f"Error generating perspective {i}: {e}")
                continue
        
        return responses
    
    def _refine_response_iteratively(self, initial_response: str, query: str, context: str) -> Tuple[str, int]:
        """Iteratively refine the response for better quality"""
        if not self.config.use_iterative_refinement:
            return initial_response, 0
        
        current_response = initial_response
        current_confidence = self._calculate_confidence_score(current_response, context)
        iterations = 0
        
        for iteration in range(self.config.max_refinement_iterations):
            try:
                # Create refinement prompt
                refinement_prompt = f"""
                Please improve and refine the following answer to make it more accurate, comprehensive, and well-structured.
                
                Original Question: {query}
                
                Current Answer: {current_response}
                
                Context for reference: {context[:1000]}...
                
                Provide an improved version that:
                1. Is more accurate and specific
                2. Better utilizes the provided context
                3. Is clearer and more comprehensive
                4. Maintains the same general structure but improves content quality
                """
                
                messages = [
                    {"role": "system", "content": "You are an expert editor improving AI responses for accuracy and clarity."},
                    {"role": "user", "content": refinement_prompt}
                ]
                
                api_response = self._make_api_call(messages)
                refined_response = api_response["choices"][0]["message"]["content"].strip()
                refined_confidence = self._calculate_confidence_score(refined_response, context)
                
                # Check if refinement improved the response
                improvement = refined_confidence - current_confidence
                if improvement >= self.config.refinement_improvement_threshold:
                    current_response = refined_response
                    current_confidence = refined_confidence
                    iterations += 1
                else:
                    break  # No significant improvement, stop refining
                    
            except Exception as e:
                logger.error(f"Error in refinement iteration {iteration}: {e}")
                break
        
        return current_response, iterations
    
    def _select_best_response(self, responses: List[AIResponse]) -> AIResponse:
        """Select the best response from multiple candidates"""
        if not responses:
            return None
        
        if len(responses) == 1:
            return responses[0]
        
        # Score responses based on multiple factors
        for response in responses:
            score = response.confidence_score * 0.6  # Base confidence weight
            
            # Length factor (prefer comprehensive but not too long responses)
            length = len(response.content)
            if 200 <= length <= 800:
                score += 0.2
            elif 100 <= length < 200 or 800 < length <= 1200:
                score += 0.1
            
            # Validation factor
            if response.validation_passed:
                score += 0.2
            
            response.confidence_score = score
        
        # Return the highest scoring response
        return max(responses, key=lambda r: r.confidence_score)
    
    def _sanitize_context(self, context: str) -> str:
        """Sanitize context to prevent JSON and API issues"""
        if not context:
            return ""
        
        # Remove problematic characters
        context = context.replace('\x00', '')  # Remove null bytes
        context = context.replace('\ufffd', '')  # Remove replacement characters
        
        # Ensure valid UTF-8
        context = context.encode('utf-8', 'ignore').decode('utf-8')
        
        # Remove excessive whitespace
        context = ' '.join(context.split())
        
        return context

    def generate_enhanced_answer(self, query: str, sources: List[Dict], search_id: str = None) -> Dict[str, Any]:
        """
        Generate enhanced AI answer with all optimization features
        Returns separated answer and sources as requested
        """
        start_time = time.time()
        
        # Convert sources to SourceInfo objects
        source_objects = []
        for source in sources:
            source_info = SourceInfo(
                title=source.get('title', 'Untitled'),
                content=source.get('content', source.get('text', source.get('snippet', ''))),
                url=source.get('url', ''),
                source_type=source.get('source_type', source.get('type', 'unknown')),
                relevance_score=source.get('relevance_score', source.get('similarity_score', 0.0))
            )
            source_objects.append(source_info)
        
        # Smart context selection
        selected_sources = self._smart_context_selection(query, source_objects)
        
        # Prepare context from selected sources
        context_parts = []
        for i, source in enumerate(selected_sources):
            sanitized_content = self._sanitize_context(source.content)
            context_parts.append(f"Source {i+1} ({source.source_type}): {source.title}\n{sanitized_content[:800]}...")
        
        context = "\n\n".join(context_parts)
        context = self._sanitize_context(context)  # Final sanitization
        
        # Track processing steps
        reasoning_steps = []
        reasoning_steps.append(f"Selected {len(selected_sources)} most relevant sources from {len(source_objects)} available")
        
        # Generate initial response
        system_prompt = (
            "You are an expert academic assistant. Provide comprehensive, accurate answers "
            "using only the context provided. If information is insufficient, clearly state what's missing. "
            "Structure your response clearly and cite relevant information from the sources."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
        ]
        
        try:
            # Generate primary response
            api_response = self._make_api_call(messages)
            primary_response = api_response["choices"][0]["message"]["content"].strip()
            reasoning_steps.append("Generated primary response using main system prompt")
            
            # Generate multi-perspective responses if enabled
            perspective_responses = []
            if self.config.use_multi_perspective:
                perspective_responses = self._generate_multi_perspective_responses(query, context)
                reasoning_steps.append(f"Generated {len(perspective_responses)} additional perspective responses")
            
            # Create primary AIResponse object
            primary_confidence = self._calculate_confidence_score(primary_response, context)
            primary_ai_response = AIResponse(
                content=primary_response,
                confidence_score=primary_confidence,
                perspective_index=0,
                processing_time=time.time() - start_time,
                sources_used=selected_sources,
                validation_passed=True,
                refinement_iterations=0
            )
            
            # Combine all responses
            all_responses = [primary_ai_response] + perspective_responses
            
            # Select best response
            best_response = self._select_best_response(all_responses)
            reasoning_steps.append(f"Selected best response from {len(all_responses)} candidates")
            
            # Validate response
            validation_passed, final_confidence = self._validate_response(
                best_response.content, query, context
            )
            best_response.validation_passed = validation_passed
            best_response.confidence_score = final_confidence
            
            if validation_passed:
                reasoning_steps.append(f"Response passed validation with confidence {final_confidence:.3f}")
            else:
                reasoning_steps.append(f"Response failed validation (confidence {final_confidence:.3f} < threshold {self.config.validation_threshold})")
            
            # Iterative refinement if enabled and validation passed
            refinement_iterations = 0
            if validation_passed and self.config.use_iterative_refinement:
                refined_content, refinement_iterations = self._refine_response_iteratively(
                    best_response.content, query, context
                )
                best_response.content = refined_content
                best_response.refinement_iterations = refinement_iterations
                reasoning_steps.append(f"Applied {refinement_iterations} refinement iterations")
            
            # Prepare final response with separated answer and sources
            total_processing_time = time.time() - start_time
            
            # Format sources for response (as requested - like web crawler cards)
            formatted_sources = []
            for source in selected_sources:
                formatted_source = {
                    'title': source.title,
                    'url': source.url,
                    'content': source.content[:300] + "..." if len(source.content) > 300 else source.content,
                    'source_type': source.source_type,
                    'relevance_score': round(source.relevance_score, 3)
                }
                formatted_sources.append(formatted_source)
            
            result = {
                # Separated AI answer (paraphrased result from sources)
                'ai_answer': {
                    'content': best_response.content,
                    'confidence_score': round(best_response.confidence_score, 3) if self.config.include_confidence_scores else None,
                    'processing_time': round(total_processing_time, 2),
                    'validation_passed': best_response.validation_passed,
                    'refinement_iterations': best_response.refinement_iterations,
                    'perspectives_considered': len(all_responses) if self.config.use_multi_perspective else 1
                },
                
                # Separated sources (for card display as requested)
                'sources': formatted_sources,
                
                # Processing metadata
                'processing_info': {
                    'total_sources_available': len(source_objects),
                    'sources_selected': len(selected_sources),
                    'optimization_features_used': {
                        'validation': self.config.use_validation,
                        'multi_perspective': self.config.use_multi_perspective,
                        'iterative_refinement': self.config.use_iterative_refinement,
                        'smart_selector': self.config.use_smart_selector
                    },
                    'reasoning_steps': reasoning_steps if self.config.include_reasoning_process else None
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error in enhanced answer generation: {e}")
            return {
                'ai_answer': {
                    'content': f"Error generating enhanced AI answer: {str(e)}",
                    'confidence_score': 0.0,
                    'processing_time': round(time.time() - start_time, 2),
                    'validation_passed': False,
                    'refinement_iterations': 0,
                    'perspectives_considered': 0
                },
                'sources': [],
                'processing_info': {
                    'total_sources_available': len(source_objects),
                    'sources_selected': 0,
                    'optimization_features_used': self.config.to_dict(),
                    'error': str(e)
                }
            }

# Backward compatibility function
def call_mistral_enhanced(question: str, context: str, sources: List[Dict] = None, search_id: str = None) -> Dict[str, Any]:
    """
    Enhanced version of call_mistral with all optimization features
    Maintains backward compatibility while providing enhanced functionality
    """
    from mistral import get_mistral_api_key
    
    try:
        api_key = get_mistral_api_key()
        enhanced_mistral = EnhancedMistralAI(api_key)
        
        # Convert context to sources format if sources not provided
        if sources is None:
            sources = [{'title': 'Context', 'content': context, 'source_type': 'context'}]
        
        return enhanced_mistral.generate_enhanced_answer(question, sources, search_id)
    
    except Exception as e:
        logger.error(f"Error in enhanced Mistral call: {e}")
        return {
            'ai_answer': {
                'content': f"❌ Enhanced Mistral AI error: {e}",
                'confidence_score': 0.0,
                'processing_time': 0.0,
                'validation_passed': False,
                'refinement_iterations': 0,
                'perspectives_considered': 0
            },
            'sources': [],
            'processing_info': {
                'error': str(e)
            }
        }
