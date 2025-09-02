"""
AI Configuration and Optimization Settings
This module provides a centralized configuration system for AI improvements
including validation, multi-perspective analysis, iterative refinement, and smart selection.
"""

class AIOptimizationConfig:
    """
    Configuration object for AI optimization settings
    Allows easy toggling of advanced features without UI changes
    """
    
    def __init__(self):
        # Advanced AI Techniques (set to True for better quality)
        self.use_validation = True
        self.use_multi_perspective = True
        self.use_iterative_refinement = True
        self.use_smart_selector = True
        
        # Token and attempt limits (increased for better results)
        self.max_tokens = 2048  # Increased from 512
        self.max_techniques_to_try = 5  # Increased from 1 (default retry)
        
        # Performance vs Quality trade-offs
        self.enable_fast_mode = False  # Set to True for faster responses
        self.enable_detailed_sources = True  # Separate sources from AI answer
        
        # Multi-perspective settings
        self.perspective_count = 3  # Number of different perspectives to consider
        self.perspective_temperature_range = (0.3, 0.7)  # Temperature variation for perspectives
        
        # Validation settings
        self.validation_threshold = 0.7  # Minimum confidence threshold
        self.max_validation_attempts = 3
        
        # Iterative refinement settings
        self.max_refinement_iterations = 2
        self.refinement_improvement_threshold = 0.1  # Minimum improvement to continue
        
        # Smart selector settings
        self.context_relevance_threshold = 0.6
        self.max_context_sources = 15  # Increased from default
        self.source_diversity_factor = 0.3  # Balance between relevance and diversity
        
        # Response formatting
        self.separate_answer_and_sources = True  # Split AI answer from sources
        self.include_confidence_scores = True
        self.include_reasoning_process = False  # Set to True for debugging
        
    def to_dict(self):
        """Convert configuration to dictionary for easy serialization"""
        return {
            'use_validation': self.use_validation,
            'use_multi_perspective': self.use_multi_perspective,
            'use_iterative_refinement': self.use_iterative_refinement,
            'use_smart_selector': self.use_smart_selector,
            'max_tokens': self.max_tokens,
            'max_techniques_to_try': self.max_techniques_to_try,
            'enable_fast_mode': self.enable_fast_mode,
            'enable_detailed_sources': self.enable_detailed_sources,
            'perspective_count': self.perspective_count,
            'perspective_temperature_range': self.perspective_temperature_range,
            'validation_threshold': self.validation_threshold,
            'max_validation_attempts': self.max_validation_attempts,
            'max_refinement_iterations': self.max_refinement_iterations,
            'refinement_improvement_threshold': self.refinement_improvement_threshold,
            'context_relevance_threshold': self.context_relevance_threshold,
            'max_context_sources': self.max_context_sources,
            'source_diversity_factor': self.source_diversity_factor,
            'separate_answer_and_sources': self.separate_answer_and_sources,
            'include_confidence_scores': self.include_confidence_scores,
            'include_reasoning_process': self.include_reasoning_process
        }
    
    def get_mistral_params(self, perspective_index=0):
        """Get Mistral API parameters based on current config and perspective"""
        base_temp = 0.4
        
        if self.use_multi_perspective and perspective_index > 0:
            # Vary temperature for different perspectives
            temp_min, temp_max = self.perspective_temperature_range
            temp_range = temp_max - temp_min
            temperature = temp_min + (temp_range * (perspective_index / max(1, self.perspective_count - 1)))
        else:
            temperature = base_temp
        
        return {
            'temperature': temperature,
            'max_tokens': self.max_tokens,
            'top_p': 0.9 if self.use_smart_selector else 1.0,
            'frequency_penalty': 0.1 if self.use_iterative_refinement else 0.0
        }

# Global configuration instance
ai_config = AIOptimizationConfig()

# Preset configurations for different use cases
class AIPresets:
    """Predefined configuration presets for different scenarios"""
    
    @staticmethod
    def fast_mode():
        """Fast responses, lower quality"""
        config = AIOptimizationConfig()
        config.use_validation = False
        config.use_multi_perspective = False
        config.use_iterative_refinement = False
        config.use_smart_selector = True
        config.max_tokens = 1024
        config.max_techniques_to_try = 1
        config.enable_fast_mode = True
        return config
    
    @staticmethod
    def balanced_mode():
        """Balanced speed and quality (default)"""
        return AIOptimizationConfig()
    
    @staticmethod
    def quality_mode():
        """Maximum quality, slower responses"""
        config = AIOptimizationConfig()
        config.use_validation = True
        config.use_multi_perspective = True
        config.use_iterative_refinement = True
        config.use_smart_selector = True
        config.max_tokens = 4096
        config.max_techniques_to_try = 8
        config.perspective_count = 5
        config.max_refinement_iterations = 3
        config.max_context_sources = 25
        config.include_reasoning_process = True
        return config
    
    @staticmethod
    def research_mode():
        """Optimized for academic research"""
        config = AIOptimizationConfig()
        config.use_validation = True
        config.use_multi_perspective = True
        config.use_iterative_refinement = True
        config.use_smart_selector = True
        config.max_tokens = 3072
        config.max_techniques_to_try = 6
        config.validation_threshold = 0.8
        config.context_relevance_threshold = 0.7
        config.source_diversity_factor = 0.5
        config.include_confidence_scores = True
        return config

def get_config_preset(preset_name="balanced"):
    """Get a configuration preset by name"""
    presets = {
        'fast': AIPresets.fast_mode,
        'balanced': AIPresets.balanced_mode,
        'quality': AIPresets.quality_mode,
        'research': AIPresets.research_mode
    }
    
    if preset_name.lower() in presets:
        return presets[preset_name.lower()]()
    else:
        return AIPresets.balanced_mode()
