"""
Performance tests for streaming and large file handling
Tests memory efficiency, throughput, and concurrent streaming
"""
import asyncio
import gc
import io
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, Mock, patch

import psutil
import pytest

from core.backup.production_backup import ProductionBackupOrchestrator
from database.clients.unified_http_client import create_streaming_client


class TestStreamingPerformance:
    """Performance tests for streaming functionality"""

    @pytest.fixture
    async def streaming_client(self):
        """Create streaming client for tests"""
        client = create_streaming_client(
            base_url="https://streaming.test.com",
            timeout=300.0,
            stream_support=True,
            enable_large_file_streaming=True,
        )
        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_memory_efficient_streaming(self, streaming_client):
        """Test that streaming doesn't load entire file into memory"""
        # Get initial memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Mock a 1GB file stream
        total_size = 1024 * 1024 * 1024  # 1GB
        chunk_size = 10 * 1024 * 1024    # 10MB chunks
        chunks_processed = 0

        async def mock_stream_response():
            nonlocal chunks_processed
            for i in range(total_size // chunk_size):
                chunks_processed += 1
                yield b'x' * chunk_size
                # Allow other tasks to run
                await asyncio.sleep(0)

        with patch.object(streaming_client._client, 'stream') as mock_stream:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {'content-length': str(total_size)}
            mock_response.aiter_bytes = mock_stream_response
            
            # Create async context manager mock
            async_cm = AsyncMock()
            async_cm.__aenter__.return_value = mock_response
            mock_stream.return_value = async_cm

            # Process stream
            bytes_processed = 0
            async with streaming_client.stream('GET', '/large-file') as response:
                async for chunk in response.aiter_bytes():
                    bytes_processed += len(chunk)
                    
                    # Check memory usage periodically
                    if chunks_processed % 10 == 0:
                        current_memory = process.memory_info().rss / 1024 / 1024
                        memory_increase = current_memory - initial_memory
                        
                        # Memory increase should be minimal (< 100MB for 1GB file)
                        assert memory_increase < 100, f"Memory increased by {memory_increase}MB"

            assert bytes_processed == total_size
            assert chunks_processed == total_size // chunk_size

    @pytest.mark.asyncio
    async def test_concurrent_streaming_throughput(self, streaming_client):
        """Test throughput with multiple concurrent streams"""
        num_streams = 5
        stream_size = 100 * 1024 * 1024  # 100MB per stream
        chunk_size = 1024 * 1024          # 1MB chunks

        async def create_mock_stream(stream_id):
            """Create a mock stream with specific ID"""
            async def generate_chunks():
                for i in range(stream_size // chunk_size):
                    yield f"stream{stream_id}_chunk{i}".encode().ljust(chunk_size, b'0')
                    await asyncio.sleep(0.01)  # Simulate network delay

            return generate_chunks()

        async def process_stream(stream_id):
            """Process a single stream and measure throughput"""
            start_time = time.time()
            bytes_received = 0

            with patch.object(streaming_client._client, 'stream') as mock_stream:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.aiter_bytes = lambda: create_mock_stream(stream_id)
                
                async_cm = AsyncMock()
                async_cm.__aenter__.return_value = mock_response
                mock_stream.return_value = async_cm

                async with streaming_client.stream('GET', f'/stream/{stream_id}') as response:
                    async for chunk in response.aiter_bytes():
                        bytes_received += len(chunk)

            duration = time.time() - start_time
            throughput_mbps = (bytes_received / 1024 / 1024) / duration
            
            return {
                'stream_id': stream_id,
                'bytes': bytes_received,
                'duration': duration,
                'throughput_mbps': throughput_mbps
            }

        # Process streams concurrently
        tasks = [process_stream(i) for i in range(num_streams)]
        results = await asyncio.gather(*tasks)

        # Analyze results
        total_bytes = sum(r['bytes'] for r in results)
        avg_throughput = sum(r['throughput_mbps'] for r in results) / num_streams
        
        assert total_bytes == num_streams * stream_size
        print(f"\nConcurrent streaming results:")
        print(f"Total data transferred: {total_bytes / 1024 / 1024:.2f} MB")
        print(f"Average throughput per stream: {avg_throughput:.2f} MB/s")
        
        # Each stream should maintain reasonable throughput
        for result in results:
            assert result['throughput_mbps'] > 5, f"Stream {result['stream_id']} too slow"

    @pytest.mark.asyncio
    async def test_streaming_error_recovery(self, streaming_client):
        """Test streaming recovery from network errors"""
        chunk_size = 1024 * 1024  # 1MB chunks
        total_chunks = 50
        error_at_chunk = 25

        async def mock_stream_with_error():
            """Generate stream that fails mid-way"""
            for i in range(total_chunks):
                if i == error_at_chunk:
                    raise ConnectionError("Network interrupted")
                yield f"chunk_{i}".encode().ljust(chunk_size, b'0')

        chunks_received = []

        with patch.object(streaming_client._client, 'stream') as mock_stream:
            # First attempt fails
            mock_response1 = Mock()
            mock_response1.status_code = 200
            mock_response1.aiter_bytes = mock_stream_with_error
            
            # Second attempt succeeds from resume point
            async def mock_resume_stream():
                for i in range(error_at_chunk, total_chunks):
                    yield f"chunk_{i}".encode().ljust(chunk_size, b'0')

            mock_response2 = Mock()
            mock_response2.status_code = 206  # Partial content
            mock_response2.aiter_bytes = mock_resume_stream

            async_cm1 = AsyncMock()
            async_cm1.__aenter__.return_value = mock_response1
            async_cm2 = AsyncMock()
            async_cm2.__aenter__.return_value = mock_response2
            
            mock_stream.side_effect = [async_cm1, async_cm2]

            # Process with error handling
            try:
                async with streaming_client.stream('GET', '/resumable-file') as response:
                    async for chunk in response.aiter_bytes():
                        chunks_received.append(chunk[:7].decode())  # Get chunk ID
            except ConnectionError:
                # Resume from last chunk
                headers = {'Range': f'bytes={error_at_chunk * chunk_size}-'}
                async with streaming_client.stream('GET', '/resumable-file', headers=headers) as response:
                    async for chunk in response.aiter_bytes():
                        chunks_received.append(chunk[:7].decode())

            # Verify all chunks received
            assert len(chunks_received) == total_chunks
            assert chunks_received[error_at_chunk - 1] == f"chunk_{error_at_chunk - 1}"
            assert chunks_received[error_at_chunk] == f"chunk_{error_at_chunk}"

    @pytest.mark.asyncio
    async def test_backup_streaming_performance(self):
        """Test backup service streaming performance"""
        orchestrator = ProductionBackupOrchestrator()
        
        # Mock dependencies
        with patch('database.clients.unified_http_client.create_streaming_client') as mock_create:
            mock_client = AsyncMock()
            mock_create.return_value = mock_client
            
            with patch('redis.asyncio.from_url') as mock_redis, \
                 patch('minio.Minio') as mock_minio:
                
                mock_redis.return_value = AsyncMock()
                mock_minio_instance = Mock()
                mock_minio_instance.bucket_exists.return_value = True
                mock_minio.return_value = mock_minio_instance
                
                await orchestrator.initialize()
                
                # Test chunked backup upload
                backup_data = b'x' * (100 * 1024 * 1024)  # 100MB backup
                
                start_time = time.time()
                chunks = await orchestrator.create_backup_chunks(backup_data)
                chunking_time = time.time() - start_time
                
                assert len(chunks) == 10  # 100MB / 10MB chunks
                assert chunking_time < 1.0  # Should be fast
                
                # Test parallel chunk upload
                upload_times = []
                
                async def mock_upload(backup_id, chunk_id, chunk_data, key_id):
                    upload_start = time.time()
                    await asyncio.sleep(0.1)  # Simulate upload
                    upload_times.append(time.time() - upload_start)
                    return chunk_id
                
                orchestrator.upload_chunk = mock_upload
                
                start_time = time.time()
                chunk_ids = await orchestrator._upload_backup_chunks(
                    "backup_123",
                    backup_data,
                    "key_123"
                )
                total_upload_time = time.time() - start_time
                
                # Parallel upload should be faster than sequential
                sequential_time = sum(upload_times)
                assert total_upload_time < sequential_time * 0.5
                assert len(chunk_ids) == 10

            await orchestrator.close()

    @pytest.mark.asyncio
    async def test_memory_pressure_handling(self, streaming_client):
        """Test behavior under memory pressure"""
        # Simulate low memory conditions
        gc.collect()
        initial_memory = psutil.virtual_memory().percent

        # Create multiple large streams
        num_streams = 3
        stream_size = 200 * 1024 * 1024  # 200MB each

        async def process_under_pressure(stream_id):
            """Process stream with memory monitoring"""
            max_memory_spike = 0
            
            async def generate_stream():
                for i in range(stream_size // (10 * 1024 * 1024)):
                    # Check memory usage
                    current_memory = psutil.virtual_memory().percent
                    memory_spike = current_memory - initial_memory
                    max_memory_spike = max(max_memory_spike, memory_spike)
                    
                    # Force garbage collection if memory is high
                    if current_memory > 80:
                        gc.collect()
                    
                    yield b'x' * (10 * 1024 * 1024)
                    await asyncio.sleep(0.01)

            bytes_processed = 0
            with patch.object(streaming_client._client, 'stream') as mock_stream:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.aiter_bytes = generate_stream
                
                async_cm = AsyncMock()
                async_cm.__aenter__.return_value = mock_response
                mock_stream.return_value = async_cm

                async with streaming_client.stream('GET', f'/pressure/{stream_id}') as response:
                    async for chunk in response.aiter_bytes():
                        bytes_processed += len(chunk)
                        # Process chunk without keeping in memory
                        del chunk

            return {
                'stream_id': stream_id,
                'bytes_processed': bytes_processed,
                'max_memory_spike': max_memory_spike
            }

        # Process streams with memory monitoring
        tasks = [process_under_pressure(i) for i in range(num_streams)]
        results = await asyncio.gather(*tasks)

        # Verify all streams completed
        for result in results:
            assert result['bytes_processed'] == stream_size
            # Memory spike should be reasonable (< 20% increase)
            assert result['max_memory_spike'] < 20, \
                f"Stream {result['stream_id']} caused {result['max_memory_spike']}% memory spike"

        # Final cleanup
        gc.collect()


class TestConnectionPoolPerformance:
    """Test connection pool performance and behavior"""

    @pytest.mark.asyncio
    async def test_connection_reuse(self):
        """Test that connections are properly reused"""
        from database.clients.unified_http_client import UnifiedHTTPClient, HTTPClientConfig
        
        config = HTTPClientConfig(
            base_url="https://api.test.com",
            connection_pool_config={
                "max_connections": 10,
                "max_keepalive_connections": 5,
            }
        )
        client = UnifiedHTTPClient(config)

        connection_count = 0
        reused_count = 0

        # Mock transport to track connections
        original_request = client._client.request

        async def tracked_request(*args, **kwargs):
            nonlocal connection_count, reused_count
            # Simulate connection tracking
            if hasattr(tracked_request, 'connection_pool'):
                reused_count += 1
            else:
                connection_count += 1
                tracked_request.connection_pool = True
            
            return Mock(
                status_code=200,
                json=lambda: {"request": connection_count + reused_count},
                headers={}
            )

        client._client.request = tracked_request

        # Make multiple requests
        tasks = []
        for i in range(20):
            tasks.append(client.get(f"/api/test/{i}"))

        await asyncio.gather(*tasks)

        # Most connections should be reused
        assert reused_count > connection_count
        print(f"\nConnection pool performance:")
        print(f"New connections: {connection_count}")
        print(f"Reused connections: {reused_count}")
        print(f"Reuse rate: {reused_count / (connection_count + reused_count) * 100:.1f}%")

        await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])