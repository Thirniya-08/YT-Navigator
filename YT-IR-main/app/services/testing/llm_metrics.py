"""LLM testing framework with comprehensive metrics collection."""

import asyncio
import json
import time
import traceback
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime

import structlog
from django.test import TestCase
from asgiref.sync import sync_to_async

from app.services.agent.main_graph import get_graph_instance
from app.models import Video, VideoChunk
from app.schemas import AgentOutput

logger = structlog.get_logger(__name__)


@dataclass
class LLMMetrics:
    """Metrics for LLM performance evaluation."""
    
    # Performance metrics
    response_time: float
    token_count: Optional[int]
    success_rate: float
    error_count: int
    
    # Quality metrics
    relevance_score: float
    completeness_score: float
    accuracy_score: float
    
    # Content metrics
    has_videos: bool
    video_count: int
    response_length: int
    
    # Technical metrics
    tool_calls_count: int
    tool_execution_time: float
    retry_count: int
    
    # Metadata
    timestamp: str
    query_type: str
    model_name: str


@dataclass
class TestCase:
    """Test case for LLM evaluation."""
    
    query: str
    expected_type: str  # 'video_search', 'general_query', 'not_relevant'
    expected_min_videos: int = 0
    expected_max_videos: int = 10
    expected_keywords: List[str] = None
    difficulty: str = 'medium'  # 'easy', 'medium', 'hard'


