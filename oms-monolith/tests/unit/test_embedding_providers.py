"""
Unit tests for vector embedding providers.
Tests all providers including the newly added Anthropic provider.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from core.embeddings.providers import (
    EmbeddingProvider,
    EmbeddingConfig,
    EmbeddingProviderFactory,
    OpenAIEmbeddingProvider,
    CohereEmbeddingProvider,
    HuggingFaceEmbeddingProvider,
    LocalSentenceTransformersProvider,
    AzureOpenAIEmbeddingProvider,
    GoogleVertexEmbeddingProvider,
    AnthropicEmbeddingProvider
)


@pytest.fixture
def sample_texts():
    """Sample texts for testing."""
    return [
        "Hello world",
        "Vector embeddings are useful for semantic search",
        "Machine learning and natural language processing"
    ]


@pytest.fixture
def sample_embedding():
    """Sample embedding vector."""
    return [0.1, 0.2, 0.3, 0.4, 0.5]


class TestEmbeddingProviderFactory:
    """Test the embedding provider factory."""
    
    def test_get_default_configs(self):
        """Test getting default configurations."""
        configs = EmbeddingProviderFactory.get_default_configs()
        
        assert EmbeddingProvider.OPENAI in configs
        assert EmbeddingProvider.COHERE in configs
        assert EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS in configs
        assert EmbeddingProvider.ANTHROPIC_CLAUDE in configs
        
        # Check OpenAI config
        openai_config = configs[EmbeddingProvider.OPENAI]
        assert openai_config.model_name == "text-embedding-3-large"
        assert openai_config.dimensions == 3072
        
        # Check Anthropic config
        anthropic_config = configs[EmbeddingProvider.ANTHROPIC_CLAUDE]
        assert anthropic_config.model_name == "claude-3-haiku-20240307"
        assert anthropic_config.dimensions == 384
        assert anthropic_config.batch_size == 20
    
    def test_create_provider_success(self):
        """Test successful provider creation."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS,
            model_name="test-model",
            api_key="test-key"
        )
        
        with patch('core.embeddings.providers.SentenceTransformer'):
            provider = EmbeddingProviderFactory.create_provider(config)
            assert isinstance(provider, LocalSentenceTransformersProvider)
            assert provider.config == config
    
    def test_create_provider_unsupported(self):
        """Test creation with unsupported provider."""
        # Create a mock enum value that's not in the factory
        class MockProvider:
            value = "unsupported_provider"
        
        config = EmbeddingConfig(
            provider=MockProvider(),
            model_name="test-model"
        )
        
        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            EmbeddingProviderFactory.create_provider(config)


class TestOpenAIEmbeddingProvider:
    """Test OpenAI embedding provider."""
    
    @pytest.mark.asyncio
    async def test_create_embeddings_success(self, sample_texts, sample_embedding):
        """Test successful embedding creation."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.OPENAI,
            model_name="text-embedding-3-large",
            api_key="test-key"
        )
        
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=sample_embedding) for _ in sample_texts]
        mock_client.embeddings.create.return_value = mock_response
        
        with patch('openai.AsyncOpenAI') as mock_openai:
            mock_openai.return_value = mock_client
            
            provider = OpenAIEmbeddingProvider(config)
            embeddings = await provider.create_embeddings(sample_texts)
            
            assert len(embeddings) == len(sample_texts)
            assert all(emb == sample_embedding for emb in embeddings)
            mock_client.embeddings.create.assert_called_once_with(
                input=sample_texts,
                model=config.model_name
            )
    
    @pytest.mark.asyncio
    async def test_create_single_embedding(self, sample_embedding):
        """Test single embedding creation."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.OPENAI,
            model_name="text-embedding-3-large",
            api_key="test-key"
        )
        
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=sample_embedding)]
        mock_client.embeddings.create.return_value = mock_response
        
        with patch('openai.AsyncOpenAI') as mock_openai:
            mock_openai.return_value = mock_client
            
            provider = OpenAIEmbeddingProvider(config)
            embedding = await provider.create_single_embedding("test text")
            
            assert embedding == sample_embedding


