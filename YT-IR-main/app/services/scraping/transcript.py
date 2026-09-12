"""Transcript-related functionality for YouTube scraping."""

import time
import traceback
from typing import (
    Dict,
    List,
)

import structlog
import yt_dlp
import requests
import xml.etree.ElementTree as ET

from app.helpers import convert_seconds_to_timestamp

logger = structlog.get_logger(__name__)


class TranscriptScraper:
    """Transcript-related functionality for YouTube scraping."""

    def __init__(self, max_transcript_segment_duration: int = 40):
        """Initialize the transcript scraper.

        Args:
            max_transcript_segment_duration: Maximum duration for transcript segments in seconds
        """
        self.max_transcript_segment_duration = max_transcript_segment_duration

    def get_video_transcript(self, video_metadata: Dict) -> List[Dict]:
        """Fetches and formats the transcript of a YouTube video using yt-dlp.

        Args:
            video_metadata: Dictionary containing video metadata

        Returns:
            List[Dict]: List of transcript segments
        """
        video_id = video_metadata["videoId"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # Retry logic with exponential backoff
        for attempt in range(3):
            try:
                # Add delay between attempts to avoid rate limiting
                if attempt > 0:
                    delay = 2 ** attempt  # 2s, 4s, 8s
                    logger.info(f"Retrying transcript fetch after {delay}s", video_id=video_id, attempt=attempt)
                    time.sleep(delay)
                
                # Use yt-dlp to fetch transcript
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'writesubtitles': False,
                    'subtitleslangs': ['en'],
                    'skip_download': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)
                    
                    # Try to get subtitles using yt-dlp's built-in method
                    try:
                        # Use yt-dlp's subtitle downloader
                        subtitles = ydl.extract_info(video_url, download=False, process=False)
                        
                        # Check for manual subtitles first
                        if 'subtitles' in subtitles and 'en' in subtitles['subtitles']:
                            subtitle_info = subtitles['subtitles']['en'][0]
                            subtitle_url = subtitle_info['url']
                        # Fall back to auto-generated captions
                        elif 'automatic_captions' in subtitles and 'en' in subtitles['automatic_captions']:
                            subtitle_info = subtitles['automatic_captions']['en'][0]
                            subtitle_url = subtitle_info['url']
                        else:
                            logger.warning(
                                f"No transcript available for https://www.youtube.com/watch?v={video_id}. Video might not have captions enabled.",
                                video_id=video_id,
                                has_subtitles="subtitles" in subtitles,
                                has_auto_captions="automatic_captions" in subtitles,
                            )
                            return []
                        
                        # Parse subtitle content
                        response = requests.get(subtitle_url, timeout=10)
                        response.raise_for_status()
                        
                        # Debug: Log response details
                        logger.info(
                            f"Subtitle response received",
                            video_id=video_id,
                            status_code=response.status_code,
                            content_type=response.headers.get('content-type', 'unknown'),
                            content_length=len(response.content),
                            subtitle_url=subtitle_url[:100] + "..." if len(subtitle_url) > 100 else subtitle_url
                        )
                        
                        # Check if response is valid format (XML or JSON)
                        try:
                            # Clean the response content - sometimes there are BOM or encoding issues
                            content = response.content.strip()
                            if content.startswith(b'\xef\xbb\xbf'):  # Remove BOM if present
                                content = content[3:]
                            
                            # Log first 200 characters of content for debugging
                            logger.info(
                                f"Subtitle content preview",
                                video_id=video_id,
                                content_preview=content[:200] if content else "Empty content",
                                content_start=content[:50] if content else "Empty"
                            )
                            
                            # Check if it's JSON format (new YouTube format)
                            if content.startswith(b'{'):
                                import json
                                try:
                                    json_data = json.loads(content.decode('utf-8'))
                                    # Convert JSON format to transcript
                                    transcript = []
                                    if 'events' in json_data:
                                        for event in json_data['events']:
                                            start_ms = event.get('tStartMs', 0)
                                            duration_ms = event.get('dDurationMs', 0)
                                            
                                            # Extract text from segments
                                            text_parts = []
                                            if 'segs' in event:
                                                for seg in event['segs']:
                                                    if 'utf8' in seg:
                                                        text_parts.append(seg['utf8'])
                                            
                                            text = ''.join(text_parts).strip()
                                            if text:
                                                transcript.append({
                                                    'text': text,
                                                    'start': start_ms / 1000.0,  # Convert to seconds
                                                    'duration': duration_ms / 1000.0,  # Convert to seconds
                                                })
                                    
                                    logger.info(f"Successfully parsed JSON transcript for {video_id}", segments=len(transcript))
                                    return self._format_transcript(transcript, video_metadata)
                                    
                                except json.JSONDecodeError as e:
                                    logger.error(f"Failed to parse JSON transcript for {video_id}", error=str(e))
                                    return []
                            
                            # Try to parse as XML (legacy format)
                            root = ET.fromstring(content)
                        except ET.ParseError as e:
                            logger.error(
                                f"Invalid XML subtitle format for https://www.youtube.com/watch?v={video_id}",
                                video_id=video_id,
                                error=str(e),
                                response_preview=response.content[:200] if response.content else "Empty response"
                            )
                            return []
                    
                    except Exception as e:
                        logger.error(
                            f"Error extracting subtitles with yt-dlp for https://www.youtube.com/watch?v={video_id}",
                            video_id=video_id,
                            error=str(e)
                        )
                        return []
                    
                    # Convert to transcript format
                    transcript = []
                    for item in root.findall('.//text'):
                        start = float(item.get('start', 0))
                        duration = float(item.get('dur', 0))
                        text = item.text or ''
                        
                        transcript.append({
                            'text': text,
                            'start': start,
                            'duration': duration
                        })
                    
                    return self._format_transcript(transcript, video_metadata)

            except Exception as e:
                if attempt < 2:  # Don't log error on final attempt
                    continue
                else:
                    logger.error(
                        f"Failed to fetch transcript after 3 attempts for https://www.youtube.com/watch?v={video_id}",
                        video_id=video_id,
                        error=e,
                    )
                    return []

    def _format_transcript(self, transcript: List[Dict], video_metadata: Dict) -> List[Dict]:
        """Formats the video transcript into segments with a maximum duration.

        Args:
            transcript: Raw transcript data from YouTube API
            video_metadata: Dictionary containing video metadata

        Returns:
            List[Dict]: List of formatted transcript segments
        """
        # CRITICAL DEBUG: Log entry to verify this method is called
        logger.info("=== _format_transcript CALLED ===", 
                   transcript_count=len(transcript),
                   video_id=video_metadata.get("videoId"))
        
        formatted_transcript = []
        segment_text, start_time = "", 0
        current_duration = 0

        try:
            # Debug: Log the first transcript item and video metadata
            if transcript:
                logger.info("Formatting transcript", 
                           first_item=transcript[0] if transcript else None,
                           video_id=video_metadata.get("videoId"),
                           video_metadata_keys=list(video_metadata.keys()))
            
            for i, item in enumerate(transcript):
                # If this is the first item or we're starting a new segment
                if i == 0 or current_duration >= self.max_transcript_segment_duration:
                    # Save the previous segment if it exists
                    if segment_text and i > 0:
                        segment_data = {
                            "video_id": video_metadata["videoId"],
                            "start_time": start_time,
                            "timestamp": convert_seconds_to_timestamp(start_time),
                            "text": segment_text.strip(),
                            "duration": current_duration,
                        }
                        formatted_transcript.append(segment_data)
                        
                        # Debug: Log first few segments
                        if len(formatted_transcript) <= 2:
                            logger.info("Created transcript segment", 
                                       segment_data=segment_data,
                                       has_video_id="video_id" in segment_data)

                    # Start a new segment
                    segment_text = item["text"]
                    start_time = item["start"]
                    current_duration = item["duration"]
                else:
                    # Continue the current segment
                    segment_text += " " + item["text"]
                    current_duration += item["duration"]

            # Add the last segment
            if segment_text:
                segment_data = {
                    "video_id": video_metadata["videoId"],
                    "start_time": start_time,
                    "timestamp": convert_seconds_to_timestamp(start_time),
                    "text": segment_text.strip(),
                    "duration": current_duration,
                }
                formatted_transcript.append(segment_data)
                
                # Debug: Log final segment
                if len(formatted_transcript) <= 2:
                    logger.info("Created final transcript segment", 
                               segment_data=segment_data,
                               has_video_id="video_id" in segment_data)

            return formatted_transcript

        except Exception as e:
            logger.error("Error formatting transcript", error=e, traceback=traceback.format_exc())
            return []
        
        # CRITICAL DEBUG: This should never be reached
        logger.error("=== _format_transcript UNEXPECTED PATH ===")
        return []