class LLMMetricsCollector:
    """Collect and analyze LLM performance metrics."""
    
    def __init__(self):
        self.metrics_history: List[LLMMetrics] = []
        self.test_results: Dict[str, Any] = {}
    
    async def run_test_suite(self, test_cases: List[TestCase]) -> Dict[str, Any]:
        """Run comprehensive test suite with metrics collection."""
        
        logger.info("Starting LLM test suite", test_count=len(test_cases))
        
        results = {
            'total_tests': len(test_cases),
            'passed_tests': 0,
            'failed_tests': 0,
            'average_response_time': 0,
            'success_rate': 0,
            'metrics': [],
            'detailed_results': []
        }
        
        total_response_time = 0
        successful_tests = 0
        
        for i, test_case in enumerate(test_cases):
            logger.info(f"Running test {i+1}/{len(test_cases)}", query=test_case.query[:50])
            
            try:
                metrics = await self._run_single_test(test_case)
                results['metrics'].append(asdict(metrics))
                results['detailed_results'].append({
                    'query': test_case.query,
                    'success': metrics.success_rate > 0,
                    'response_time': metrics.response_time,
                    'error_count': metrics.error_count,
                    'video_count': metrics.video_count
                })
                
                total_response_time += metrics.response_time
                if metrics.success_rate > 0:
                    successful_tests += 1
                    results['passed_tests'] += 1
                else:
                    results['failed_tests'] += 1
                    
            except Exception as e:
                logger.error("Test failed", test_case=test_case.query, error=str(e))
                results['failed_tests'] += 1
                results['detailed_results'].append({
                    'query': test_case.query,
                    'success': False,
                    'error': str(e),
                    'response_time': 0
                })
        
        # Calculate aggregates
        if len(test_cases) > 0:
            results['average_response_time'] = total_response_time / len(test_cases)
            results['success_rate'] = successful_tests / len(test_cases)
        
        logger.info("Test suite completed", 
                   passed=results['passed_tests'],
                   failed=results['failed_tests'],
                   success_rate=results['success_rate'])
        
        return results
    
    async def _run_single_test(self, test_case: TestCase) -> LLMMetrics:
        """Run a single test case and collect metrics."""
        
        start_time = time.time()
        error_count = 0
        retry_count = 0
        tool_calls_count = 0
        tool_execution_time = 0
        
        try:
            # Get graph instance
            graph = await get_graph_instance()
            
            # Mock user and channel for testing
            from unittest.mock import Mock
            mock_user = Mock()
            mock_user.id = "test_user"
            mock_channel = None
            
            # Execute with retry logic
            for attempt in range(3):  # Max 3 attempts
                try:
                    response = await asyncio.wait_for(
                        graph.process_message(
                            message=test_case.query,
                            channel=mock_channel,
                            user=mock_user
                        ),
                        timeout=60  # 60 second timeout
                    )
                    break
                except Exception as e:
                    retry_count += 1
                    if attempt == 2:  # Last attempt
                        raise e
                    await asyncio.sleep(1)  # Wait before retry
            
            response_time = time.time() - start_time
            
            # Parse response
            try:
                agent_output = AgentOutput.model_validate_json(response)
                video_count = len(agent_output.videos)
                has_videos = video_count > 0
                response_length = len(agent_output.placeholder)
            except Exception:
                video_count = 0
                has_videos = False
                response_length = len(response) if response else 0
            
            # Calculate quality scores
            relevance_score = self._calculate_relevance(test_case, response)
            completeness_score = self._calculate_completeness(test_case, response)
            accuracy_score = self._calculate_accuracy(test_case, response)
            
            metrics = LLMMetrics(
                response_time=response_time,
                token_count=None,  # Could be extracted from API response
                success_rate=1.0 if response else 0.0,
                error_count=error_count,
                relevance_score=relevance_score,
                completeness_score=completeness_score,
                accuracy_score=accuracy_score,
                has_videos=has_videos,
                video_count=video_count,
                response_length=response_length,
                tool_calls_count=tool_calls_count,
                tool_execution_time=tool_execution_time,
                retry_count=retry_count,
                timestamp=datetime.now().isoformat(),
                query_type=test_case.expected_type,
                model_name="llama-3.1-8b-instant"
            )
            
            self.metrics_history.append(metrics)
            return metrics
            
        except Exception as e:
            logger.error("Test execution failed", error=str(e), traceback=traceback.format_exc())
            
            metrics = LLMMetrics(
                response_time=time.time() - start_time,
                token_count=None,
                success_rate=0.0,
                error_count=1,
                relevance_score=0.0,
                completeness_score=0.0,
                accuracy_score=0.0,
                has_videos=False,
                video_count=0,
                response_length=0,
                tool_calls_count=0,
                tool_execution_time=0,
                retry_count=retry_count,
                timestamp=datetime.now().isoformat(),
                query_type=test_case.expected_type,
                model_name="llama-3.1-8b-instant"
            )
            
            self.metrics_history.append(metrics)
            return metrics
    
    def _calculate_relevance(self, test_case: TestCase, response: str) -> float:
        """Calculate relevance score based on expected keywords and content."""
        if not response:
            return 0.0
        
        score = 0.5  # Base score
        
        if test_case.expected_keywords:
            response_lower = response.lower()
            keyword_matches = sum(1 for kw in test_case.expected_keywords 
                                 if kw.lower() in response_lower)
            if keyword_matches > 0:
                score += (keyword_matches / len(test_case.expected_keywords)) * 0.5
        
        # Check if response type matches expectation
        if test_case.expected_type == 'video_search' and 'videos' in response.lower():
            score += 0.2
        elif test_case.expected_type == 'general_query' and len(response) > 50:
            score += 0.2
        
        return min(score, 1.0)
    
    def _calculate_completeness(self, test_case: TestCase, response: str) -> float:
        """Calculate completeness score based on response thoroughness."""
        if not response:
            return 0.0
        
        score = 0.3  # Base score for any response
        
        # Length-based scoring
        if len(response) > 100:
            score += 0.3
        elif len(response) > 50:
            score += 0.2
        
        # Structure-based scoring
        if any(marker in response.lower() for marker in ['video', 'moment', 'point', 'key']):
            score += 0.2
        
        # Video count expectations
        try:
            agent_output = AgentOutput.model_validate_json(response)
            video_count = len(agent_output.videos)
            
            if test_case.expected_min_videos <= video_count <= test_case.expected_max_videos:
                score += 0.2
            elif video_count > 0:
                score += 0.1
        except Exception:
            pass
        
        return min(score, 1.0)
    
    def _calculate_accuracy(self, test_case: TestCase, response: str) -> float:
        """Calculate accuracy score based on factual correctness."""
        # This is a simplified accuracy calculation
        # In practice, you might use more sophisticated methods
        
        if not response:
            return 0.0
        
        score = 0.5  # Base score
        
        # Check for common error patterns
        error_indicators = ['i cannot', 'i don\'t know', 'error', 'failed']
        if any(indicator in response.lower() for indicator in error_indicators):
            score -= 0.3
        
        # Check for successful response patterns
        success_indicators = ['found', 'here are', 'video', 'moment', 'key point']
        if any(indicator in response.lower() for indicator in success_indicators):
            score += 0.3
        
        return max(0.0, min(score, 1.0))
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate comprehensive test report."""
        
        report = f"""
