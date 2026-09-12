"""Notes generator service for YouTube videos."""

import asyncio
import json
import re
import traceback
import time
import random
from typing import List, Dict, Optional

import structlog
from asgiref.sync import sync_to_async
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from app.models import VideoChunk
from yt_navigator.settings import INSTANT_LLM

logger = structlog.get_logger(__name__)


class NotesGenerator:
    """Generate structured notes from YouTube video transcripts."""

    def __init__(self):
        """Initialize the notes generator with LLM."""
        self.llm = ChatGroq(
            model=INSTANT_LLM,
            temperature=0.3,  # Lower temperature for more structured output
            max_tokens=3000  # Increased from 2000 to allow more detailed notes
        )
        self.output_parser = StrOutputParser()
        self.CHUNK_SIZE = 25  # Process 25 chunks at a time (~12-13K chars, well under limit)
        self.base_delay = 5.0  # Base delay between API calls
        self.max_delay = 60.0  # Maximum delay for exponential backoff
        self.max_retries = 3  # Maximum retries per request

    async def generate_notes_from_video_id(self, video_id: str, video_title: str = "") -> dict:
        """Generate structured notes from stored video chunks in SQLite.

        Args:
            video_id: The ID of the video to generate notes for
            video_title: Title of the video for context

        Returns:
            dict: Structured notes with main points, key concepts, and summary
        """
        try:
            # Fetch stored chunks from database
            get_chunks = sync_to_async(
                lambda: list(VideoChunk.objects.filter(video_id=video_id).order_by('start')),
                thread_sensitive=True
            )
            chunks = await get_chunks()
            
            if not chunks:
                logger.warning("No chunks found for video", video_id=video_id)
                return self._create_error_fallback(video_title)
            
            logger.info("Processing stored chunks from database", 
                       video_id=video_id, 
                       total_chunks=len(chunks),
                       chunk_size=self.CHUNK_SIZE)
            
            # Process chunks in batches
            all_notes = []
            for batch_num, i in enumerate(range(0, len(chunks), self.CHUNK_SIZE)):
                batch = chunks[i:i + self.CHUNK_SIZE]
                batch_text = " ".join([chunk.text for chunk in batch])
                batch_chars = len(batch_text)
                
                logger.info("Processing batch", 
                           video_id=video_id,
                           batch_num=batch_num + 1,
                           batch_size=len(batch),
                           total_batches=(len(chunks) // self.CHUNK_SIZE) + (1 if len(chunks) % self.CHUNK_SIZE else 0),
                           batch_chars=batch_chars)
                
                # Add adaptive delay between batches to avoid rate limiting
                if batch_num > 0:
                    # Calculate delay with jitter to prevent synchronized requests
                    # Start with base delay and increase if we've had rate limit issues
                    jitter = random.uniform(0.8, 1.2)  # ±20% jitter
                    delay = self.base_delay * jitter
                    
                    logger.info("Adding adaptive delay between batches", 
                               delay=round(delay, 2), 
                               batch_num=batch_num,
                               jitter_factor=round(jitter, 2))
                    await asyncio.sleep(delay)
                
                # Generate notes for this batch
                batch_notes = await sync_to_async(self.generate_notes, thread_sensitive=True)(
                    batch_text, 
                    f"{video_title} (Part {batch_num + 1})"
                )
                
                if batch_notes and batch_notes.get("main_topics"):
                    all_notes.append(batch_notes)
            
            if not all_notes:
                logger.warning("No notes generated from any batch, using fallback")
                return self._create_error_fallback(video_title)
            
            # Combine notes from all batches
            combined_notes = self._combine_batch_notes(all_notes, video_title)
            logger.info("Successfully generated notes from stored chunks", video_id=video_id)
            return combined_notes
            
        except Exception as e:
            logger.error("Error generating notes from stored chunks", 
                        video_id=video_id, 
                        error=str(e), 
                        traceback=traceback.format_exc())
            return self._create_error_fallback(video_title)

    def _combine_batch_notes(self, batch_notes_list: List[Dict], video_title: str) -> dict:
        """Combine notes from multiple batches into a single coherent structure.

        Args:
            batch_notes_list: List of note dictionaries from each batch
            video_title: Video title for the combined notes

        Returns:
            dict: Combined structured notes
        """
        combined = {
            "main_topics": [],
            "key_concepts": [],
            "summary": "",
            "action_items": []
        }
        
        seen_topics = set()
        seen_concepts = set()
        all_summaries = []
        
        for batch_notes in batch_notes_list:
            # Combine topics (avoid duplicates)
            for topic in batch_notes.get("main_topics", []):
                topic_name = topic.get("topic", "")
                if topic_name and topic_name not in seen_topics:
                    seen_topics.add(topic_name)
                    combined["main_topics"].append(topic)
            
            # Combine concepts (avoid duplicates)
            for concept in batch_notes.get("key_concepts", []):
                concept_name = concept.get("concept", "")
                if concept_name and concept_name not in seen_concepts:
                    seen_concepts.add(concept_name)
                    combined["key_concepts"].append(concept)
            
            # Collect summaries
            if batch_notes.get("summary"):
                all_summaries.append(batch_notes["summary"])
            
            # Combine action items
            combined["action_items"].extend(batch_notes.get("action_items", []))
        
        # Create combined summary
        combined["summary"] = " ".join(all_summaries) if all_summaries else f"Notes compiled from {len(batch_notes_list)} content sections of {video_title}"
        
        # Limit to avoid excessive data but allow more comprehensive content
        combined["main_topics"] = combined["main_topics"][:8]
        combined["key_concepts"] = combined["key_concepts"][:15]
        combined["action_items"] = list(set(combined["action_items"]))[:8]
        
        return combined

    def generate_notes(self, transcript: str, video_title: str = "") -> dict:
        """Generate structured bullet-point notes from video transcript.

        Args:
            transcript: Full video transcript text
            video_title: Title of the video for context

        Returns:
            dict: Structured notes with main points, key concepts, and summary
        """
        try:
            logger.info("Starting notes generation", video_title=video_title, transcript_length=len(transcript))
            
            if not transcript or len(transcript.strip()) < 50:
                logger.warning("Transcript too short for meaningful notes", length=len(transcript))
                return self._create_error_fallback(video_title)
            
            # Smart sampling for long transcripts to capture content from different parts
            def sample_transcript(text, max_chars):
                """Sample transcript from beginning, middle and end for comprehensive coverage."""
                if len(text) <= max_chars:
                    return text
                
                # Calculate sample sizes
                beginning_size = int(max_chars * 0.4)  # 40% from beginning
                end_size = int(max_chars * 0.3)        # 30% from end
                middle_size = max_chars - beginning_size - end_size  # 30% from middle
                
                # Get samples from different parts
                beginning = text[:beginning_size]
                
                # Find a good middle section (avoid cutting mid-sentence if possible)
                middle_start = len(text) // 2 - middle_size // 2
                middle = text[middle_start:middle_start + middle_size]
                
                end = text[-end_size:]
                
                # Combine with markers
                combined = (
                    f"[BEGINNING OF VIDEO - First {beginning_size} characters]\n{beginning}\n\n"
                    f"[MIDDLE OF VIDEO - Representative sample]\n{middle}\n\n"
                    f"[END OF VIDEO - Last {end_size} characters]\n{end}\n\n"
                    f"[Note: This is a sampled excerpt from a {len(text):,} character transcript. "
                    f"Total video length analyzed: approximately {len(text) // 1000} minutes of content.]"
                )
                
                return combined
            
            # Progressive truncation with more conservative sizes to avoid rate limits
            # Start with smaller sizes to prevent immediate rate limiting
            max_chars_values = [30000, 25000, 20000, 15000, 12000, 10000, 8000, 6000]
            
            for i, max_chars in enumerate(max_chars_values):
                try:
                    # Add delay between attempts with exponential backoff and jitter
                    if i > 0:
                        # Exponential backoff: 5s, 10s, 20s with jitter
                        base_delay_time = self.base_delay * (2 ** (i - 1))
                        jitter = random.uniform(0.8, 1.2)
                        delay_time = min(base_delay_time * jitter, self.max_delay)
                        
                        logger.info("Adding exponential backoff delay", 
                                   delay=round(delay_time, 2), 
                                   attempt=i+1,
                                   base_delay=round(base_delay_time, 2))
                        time.sleep(delay_time)
                    
                    # Use smart sampling instead of just taking beginning
                    truncated_transcript = sample_transcript(transcript, max_chars)
                    actual_chars = len(truncated_transcript)
                    
                    if len(transcript) > max_chars:
                        logger.info("Using smart sampled transcript", 
                                max_chars=max_chars, 
                                original_length=len(transcript), 
                                sample_length=actual_chars,
                                coverage_percent=round((max_chars/len(transcript))*100, 1),
                                attempt=i+1)
                    else:
                        logger.info("Using full transcript", length=len(transcript))
                    
                    system_prompt = """You are an expert technical note-taker. Create COMPREHENSIVE, DETAILED notes covering ALL important content from video transcripts.

CRITICAL REQUIREMENTS:
1. Output MUST be valid JSON - no exceptions
2. Extract ALL essential technical concepts, definitions, examples, and explanations
3. Be THOROUGH - include details, examples, and context
4. Cover the full breadth and depth of the content
5. Include practical examples when provided

OUTPUT FORMAT (JSON):
{
    "main_topics": [
        {
            "topic": "Technical topic name (descriptive)",
            "points": [
                {
                    "point": "Detailed technical concept or explanation",
                    "details": "Comprehensive explanation with examples if provided",
                    "timestamp": "Optional time reference"
                }
            ]
        }
    ],
    "key_concepts": [
        {
            "concept": "Technical term",
            "definition": "Detailed definition with context and usage"
        }
    ],
    "summary": "Comprehensive 4-5 sentence summary covering all major points",
    "action_items": ["Specific actionable takeaways or implementation steps"]
}

RULES FOR COMPREHENSIVE NOTES:
1. Maximum 6-8 main topics to cover all content areas
2. Maximum 5-6 points per topic for thorough coverage
3. Each point should be detailed with explanations and examples
4. Include practical examples and use cases when mentioned
5. Provide context and relationships between concepts
6. Capture step-by-step processes and methodologies
7. Include important nuances and edge cases discussed

EXAMPLE BAD POINT:
"Data structure: organizes data"

EXAMPLE GOOD POINT:
"Data structure: systematic method of organizing and storing data in a computer so that it can be accessed and modified efficiently. Common types include arrays, linked lists, trees, and graphs, each with specific use cases and performance characteristics."

REMEMBER: Output MUST be valid JSON. Start with { and end with }."""

                    human_prompt = f"""Video Title: {video_title}

TRANSCRIPT TO ANALYZE:
{truncated_transcript}

TASK: Create comprehensive, detailed notes covering ALL important content.
- Include all major topics and subtopics discussed
- Provide detailed explanations with examples
- Capture step-by-step processes and methodologies
- Include practical applications and use cases
- Extract all important concepts with thorough definitions
- Provide context and relationships between ideas

Output valid JSON only."""

                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=human_prompt)
                    ]

                    # Generate notes with retry logic
                    response = self._invoke_with_retry_sync(messages, max_retries=self.max_retries)
                    parsed_output = self.output_parser.parse(response.content)
                    
                    # Try to parse as JSON, fallback to structured text if needed
                    try:
                        import json
                        import re
                        
                        # Clean the response to ensure it's valid JSON
                        cleaned_output = parsed_output.strip()
                        
                        # Remove any text before or after JSON
                        json_match = re.search(r'\{.*\}', cleaned_output, re.DOTALL)
                        if json_match:
                            cleaned_output = json_match.group(0)
                        
                        notes_data = json.loads(cleaned_output)
                        
                        # Validate the structure and add missing fields if needed
                        if not isinstance(notes_data, dict):
                            raise ValueError("Response is not a valid JSON object")
                        
                        # Ensure required fields exist
                        if "main_topics" not in notes_data:
                            notes_data["main_topics"] = []
                        if "key_concepts" not in notes_data:
                            notes_data["key_concepts"] = []
                        if "summary" not in notes_data:
                            notes_data["summary"] = "Summary not available"
                        if "action_items" not in notes_data:
                            notes_data["action_items"] = []
                        
                        # Validate content quality
                        if not notes_data["main_topics"] and not notes_data["key_concepts"]:
                            logger.warning("Generated notes are empty, creating fallback")
                            return self._create_fallback_structure(parsed_output, video_title)
                        
                        logger.info("Successfully generated structured notes", video_title=video_title, chars_used=max_chars)
                        return notes_data
                        
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning("JSON parsing failed, creating fallback structure", error=str(e))
                        return self._create_fallback_structure(parsed_output, video_title)
                        
                except Exception as api_error:
                    if "413" in str(api_error) or "rate_limit_exceeded" in str(api_error) or "tokens per minute" in str(api_error) or "429" in str(api_error):
                        logger.warning("API rate limit hit, trying smaller transcript", max_chars=max_chars, error=str(api_error))
                        continue  # Try with smaller transcript
                    else:
                        raise api_error  # Re-raise non-rate-limit errors
            
            # If all attempts failed, create fallback
            logger.error("All transcript sizes failed, using fallback")
            return self._create_error_fallback(video_title)

        except Exception as e:
            logger.error("Error generating notes", error=str(e), traceback=traceback.format_exc())
            return self._create_error_fallback(video_title)

    def _create_fallback_structure(self, text_content: str, video_title: str) -> dict:
        """Create structured notes from text content when JSON parsing fails."""
        try:
            # Extract main topics from the text content
            lines = [line.strip() for line in text_content.split('\n') if line.strip()]
            
            # Look for topic indicators
            main_topics = []
            key_concepts = []
            current_topic = None
            
            for i, line in enumerate(lines):
                # Skip very short lines or generic statements
                if len(line) < 10 or line.lower() in ['summary:', 'conclusion:', 'in conclusion:']:
                    continue
                    
                # Look for topic indicators (questions, definitions, main points, examples, processes)
                if any(indicator in line.lower() for indicator in ['what is', 'definition', 'how to', 'why', 'when', 'where', 'types of', 'examples', 'steps', 'process', 'method', 'approach', 'technique', 'algorithm', 'implementation', 'use case', 'benefit', 'advantage', 'disadvantage', 'limitation', 'consideration']):
                    if current_topic:
                        main_topics.append(current_topic)
                    
                    current_topic = {
                        "topic": line[:120] + "..." if len(line) > 120 else line,
                        "points": [
                            {
                                "point": "Key concept extracted from transcript",
                                "details": line[:300] + "..." if len(line) > 300 else line,
                                "timestamp": ""
                            }
                        ]
                    }
                elif current_topic and len(line) > 15:
                    # Add as a point to current topic with more detail
                    current_topic["points"].append({
                        "point": line[:120] + "..." if len(line) > 120 else line,
                        "details": line[:250] + "..." if len(line) > 250 else "",
                        "timestamp": ""
                    })
            
            if current_topic:
                main_topics.append(current_topic)
            
            # Extract key concepts (single words or short phrases that seem important)
            for line in lines[:20]:  # Check first 20 lines for concepts
                words = line.split()
                for word in words:
                    if len(word) > 6 and word.isalpha() and not any(skip in word.lower() for skip in ['this', 'that', 'with', 'from', 'they', 'have', 'been']):
                        concept = {
                            "concept": word.capitalize(),
                            "definition": f"Key concept mentioned in the transcript about {word}"
                        }
                        key_concepts.append(concept)
                        if len(key_concepts) >= 5:  # Limit to 5 concepts
                            break
                if len(key_concepts) >= 5:
                    break
            
            # Create summary from first few lines
            summary_lines = [line for line in lines[:5] if len(line) > 20]
            summary = " ".join(summary_lines[:3]) if summary_lines else "Summary could not be generated from the transcript content."
            
            # Generate action items based on content
            action_items = [
                "Review the key concepts and definitions presented",
                "Apply the examples and techniques discussed",
                "Practice with the methods explained in the content"
            ]
            
            return {
                "main_topics": main_topics[:5],  # Limit to 5 topics
                "key_concepts": key_concepts,
                "summary": summary[:500] + "..." if len(summary) > 500 else summary,
                "action_items": action_items
            }
            
        except Exception as e:
            logger.error("Error creating fallback structure", error=str(e))
            return self._create_error_fallback(video_title)

    def _create_error_fallback(self, video_title: str) -> dict:
        """Create error fallback structure."""
        return {
            "main_topics": [
                {
                    "topic": "Error",
                    "points": [
                        {
                            "point": "Unable to generate notes at this time",
                            "details": "Please try again later",
                            "timestamp": ""
                        }
                    ]
                }
            ],
            "key_concepts": [],
            "summary": f"Error generating notes for: {video_title}",
            "action_items": []
        }

    async def _invoke_with_retry(self, messages, max_retries=3):
        """Invoke LLM with intelligent retry logic for rate limiting."""
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
                            "Rate limit hit, retrying with exponential backoff",
                            attempt=attempt + 1,
                            max_retries=max_retries + 1,
                            delay=round(delay, 2),
                            error=str(api_error)
                        )
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(
                            "Max retries exceeded for rate limiting",
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
