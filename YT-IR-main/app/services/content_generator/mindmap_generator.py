"""Mindmap generator service for YouTube videos."""

import json
import traceback
import time
import random
from typing import Dict, List

import structlog
from asgiref.sync import sync_to_async
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from yt_navigator.settings import INSTANT_LLM

logger = structlog.get_logger(__name__)


class MindmapGenerator:
    """Generate mindmap data from YouTube video transcripts."""

    def __init__(self):
        """Initialize the mindmap generator with LLM."""
        self.llm = ChatGroq(
            model=INSTANT_LLM,
            temperature=0.4,  # Moderate temperature for creativity
            max_tokens=1800  # Reduced to stay within 6000 TPM limit
        )
        self.output_parser = StrOutputParser()
        self.base_delay = 5.0  # Base delay between API calls
        self.max_delay = 60.0  # Maximum delay for exponential backoff
        self.max_retries = 3  # Maximum retries per request

    def generate_mindmap(self, transcript: str, video_title: str = "") -> dict:
        """Generate mindmap structure from video transcript.

        Args:
            transcript: Full video transcript text
            video_title: Title of the video for context

        Returns:
            dict: Hierarchical mindmap structure suitable for visualization
        """
        try:
            logger.info("Starting mindmap generation", video_title=video_title, transcript_length=len(transcript))
            
            if not transcript or len(transcript.strip()) < 50:
                logger.warning("Transcript too short for meaningful mindmap", length=len(transcript))
                return self._create_error_mindmap(video_title)
            
            # Smart sampling for long transcripts to capture content from different parts
            def sample_transcript(text, max_chars):
                """Sample transcript from multiple sections for comprehensive coverage."""
                if len(text) <= max_chars:
                    return text
                
                # For better coverage, sample from 5 sections instead of 3
                section_size = max_chars // 5
                
                # Get samples from different parts of the video
                section1 = text[:section_size]  # Beginning
                section2 = text[len(text)//5:len(text)//5 + section_size]  # 20% mark
                section3 = text[len(text)//2 - section_size//2:len(text)//2 + section_size//2]  # Middle
                section4 = text[3*len(text)//5:3*len(text)//5 + section_size]  # 60% mark
                section5 = text[-section_size:]  # End
                
                combined = (
                    f"[BEGINNING OF VIDEO]\n{section1}\n\n"
                    f"[20% MARK]\n{section2}\n\n"
                    f"[MIDDLE OF VIDEO]\n{section3}\n\n"
                    f"[60% MARK]\n{section4}\n\n"
                    f"[END OF VIDEO]\n{section5}\n\n"
                    f"[Note: Sampled from {len(text):,} character transcript across 5 sections]"
                )
                
                return combined
            
            # Progressive truncation with more conservative sizes to avoid rate limits
            # Need to balance coverage with 6000 TPM limit
            # Start with smaller sizes to prevent immediate rate limiting
            max_chars_values = [22000, 20000, 18000, 15000, 12000, 10000, 8000]
            
            for i, max_chars in enumerate(max_chars_values):
                try:
                    # Add delay between attempts with exponential backoff and jitter
                    if i > 0:
                        # Exponential backoff: 5s, 10s, 20s with jitter
                        base_delay_time = self.base_delay * (2 ** (i - 1))
                        jitter = random.uniform(0.8, 1.2)
                        delay_time = min(base_delay_time * jitter, self.max_delay)
                        
                        logger.info("Adding exponential backoff delay for mindmap", 
                                   delay=round(delay_time, 2), 
                                   attempt=i+1,
                                   base_delay=round(base_delay_time, 2))
                        time.sleep(delay_time)
                    
                    # Use smart sampling instead of just taking beginning
                    truncated_transcript = sample_transcript(transcript, max_chars)
                    actual_chars = len(truncated_transcript)
                    
                    if len(transcript) > max_chars:
                        logger.info("Using smart sampled transcript for mindmap", 
                                max_chars=max_chars, 
                                original_length=len(transcript), 
                                sample_length=actual_chars,
                                coverage_percent=round((max_chars/len(transcript))*100, 1),
                                attempt=i+1)
                    else:
                        logger.info("Using full transcript for mindmap", length=len(transcript))
                    
                    system_prompt = """You are an expert technical mindmap creator. Create COMPREHENSIVE, DETAILED mindmaps covering ALL important content from video transcripts.

CRITICAL REQUIREMENTS:
1. Output MUST be valid JSON - no exceptions
2. Extract ALL essential technical concepts, examples, processes, and relationships
3. Be THOROUGH - include details, examples, and context
4. Cover the full breadth and depth of content discussed
5. Include practical examples and applications when provided

OUTPUT FORMAT (JSON):
{
    "central_topic": {
        "text": "Descriptive central topic covering main theme",
        "color": "#1e40af"
    },
    "branches": [
        {
            "id": "branch_1",
            "text": "Main technical topic (descriptive name)",
            "color": "#059669",
            "children": [
                {
                    "id": "child_1_1",
                    "text": "Specific concept or subtopic with details",
                    "color": "#10b981",
                    "children": [
                        {
                            "id": "grandchild_1_1_1",
                            "text": "Detailed example or specific implementation",
                            "color": "#6366f1",
                            "children": []
                        }
                    ]
                }
            ]
        }
    ]
}

RULES FOR COMPREHENSIVE MINDMAPS:
1. Maximum 12-15 main branches to cover all content areas
2. Maximum 8-10 children per branch for thorough coverage
3. Maximum 4-5 grandchildren per child for detailed examples
4. Each node: 2-5 words maximum - just concepts, no sentences
5. NO sentences, NO explanations, NO filler words
6. Use technical terms and concepts only
7. Focus on WHAT it is, not HOW it's explained
8. Hierarchical: broad concept -> specific detail -> example
9. Clean spacing between nodes
10. Connect concepts clearly

EXAMPLE BAD NODE:
"Data structures are essential ingredients in creating fast and powerful algorithms"

EXAMPLE GOOD NODE:
"Data Structures"

EXAMPLE GOOD DETAILED NODE:
"Data Structures: Efficient organization methods"

REMEMBER: Output MUST be valid JSON. Start with { and end with }."""

                    human_prompt = f"""Video Title: {video_title}

TRANSCRIPT TO ANALYZE:
{truncated_transcript}

TASK: Create comprehensive mindmap covering ALL important content with clean spacing.
- Extract ALL major concepts and topics discussed
- Maximum 2-5 words per node - just concepts, no sentences
- NO explanations, NO filler words, NO descriptions
- Focus on technical terms and their relationships
- Create more nodes with better spacing
- Connect concepts hierarchically
- Use concise labels only

Output valid JSON only."""

                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=human_prompt)
                    ]

                    # Generate mindmap with retry logic
                    response = self._invoke_with_retry_sync(messages, max_retries=self.max_retries)
                    parsed_output = self.output_parser.parse(response.content)

                    # Try to parse as JSON
                    try:
                        import json
                        import re
                        
                        # Clean the response to ensure it's valid JSON
                        cleaned_output = parsed_output.strip()
                        
                        # Remove any text before or after JSON
                        json_match = re.search(r'\{.*\}', cleaned_output, re.DOTALL)
                        if json_match:
                            cleaned_output = json_match.group(0)
                        
                        mindmap_data = json.loads(cleaned_output)
                        
                        # Validate the structure and add missing fields if needed
                        if not isinstance(mindmap_data, dict):
                            raise ValueError("Response is not a valid JSON object")
                        
                        # Ensure required fields exist
                        if "central_topic" not in mindmap_data:
                            mindmap_data["central_topic"] = {
                                "text": video_title or "Main Topic",
                                "color": "#1e40af"
                            }
                        if "branches" not in mindmap_data:
                            mindmap_data["branches"] = []
                        
                        # Validate content quality
                        if not mindmap_data["branches"]:
                            logger.warning("Generated mindmap has no branches, creating fallback")
                            return self._create_fallback_mindmap(parsed_output, video_title)
                        
                        logger.info("Successfully generated mindmap", video_title=video_title, chars_used=max_chars)
                        return self._validate_and_fix_mindmap(mindmap_data)
                        
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning("JSON parsing failed for mindmap, creating fallback", error=str(e))
                        return self._create_fallback_mindmap(parsed_output, video_title)
                        
                except Exception as api_error:
                    if "413" in str(api_error) or "rate_limit_exceeded" in str(api_error) or "tokens per minute" in str(api_error) or "429" in str(api_error):
                        logger.warning("API rate limit hit for mindmap, trying smaller transcript", max_chars=max_chars, error=str(api_error))
                        continue  # Try with smaller transcript
                    else:
                        raise api_error  # Re-raise non-rate-limit errors
            
            # If all attempts failed, create fallback
            logger.error("All transcript sizes failed for mindmap, using fallback")
            return self._create_error_mindmap(video_title)

        except Exception as e:
            logger.error("Error generating mindmap", error=str(e), traceback=traceback.format_exc())
            return self._create_error_mindmap(video_title)

    def _validate_and_fix_mindmap(self, mindmap_data: dict) -> dict:
        """Validate and fix mindmap structure."""
        # Ensure required fields exist
        if "central_topic" not in mindmap_data:
            mindmap_data["central_topic"] = {
                "text": "Video Content",
                "color": "#1e40af"
            }

        if "branches" not in mindmap_data:
            mindmap_data["branches"] = []

        # Ensure all nodes have required fields
        for branch in mindmap_data["branches"]:
            if "id" not in branch:
                branch["id"] = f"branch_{hash(branch.get('text', '')) % 10000}"
            if "color" not in branch:
                branch["color"] = "#3b82f6"
            if "children" not in branch:
                branch["children"] = []

            self._validate_children(branch["children"])

        return mindmap_data

    def _validate_children(self, children: List[dict]) -> None:
        """Recursively validate child nodes."""
        for child in children:
            if "id" not in child:
                child["id"] = f"child_{hash(child.get('text', '')) % 10000}"
            if "color" not in child:
                child["color"] = "#10b981"
            if "children" not in child:
                child["children"] = []
            self._validate_children(child["children"])

    def _create_fallback_mindmap(self, text_content: str, video_title: str) -> dict:
        """Create mindmap from text content when JSON parsing fails."""
        try:
            # Extract main topics from the text content
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            
            # Create branches based on content analysis
            branches = []
            branch_counter = 1
            
            # Look for main topics throughout the ENTIRE transcript for comprehensive coverage
            # Scan all lines and group by topic indicators for complete coverage
            topic_lines = {}
            for i, line in enumerate(lines):
                if len(line) < 10:
                    continue
                    
                # Check if this line contains a topic indicator
                if any(indicator in line.lower() for indicator in ['what is', 'definition', 'how to', 'why', 'when', 'where', 'types of', 'examples', 'steps', 'process', 'method', 'approach', 'technique', 'algorithm', 'implementation', 'use case', 'benefit', 'advantage', 'disadvantage', 'limitation', 'consideration', 'introduction', 'overview', 'application', 'purpose', 'feature', 'characteristic', 'principle', 'concept', 'theory', 'framework', 'model', 'pattern', 'strategy', 'benefit', 'advantage', 'disadvantage', 'limitation', 'consideration', 'introduction', 'overview', 'application', 'purpose', 'feature', 'characteristic', 'principle', 'concept', 'theory', 'framework', 'model', 'pattern', 'strategy']):
                    topic_lines[i] = line
            
            # Create branches from all found topics (not just first 15)
            for i, (line_num, line) in enumerate(topic_lines.items()):
                if branch_counter > 15:  # Limit to 15 main branches for readability
                    break
                    
                branch_id = f"branch_{branch_counter}"
                # Extract just the concept, remove filler words
                concept_words = []
                for word in line.split():
                    if len(word) > 2 and word.lower() not in ['the', 'is', 'are', 'was', 'were', 'been', 'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those', 'for', 'with', 'from', 'about', 'into', 'onto', 'upon', 'and', 'but', 'or', 'nor', 'yet', 'so']:
                        concept_words.append(word)
                branch_text = ' '.join(concept_words[:5])  # Max 5 words for clean spacing
                
                # Create children from surrounding lines
                children = []
                child_counter = 1
                
                # Look for supporting concepts in surrounding lines (both before and after)
                surrounding_range = 15
                start_check = max(0, line_num - surrounding_range//2)
                end_check = min(len(lines), line_num + surrounding_range//2 + 1)
                
                for j in range(start_check, end_check):
                    if j != line_num and len(lines[j]) > 8 and lines[j] != line:
                        # Extract concise concept for child
                        child_words = []
                        for word in lines[j].split():
                            if len(word) > 2 and word.lower() not in ['the', 'is', 'are', 'was', 'were', 'been', 'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those', 'for', 'with', 'from', 'about', 'into', 'onto', 'upon', 'and', 'but', 'or', 'nor', 'yet', 'so']:
                                child_words.append(word)
                        child_id = f"{branch_id}_{child_counter}"
                        child_text = ' '.join(child_words[:4])  # Max 4 words for children
                        
                        # Create grandchildren from surrounding lines
                        grandchildren = []
                        grandchild_counter = 1
                        
                        # Look for grandchildren in smaller range around child
                        child_surrounding = 8
                        child_start = max(0, j - child_surrounding//2)
                        child_end = min(len(lines), j + child_surrounding//2 + 1)
                        
                        for k in range(child_start, child_end):
                            if k != j and k != line_num and len(lines[k]) > 6:
                                # Extract very concise grandchild concept
                                grandchild_words = []
                                for word in lines[k].split():
                                    if len(word) > 2 and word.lower() not in ['the', 'is', 'are', 'was', 'were', 'been', 'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those', 'for', 'with', 'from', 'about', 'into', 'onto', 'upon', 'and', 'but', 'or', 'nor', 'yet', 'so']:
                                        grandchild_words.append(word)
                                grandchild_id = f"{child_id}_{grandchild_counter}"
                                grandchild_text = ' '.join(grandchild_words[:3])  # Max 3 words for grandchildren
                            grandchildren.append({
                                "id": grandchild_id,
                                "text": grandchild_text,
                                "color": "#f59e0b",
                                "children": []
                            })
                            grandchild_counter += 1
                            if grandchild_counter > 2:
                                break
                            
                            children.append({
                                "id": child_id,
                                "text": child_text,
                                "color": "#10b981",
                                "children": grandchildren
                            })
                            child_counter += 1
                            if child_counter > 3:  # Limit children
                                break
                    
                    branches.append({
                        "id": branch_id,
                        "text": branch_text,
                        "color": "#3b82f6",
                        "children": children
                    })
                    branch_counter += 1
                    if branch_counter > 5:  # Limit branches
                        break
            
            # If no branches found, create generic ones
            if not branches:
                branches = [
                    {
                        "id": "branch_1",
                        "text": "Main Content",
                        "color": "#3b82f6",
                        "children": [
                            {
                                "id": "branch_1_1",
                                "text": "Key Points",
                                "color": "#10b981",
                                "children": [
                                    {
                                        "id": "branch_1_1_1",
                                        "text": "Important Information",
                                        "color": "#f59e0b",
                                        "children": []
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "id": "branch_2",
                        "text": "Supporting Details",
                        "color": "#3b82f6",
                        "children": [
                            {
                                "id": "branch_2_1",
                                "text": "Examples",
                                "color": "#10b981",
                                "children": []
                            }
                        ]
                    }
                ]
            
            return {
                "central_topic": {
                    "text": video_title or "Content Analysis",
                    "color": "#1e40af"
                },
                "branches": branches
            }
            
        except Exception as e:
            logger.error("Error creating fallback mindmap", error=str(e))
            return self._create_error_mindmap(video_title)

    def _create_error_mindmap(self, video_title: str) -> dict:
        """Create error fallback mindmap."""
        return {
            "central_topic": {
                "text": video_title or "Error",
                "color": "#ef4444"
            },
            "branches": [
                {
                    "id": "error_branch_1",
                    "text": "Error Processing Content",
                    "color": "#ef4444",
                    "children": [
                        {
                            "id": "error_child_1",
                            "text": "Unable to generate mindmap",
                            "color": "#ef4444",
                            "children": []
                        }
                    ]
                }
            ]
        }

    async def _invoke_with_retry(self, messages, max_retries=3):
        """Invoke LLM with intelligent retry logic for rate limiting."""
        import asyncio
        
        for attempt in range(max_retries + 1):
            try:
                return self.llm.invoke(messages)
            except Exception as api_error:
                if "429" in str(api_error) or "rate_limit_exceeded" in str(api_error) or "Too Many Requests" in str(api_error) or "tokens per minute" in str(api_error):
                    if attempt < max_retries:
                        # Calculate exponential backoff with jitter
                        base_delay = self.base_delay * (2 ** attempt)
                        jitter = random.uniform(0.5, 1.5)
                        delay = min(base_delay * jitter, self.max_delay)
                        
                        logger.warning(
                            "Rate limit hit for mindmap, retrying with exponential backoff",
                            attempt=attempt + 1,
                            max_retries=max_retries + 1,
                            delay=round(delay, 2),
                            error=str(api_error)
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "Max retries exceeded for rate limiting in mindmap",
                            attempts=attempt + 1,
                            error=str(api_error)
                        )
                        raise api_error
                else:
                    # Non-rate-limit error, re-raise immediately
                    raise api_error
        
        # Should not reach here
        raise Exception("Unexpected error in retry logic")

    def _invoke_with_retry_sync(self, messages, max_retries=3):
        """Synchronous version of _invoke_with_retry for use in sync functions."""
        import asyncio
        import concurrent.futures
        
        # Always use thread pool to avoid event loop conflicts
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self._invoke_with_retry(messages, max_retries))
            return future.result()