# LLM Performance Test Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- Total Tests: {results['total_tests']}
- Passed: {results['passed_tests']}
- Failed: {results['failed_tests']}
- Success Rate: {results['success_rate']:.2%}
- Average Response Time: {results['average_response_time']:.2f}s

## Performance Metrics
"""
        
        if results['metrics']:
            avg_relevance = sum(m['relevance_score'] for m in results['metrics']) / len(results['metrics'])
            avg_completeness = sum(m['completeness_score'] for m in results['metrics']) / len(results['metrics'])
            avg_accuracy = sum(m['accuracy_score'] for m in results['metrics']) / len(results['metrics'])
            avg_video_count = sum(m['video_count'] for m in results['metrics']) / len(results['metrics'])
            
            report += f"""
- Average Relevance Score: {avg_relevance:.2f}
- Average Completeness Score: {avg_completeness:.2f}
- Average Accuracy Score: {avg_accuracy:.2f}
- Average Video Count: {avg_video_count:.1f}
"""
        
        report += "\n## Detailed Results\n"
        for i, result in enumerate(results['detailed_results'], 1):
            status = "PASS" if result['success'] else "FAIL"
            report += f"""
{i}. {result['query'][:50]}...
   Status: {status}
   Response Time: {result['response_time']:.2f}s
   Videos Found: {result.get('video_count', 0)}
"""
            if 'error' in result:
                report += f"   Error: {result['error']}\n"
        
        return report
    
    def save_metrics(self, filename: str = None):
        """Save metrics to JSON file."""
        if filename is None:
            filename = f"llm_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'metrics_history': [asdict(m) for m in self.metrics_history],
            'summary': self._generate_summary()
        }
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info("Metrics saved", filename=filename)
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics from metrics history."""
        if not self.metrics_history:
            return {}
        
        return {
            'total_tests': len(self.metrics_history),
            'avg_response_time': sum(m.response_time for m in self.metrics_history) / len(self.metrics_history),
            'avg_relevance': sum(m.relevance_score for m in self.metrics_history) / len(self.metrics_history),
            'avg_completeness': sum(m.completeness_score for m in self.metrics_history) / len(self.metrics_history),
            'avg_accuracy': sum(m.accuracy_score for m in self.metrics_history) / len(self.metrics_history),
            'success_rate': sum(m.success_rate for m in self.metrics_history) / len(self.metrics_history),
            'total_errors': sum(m.error_count for m in self.metrics_history)
        }


# Predefined test cases
DEFAULT_TEST_CASES = [
    TestCase(
        query="Best moments of the video",
        expected_type="video_search",
        expected_min_videos=1,
        expected_max_videos=5,
        expected_keywords=["moment", "best", "video"],
        difficulty="easy"
    ),
    TestCase(
        query="Key points discussed",
        expected_type="video_search", 
        expected_min_videos=1,
        expected_max_videos=3,
        expected_keywords=["key", "point", "discussed"],
        difficulty="medium"
    ),
    TestCase(
        query="What is the weather today?",
        expected_type="not_relevant",
        expected_min_videos=0,
        expected_max_videos=0,
        expected_keywords=[],
        difficulty="easy"
    ),
    TestCase(
        query="Show me videos about machine learning",
        expected_type="video_search",
        expected_min_videos=1,
        expected_max_videos=10,
        expected_keywords=["machine learning", "video"],
        difficulty="medium"
    ),
    TestCase(
        query="Summarize the main topics",
        expected_type="video_search",
        expected_min_videos=1,
        expected_max_videos=5,
        expected_keywords=["summarize", "main", "topic"],
        difficulty="hard"
    )
]
