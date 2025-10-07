#!/usr/bin/env python3
"""
Model Manager for Sentence Transformers
Handles model installation, caching, and validation separately from deduplication logic
"""

import os
import sys
import logging
from pathlib import Path
from sentence_transformers import SentenceTransformer
from typing import Optional, Dict, Any

class ModelManager:
    """Manages sentence transformer models with proper caching and error handling"""
    
    def __init__(self, cache_dir: Optional[str] = None):
        # Use Windows cache path by default
        if cache_dir is None:
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            if not os.path.exists(cache_dir):
                # Try alternative Windows path
                cache_dir = os.path.join(os.getenv('LOCALAPPDATA', ''), 'huggingface', 'hub')
        
        self.cache_dir = cache_dir
        self.logger = logging.getLogger(__name__)
        
        # Set environment variables to reduce warnings and improve caching
        os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        os.environ['HF_HUB_CACHE'] = cache_dir
        os.environ['TRANSFORMERS_CACHE'] = cache_dir
    
    def get_model_cache_path(self, model_name: str) -> str:
        """Get the specific cache path for a model"""
        # Convert model name to cache-friendly path
        model_path = model_name.replace('/', '_')
        return os.path.join(self.cache_dir, model_path)
    
    def is_model_cached(self, model_name: str) -> bool:
        """Check if model files exist in cache directory"""
        cache_path = self.get_model_cache_path(model_name)
        # Check for key model files
        required_files = ['config.json', 'pytorch_model.bin', 'sentence_bert_config.json']
        return all(os.path.exists(os.path.join(cache_path, f)) for f in required_files)
    
    def is_model_available(self, model_name: str) -> bool:
        """Check if model is already downloaded and available"""
        try:
            # First check if files are cached
            if not self.is_model_cached(model_name):
                return False
            
            # Try to load the model directly - if it works, it's available
            model = SentenceTransformer(model_name)
            # Quick validation test
            test_embeddings = model.encode(["test"])
            return test_embeddings.shape[0] == 1 and test_embeddings.shape[1] > 0
        except Exception as e:
            self.logger.warning(f"Model availability check failed: {e}")
            return False
    
    def get_model(self, model_name: str, force_download: bool = False) -> Optional[SentenceTransformer]:
        """Get model with proper error handling and caching"""
        
        try:
            # Check if model is already available
            if not force_download and self.is_model_available(model_name):
                self.logger.info(f"Using cached model: {model_name}")
                return SentenceTransformer(model_name)
            
            # Model not available, need to download
            if not force_download:
                self.logger.warning(f"Model {model_name} not found in cache")
                self.logger.info("Please run the model verification script first")
                return None
            
            # Download the model
            self.logger.info(f"Downloading model: {model_name}")
            model = SentenceTransformer(model_name)
            self.logger.info(f"Model downloaded successfully: {model_name}")
            return model
            
        except Exception as e:
            self.logger.error(f"Failed to load model {model_name}: {e}")
            return None
    
    def validate_model(self, model: SentenceTransformer) -> bool:
        """Validate that the model works correctly"""
        try:
            test_texts = ["Hello world", "Hi there"]
            embeddings = model.encode(test_texts)
            return embeddings.shape[0] == 2 and embeddings.shape[1] > 0
        except Exception as e:
            self.logger.error(f"Model validation failed: {e}")
            return False
    
    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """Get information about a model"""
        try:
            model = SentenceTransformer(model_name)
            return {
                "name": model_name,
                "dimensions": model.get_sentence_embedding_dimension(),
                "max_seq_length": model.max_seq_length,
                "device": str(model.device),
                "cached": self.is_model_cached(model_name)
            }
        except Exception as e:
            return {"name": model_name, "error": str(e), "cached": False}

# Global model manager instance
model_manager = ModelManager()

def get_deduplication_model(model_name: str = "paraphrase-MiniLM-L3-v2") -> Optional[SentenceTransformer]:
    """Get the paraphrase model for deduplication with robust caching"""
    try:
        # Try to load the model directly - SentenceTransformers handles caching automatically
        print(f"Loading model {model_name}...")
        model = SentenceTransformer(model_name)
        print(f"Model loaded successfully! Dimensions: {model.get_sentence_embedding_dimension()}")
        return model
    except Exception as e:
        print(f"Failed to load paraphrase model: {e}")
        print("Please run 'python verify_model.py' to download and verify the model")
        return None
