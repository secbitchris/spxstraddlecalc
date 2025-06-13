#!/usr/bin/env python3

import aiohttp
import asyncio
import json
import logging
from datetime import datetime
import pytz
from typing import Dict, Any, Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class GistPublisher:
    """
    GitHub Gist publisher for SPX straddle analysis reports
    """
    
    def __init__(self, github_token: str = None):
        """
        Initialize GitHub Gist publisher
        
        Args:
            github_token: GitHub personal access token with gist scope
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.github_api_url = "https://api.github.com/gists"
        self.enabled = bool(self.github_token)
        
        if not self.enabled:
            logger.warning("GitHub token not provided - Gist publishing disabled")
        else:
            logger.info("GitHub Gist publisher initialized")
    
    async def create_gist(self, title: str, content: str, description: str = None, public: bool = True) -> Optional[Dict[str, Any]]:
        """
        Create a new GitHub Gist
        
        Args:
            title: Title/filename for the gist
            content: Content of the gist
            description: Description of the gist
            public: Whether the gist should be public
            
        Returns:
            Gist information dict with 'url', 'id', etc. or None if failed
        """
        if not self.enabled:
            logger.warning("GitHub Gist publishing is disabled")
            return None
        
        try:
            # Prepare gist data
            gist_data = {
                "description": description or f"SPX 0DTE Straddle Analysis - {title}",
                "public": public,
                "files": {
                    f"{title}.md": {
                        "content": content
                    }
                }
            }
            
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "SPX-Straddle-Calculator"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.github_api_url, json=gist_data, headers=headers) as response:
                    if response.status == 201:
                        gist_info = await response.json()
                        logger.info(f"Successfully created Gist: {gist_info['html_url']}")
                        return {
                            "status": "success",
                            "url": gist_info["html_url"],
                            "raw_url": gist_info["files"][f"{title}.md"]["raw_url"],
                            "id": gist_info["id"],
                            "created_at": gist_info["created_at"],
                            "description": gist_info["description"]
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create Gist: {response.status} - {error_text}")
                        return {
                            "status": "error",
                            "error": f"GitHub API error: {response.status}",
                            "details": error_text
                        }
                        
        except Exception as e:
            logger.error(f"Error creating Gist: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def update_gist(self, gist_id: str, title: str, content: str, description: str = None) -> Optional[Dict[str, Any]]:
        """
        Update an existing GitHub Gist
        
        Args:
            gist_id: ID of the gist to update
            title: Title/filename for the gist
            content: New content of the gist
            description: New description of the gist
            
        Returns:
            Updated gist information dict or None if failed
        """
        if not self.enabled:
            logger.warning("GitHub Gist publishing is disabled")
            return None
        
        try:
            # Prepare update data
            update_data = {
                "files": {
                    f"{title}.md": {
                        "content": content
                    }
                }
            }
            
            if description:
                update_data["description"] = description
            
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "SPX-Straddle-Calculator"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.patch(f"{self.github_api_url}/{gist_id}", json=update_data, headers=headers) as response:
                    if response.status == 200:
                        gist_info = await response.json()
                        logger.info(f"Successfully updated Gist: {gist_info['html_url']}")
                        return {
                            "status": "success",
                            "url": gist_info["html_url"],
                            "raw_url": gist_info["files"][f"{title}.md"]["raw_url"],
                            "id": gist_info["id"],
                            "updated_at": gist_info["updated_at"],
                            "description": gist_info["description"]
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to update Gist: {response.status} - {error_text}")
                        return {
                            "status": "error",
                            "error": f"GitHub API error: {response.status}",
                            "details": error_text
                        }
                        
        except Exception as e:
            logger.error(f"Error updating Gist: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def publish_analysis_report(self, report_content: str, metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Publish SPX straddle analysis report as a GitHub Gist
        
        Args:
            report_content: The markdown report content
            metadata: Report metadata (timestamp, timeframes, etc.)
            
        Returns:
            Gist information dict or None if failed
        """
        if not self.enabled:
            return None
        
        try:
            # Generate title and description
            et_tz = pytz.timezone('US/Eastern')
            timestamp = datetime.now(et_tz)
            date_str = timestamp.strftime('%Y-%m-%d')
            time_str = timestamp.strftime('%H:%M ET')
            
            title = f"SPX-0DTE-Straddle-Analysis-{date_str}"
            description = f"SPX 0DTE Straddle Multi-Timeframe Analysis - {date_str} at {time_str} | {metadata.get('timeframes_analyzed', 0)} timeframes | {metadata.get('total_data_points', 0)} data points"
            
            # Create the gist
            result = await self.create_gist(title, report_content, description, public=True)
            
            if result and result.get("status") == "success":
                logger.info(f"Published analysis report to Gist: {result['url']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error publishing analysis report: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def is_enabled(self) -> bool:
        """Check if Gist publishing is enabled"""
        return self.enabled

# Example usage
async def main():
    """Test the Gist publisher"""
    publisher = GistPublisher()
    
    if not publisher.is_enabled():
        print("GitHub token not configured - set GITHUB_TOKEN environment variable")
        return
    
    # Test content
    test_content = """# Test SPX Analysis Report

This is a test report generated at """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """

## Test Data
- Sample metric 1: $50.00
- Sample metric 2: 25%
- Sample metric 3: Increasing trend

## Conclusion
This is a test of the Gist publishing system.
"""
    
    result = await publisher.create_gist("Test-SPX-Report", test_content, "Test SPX analysis report")
    
    if result:
        print(f"Test Gist created: {result.get('url', 'No URL')}")
    else:
        print("Failed to create test Gist")

if __name__ == "__main__":
    asyncio.run(main()) 