class TestAnthropicEmbeddingProvider:
    """Test Anthropic embedding provider."""
    
    @pytest.mark.asyncio
    async def test_create_embeddings_success(self, sample_texts):
        """Test successful embedding creation with Anthropic."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.ANTHROPIC_CLAUDE,
            model_name="claude-3-haiku-20240307",
            api_key="test-key",
            dimensions=384
        )
        
        # Mock Anthropic client
        mock_client = AsyncMock()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="0.1 0.2 0.3 0.4 0.5")]
        mock_client.messages.create.return_value = mock_message
        
        with patch('anthropic.AsyncAnthropic') as mock_anthropic:
            mock_anthropic.return_value = mock_client
            
            provider = AnthropicEmbeddingProvider(config)
            embeddings = await provider.create_embeddings(sample_texts)
            
            assert len(embeddings) == len(sample_texts)
            assert all(len(emb) == config.dimensions for emb in embeddings)
            assert mock_client.messages.create.call_count == len(sample_texts)
    
    @pytest.mark.asyncio
    async def test_create_embeddings_fallback(self, sample_texts):
        """Test fallback to zero vector on API failure."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.ANTHROPIC_CLAUDE,
            model_name="claude-3-haiku-20240307",
            api_key="test-key",
            dimensions=10
        )
        
        # Mock Anthropic client to raise exception
        mock_client = AsyncMock()
        mock_client.messages.create.side_effect = Exception("API Error")
        
        with patch('anthropic.AsyncAnthropic') as mock_anthropic:
            mock_anthropic.return_value = mock_client
            
            provider = AnthropicEmbeddingProvider(config)
            embeddings = await provider.create_embeddings(sample_texts)
            
            assert len(embeddings) == len(sample_texts)
            # Should return zero vectors
            assert all(emb == [0.0] * config.dimensions for emb in embeddings)
    
    def test_initialization_missing_package(self):
        """Test initialization failure when anthropic package is missing."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.ANTHROPIC_CLAUDE,
            model_name="claude-3-haiku-20240307",
            api_key="test-key"
        )
        
        with patch('anthropic.AsyncAnthropic', side_effect=ImportError("No module named 'anthropic'")):
            with pytest.raises(ImportError, match="anthropic package required"):
                AnthropicEmbeddingProvider(config)


class TestLocalSentenceTransformersProvider:
    """Test local Sentence Transformers provider."""
    
    @pytest.mark.asyncio
    async def test_create_embeddings_success(self, sample_texts):
        """Test successful embedding creation with local model."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS,
            model_name="all-MiniLM-L6-v2"
        )
        
        # Mock SentenceTransformer
        mock_model = MagicMock()
        mock_embeddings = [[0.1, 0.2, 0.3] for _ in sample_texts]
        mock_model.encode.return_value = MagicMock(tolist=lambda: mock_embeddings)
        
        with patch('core.embeddings.providers.SentenceTransformer') as mock_st:
            mock_st.return_value = mock_model
            
            provider = LocalSentenceTransformersProvider(config)
            
            # Mock asyncio.get_event_loop().run_in_executor
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=MagicMock(tolist=lambda: mock_embeddings))
                mock_loop.return_value.run_in_executor = mock_executor
                
                embeddings = await provider.create_embeddings(sample_texts)
                
                assert len(embeddings) == len(sample_texts)
                mock_executor.assert_called_once()


class TestGoogleVertexEmbeddingProvider:
    """Test Google Vertex AI embedding provider."""
    
    @pytest.mark.asyncio
    async def test_create_embeddings_success(self, sample_texts):
        """Test successful embedding creation with Google Vertex."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.GOOGLE_VERTEX,
            model_name="textembedding-gecko@003"
        )
        
        # Mock the threaded execution
        mock_embeddings = [[0.1, 0.2, 0.3] for _ in sample_texts]
        
        with patch('google.cloud.aiplatform') as mock_aiplatform:
            mock_aiplatform.init.return_value = None
            
            provider = GoogleVertexEmbeddingProvider(config)
            
            # Mock asyncio.get_event_loop().run_in_executor
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_executor = AsyncMock(return_value=mock_embeddings)
                mock_loop.return_value.run_in_executor = mock_executor
                
                embeddings = await provider.create_embeddings(sample_texts)
                
                assert len(embeddings) == len(sample_texts)
                mock_executor.assert_called_once()


class TestBatchingFunctionality:
    """Test batching functionality in providers."""
    
    @pytest.mark.asyncio
    async def test_create_embeddings_with_batching(self):
        """Test automatic batching for large inputs."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS,
            model_name="test-model",
            batch_size=2  # Small batch size for testing
        )
        
        # Create many texts to trigger batching
        texts = [f"Text {i}" for i in range(5)]
        
        mock_model = MagicMock()
        
        with patch('core.embeddings.providers.SentenceTransformer') as mock_st:
            mock_st.return_value = mock_model
            
            provider = LocalSentenceTransformersProvider(config)
            
            # Mock the batching behavior
            with patch.object(provider, 'create_embeddings') as mock_create:
                mock_create.side_effect = [
                    [[0.1, 0.2], [0.3, 0.4]],  # First batch
                    [[0.5, 0.6], [0.7, 0.8]],  # Second batch  
                    [[0.9, 1.0]]                # Third batch
                ]
                
                embeddings = await provider.create_embeddings_with_batching(texts)
                
                assert len(embeddings) == len(texts)
                assert mock_create.call_count == 3  # Should be called 3 times for 3 batches
    
    def test_split_into_batches(self):
        """Test batch splitting functionality."""
        config = EmbeddingConfig(
            provider=EmbeddingProvider.OPENAI,
            model_name="test-model",
            batch_size=3
        )
        
        with patch('openai.AsyncOpenAI'):
            provider = OpenAIEmbeddingProvider(config)
            
            texts = [f"Text {i}" for i in range(7)]
            batches = provider._split_into_batches(texts)
            
            assert len(batches) == 3
            assert len(batches[0]) == 3
            assert len(batches[1]) == 3
            assert len(batches[2]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])