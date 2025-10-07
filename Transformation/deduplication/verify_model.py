#!/usr/bin/env python3
"""
Model Verification Script
Downloads and verifies the Sentence Transformer model for deduplication
Run this script once to ensure the model is properly cached
"""

import os
import sys
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

def verify_model():
    """Download and verify the paraphrase model"""
    model_name = "paraphrase-MiniLM-L3-v2"
    
    print("=" * 60)
    print("MODEL VERIFICATION SCRIPT")
    print("=" * 60)
    print(f"Model: {model_name}")
    print("Purpose: Download and verify Sentence Transformer model for deduplication")
    print("=" * 60)
    
    try:
        # Step 1: Download/load the model
        print("\nStep 1: Loading model...")
        print("This may take a few minutes on first run...")
        
        model = SentenceTransformer(model_name)
        
        # Step 2: Get model information
        print("\nStep 2: Model Information")
        print("-" * 30)
        print(f"Model Name: {model_name}")
        print(f"Embedding Dimensions: {model.get_sentence_embedding_dimension()}")
        print(f"Max Sequence Length: {model.max_seq_length}")
        print(f"Device: {model.device}")
        
        # Step 3: Test the model
        print("\nStep 3: Testing model functionality...")
        print("-" * 30)
        
        # Test case 1: Basic encoding
        test_texts = ["Hello world", "Hi there", "Goodbye"]
        embeddings = model.encode(test_texts)
        print(f"✓ Basic encoding test: {embeddings.shape}")
        
        # Test case 2: Similarity calculation
        text1 = "The Supreme Court ruled on constitutional rights"
        text2 = "The highest court decided on fundamental rights"
        text3 = "The weather is sunny today"
        
        test_embeddings = model.encode([text1, text2, text3])
        
        # Calculate similarities
        similarity_1_2 = cosine_similarity([test_embeddings[0]], [test_embeddings[1]])[0][0]
        similarity_1_3 = cosine_similarity([test_embeddings[0]], [test_embeddings[2]])[0][0]
        
        print(f"✓ Similarity test:")
        print(f"  Similar texts similarity: {similarity_1_2:.3f}")
        print(f"  Different texts similarity: {similarity_1_3:.3f}")
        
        # Test case 3: Threshold test
        threshold = 0.85
        is_similar = similarity_1_2 >= threshold
        print(f"✓ Threshold test (0.85): {'PASS' if is_similar else 'FAIL'}")
        
        # Step 4: Verify cache location
        print("\nStep 4: Cache verification...")
        print("-" * 30)
        
        # Get cache directory
        cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
        if not os.path.exists(cache_dir):
            cache_dir = os.path.join(os.getenv('LOCALAPPDATA', ''), 'huggingface', 'hub')
        
        print(f"Cache directory: {cache_dir}")
        
        # Check if model files exist
        model_cache_path = os.path.join(cache_dir, "sentence-transformers_paraphrase-MiniLM-L3-v2")
        if os.path.exists(model_cache_path):
            print("✓ Model files found in cache")
            print(f"Cache path: {model_cache_path}")
        else:
            print("⚠ Model files not found in expected cache location")
        
        print("\n" + "=" * 60)
        print("✅ MODEL VERIFICATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("The model is now ready for deduplication.")
        print("You can run the deduplication system without any downloads.")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ MODEL VERIFICATION FAILED: {e}")
        print("=" * 60)
        print("Troubleshooting:")
        print("1. Check your internet connection")
        print("2. Ensure you have sufficient disk space")
        print("3. Try running the script again")
        print("4. Check if the model name is correct")
        print("=" * 60)
        return False

def main():
    """Main function"""
    print("Starting model verification...")
    success = verify_model()
    
    if success:
        print("\n🎉 Model verification completed successfully!")
        print("You can now use the deduplication system.")
    else:
        print("\n💥 Model verification failed!")
        print("Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
