"""Django management command to run LLM metrics testing."""

import asyncio
import os
import sys
from django.core.management.base import BaseCommand
from django.conf import settings

from app.services.testing.llm_metrics import LLMMetricsCollector, DEFAULT_TEST_CASES


class Command(BaseCommand):
    help = 'Run LLM performance tests with comprehensive metrics collection'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='llm_test_report.txt',
            help='Output file for test report'
        )
        parser.add_argument(
            '--metrics-file',
            type=str,
            default=None,
            help='JSON file to save detailed metrics'
        )
        parser.add_argument(
            '--quick',
            action='store_true',
            help='Run quick test suite (fewer test cases)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose logging'
        )
    
    def handle(self, *args, **options):
        """Run the LLM metrics test suite."""
        
        if options['verbose']:
            import structlog
            structlog.configure(
                processors=[
                    structlog.stdlib.filter_by_level,
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.PositionalArgumentsFormatter(),
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.UnicodeDecoder(),
                    structlog.processors.JSONRenderer()
                ],
                context_class=dict,
                logger_factory=structlog.stdlib.LoggerFactory(),
                wrapper_class=structlog.stdlib.BoundLogger,
                cache_logger_on_first_use=True,
            )
        
        self.stdout.write("Starting LLM Metrics Test Suite...")
        
        # Select test cases
        test_cases = DEFAULT_TEST_CASES
        if options['quick']:
            test_cases = test_cases[:3]  # Run first 3 tests for quick mode
        
        # Run tests
        collector = LLMMetricsCollector()
        
        try:
            loop = asyncio.get_event_loop()
            results = loop.run_until_complete(collector.run_test_suite(test_cases))
        except Exception as e:
            self.stderr.write(f"Error running tests: {e}")
            return
        
        # Generate and save report
        report = collector.generate_report(results)
        
        with open(options['output'], 'w') as f:
            f.write(report)
        
        self.stdout.write(f"Test report saved to: {options['output']}")
        
        # Save detailed metrics if requested
        if options['metrics_file']:
            collector.save_metrics(options['metrics_file'])
            self.stdout.write(f"Detailed metrics saved to: {options['metrics_file']}")
        
        # Display summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("TEST SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Total Tests: {results['total_tests']}")
        self.stdout.write(f"Passed: {results['passed_tests']}")
        self.stdout.write(f"Failed: {results['failed_tests']}")
        self.stdout.write(f"Success Rate: {results['success_rate']:.2%}")
        self.stdout.write(f"Average Response Time: {results['average_response_time']:.2f}s")
        
        if results['metrics']:
            avg_relevance = sum(m['relevance_score'] for m in results['metrics']) / len(results['metrics'])
            avg_completeness = sum(m['completeness_score'] for m in results['metrics']) / len(results['metrics'])
            avg_accuracy = sum(m['accuracy_score'] for m in results['metrics']) / len(results['metrics'])
            
            self.stdout.write(f"Average Relevance: {avg_relevance:.2f}")
            self.stdout.write(f"Average Completeness: {avg_completeness:.2f}")
            self.stdout.write(f"Average Accuracy: {avg_accuracy:.2f}")
        
        # Exit with error code if tests failed
        if results['failed_tests'] > 0:
            sys.exit(1)
